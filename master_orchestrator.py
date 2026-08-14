import os
import pickle
from collections import deque
from datetime import datetime

import numpy as np
import optuna
import pandas as pd
from rich.console import Console, Group
from rich.live import Live
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)
from rich.table import Table

# =====================================================================
# SPEED PATCH: SILENCE THE UI ENGINE & MONTE CARLO SPAM
# =====================================================================
import backtest
import backtest_control_center as control
import fitness_engine
import monte_carlo
from backtest import preload_regime_data, simulate_strategy_on_universe

# =====================================================================
# FITNESS ENGINE REGISTRY
# =====================================================================
# Every fitness function takes (regime_metrics_list) and returns a dict
# with at least "fitness_score", "avg_pf", "min_p5", "total_trades" --
# that's the only contract this file relies on. To add a new one: drop
# the module import, add one line to FITNESS_ENGINES, done. To switch
# which one runs: change ACTIVE_FITNESS_ENGINE below, nothing else.
FITNESS_ENGINES = {
    "heavy_tail": fitness_engine.calculate_heavy_tail_fitness,
    "bull_chop": fitness_engine.calculate_bull_chop_fitness,
    "bull_50th_pct": fitness_engine.calculate_percentile_fitness
}

# <-- THE ONLY LINE YOU NEED TO TOUCH TO SWAP FITNESS ENGINES
ACTIVE_FITNESS_ENGINE = "bull_50th_pct"

def get_active_fitness_fn():
    try:
        return FITNESS_ENGINES[ACTIVE_FITNESS_ENGINE]
    except KeyError:
        available = ", ".join(sorted(FITNESS_ENGINES)) or "(none registered)"
        raise ValueError(
            f"ACTIVE_FITNESS_ENGINE = '{ACTIVE_FITNESS_ENGINE}' is not registered. "
            f"Available: {available}"
        )

if hasattr(backtest, 'reporter'):
    backtest.reporter.print_strategy_header = lambda *args, **kwargs: None
    backtest.reporter.print_regime_header = lambda *args, **kwargs: None
    backtest.reporter.print_regime_summary = lambda *args, **kwargs: None
    backtest.reporter.print_global_summary = lambda *args, **kwargs: None
    backtest.reporter.print_monte_carlo_header = lambda *args, **kwargs: None
    backtest.reporter.generate_comparison_matrix = lambda *args, **kwargs: []
    backtest.reporter.save_and_export_data = lambda *args, **kwargs: None

if hasattr(monte_carlo, 'console'):
    monte_carlo.console.quiet = True
monte_carlo.print = lambda *args, **kwargs: None

console = Console()

# =====================================================================
# 1. ORCHESTRATOR SETTINGS & TOURNAMENT PARAMETERS
# =====================================================================
STAGE_1_TRIALS = 10          
STAGE_2_TRIALS = 15          
UNIVERSES_TO_KEEP = 5        

# Select which regime types to optimize against. Options: "BULL", "BEAR", "CHOP", "ALL"
TARGET_REGIME_TAGS = ["BULL"]

ALL_UNIVERSES = [
    "core_stratified",
    "top_dollar_volume_25",
    "cross_sectional_spread",
    "high_beta_growth",
    "defensive_value",
    "cyclical_macro",
    "tech_semiconductor_heavy"
]

ACTIVE_STRAT = control.ACTIVE_STRATEGIES[0]
SEARCH_SPACE = ACTIVE_STRAT.get_optuna_space()

# =====================================================================
# 1b. LIVE MONITORING STATE & DUPLICATE TRACKING
# =====================================================================
RECENT_TRIALS_WINDOW = 6  
recent_trials = deque(maxlen=RECENT_TRIALS_WINDOW)  
per_universe_stats = {}  
seen_parameter_hashes = set()  

def record_trial_result(universe_logic, trial_number, score, is_duplicate=False):
    status_label = "⚠️ WARNING: Duplicate Trial" if is_duplicate else "[green]OK[/green]"
    recent_trials.append((universe_logic, trial_number, score, status_label))

    stats = per_universe_stats.setdefault(universe_logic, {"scores": []})
    stats["scores"].append(score)
    scores = stats["scores"]
    stats["count"] = len(scores)
    stats["median"] = float(np.median(scores))
    stats["std"] = float(np.std(scores))
    stats["zero_trade_pct"] = 100.0 * sum(1 for s in scores if s == -10.0) / len(scores)


def build_monitor_group():
    stats_table = Table(title="Live Universe Diagnostics", expand=True, show_lines=False)
    stats_table.add_column("Universe", style="cyan", no_wrap=True)
    stats_table.add_column("Trials", justify="right")
    stats_table.add_column("Median", justify="right")
    stats_table.add_column("StdDev", justify="right")
    stats_table.add_column("Status")

    for u_logic in ALL_UNIVERSES:
        stats = per_universe_stats.get(u_logic)
        if not stats:
            stats_table.add_row(u_logic, "0", "--", "--", "[dim]not started[/dim]")
            continue

        count = stats["count"]
        median, std = stats["median"], stats["std"]
        zero_pct = stats["zero_trade_pct"]

        if count >= 3 and median == -10.0 and std == 0.0:
            status = "[bold red]⚠️  -10 WALL -- every trial hit 0 trades/failed[/bold red]"
        elif zero_pct >= 50:
            status = f"[yellow]⚠️  {zero_pct:.0f}% of trials hit penalty[/yellow]"
        else:
            status = "[green]OK[/green]"

        stats_table.add_row(u_logic, str(count), f"{median:.2f}", f"{std:.2f}", status)

    log_table = Table(title=f"Last {len(recent_trials)} Trial Results", expand=True, show_lines=False)
    log_table.add_column("Universe", style="cyan", no_wrap=True)
    log_table.add_column("Trial #", justify="right")
    log_table.add_column("Score", justify="right")
    log_table.add_column("Status / Warning", justify="left")

    for u_logic, trial_num, score, status_label in recent_trials:
        if score == -10.0:
            score_str = "[red]-10.00 (Penalty)[/red]"
        else:
            score_str = f"[green]{score:+.2f}[/green]"
        log_table.add_row(u_logic, str(trial_num), score_str, status_label)

    return Group(Panel(stats_table, border_style="white"), Panel(log_table, border_style="dim white"))

# =====================================================================
# 2. DYNAMIC OPTUNA OBJECTIVE FACTORY
# =====================================================================
def create_objective(universe_logic, phase_name):
    if phase_name == "TRAINING_1":
        base_regimes = control.REGIME_WINDOWS_TRAIN_1
    else:
        base_regimes = control.REGIME_WINDOWS_TRAIN_2

    if "ALL" in [t.upper() for t in TARGET_REGIME_TAGS]:
        regimes = base_regimes
    else:
        regimes = {k: v for k, v in base_regimes.items() if v.get("tag", "").upper() in [t.upper() for t in TARGET_REGIME_TAGS]}

    def objective(trial):
        dynamic_params = {}
        for param_name, config in SEARCH_SPACE.items():
            if config["type"] == "float":
                dynamic_params[param_name] = trial.suggest_float(
                    param_name, config["low"], config["high"], step=config.get("step")
                )
            elif config["type"] == "int":
                dynamic_params[param_name] = trial.suggest_int(
                    param_name, config["low"], config["high"], step=config.get("step", 1)
                )

        param_tuple = tuple(sorted(dynamic_params.items()))
        is_duplicate = param_tuple in seen_parameter_hashes
        if not is_duplicate:
            seen_parameter_hashes.add(param_tuple)

        trial.user_attrs["is_duplicate"] = is_duplicate

        regime_metrics_list = []
        for regime_name, regime_config in regimes.items():
            df_regime = preload_regime_data(regime_name, regime_config)
            if df_regime.empty: continue
            
            u_tickers = regime_config.get("universes", {}).get(universe_logic, [])
            if not u_tickers: continue

            df_universe = df_regime[df_regime['symbol'].isin(u_tickers)]
            
            metrics = simulate_strategy_on_universe(df_universe, **dynamic_params)
            if metrics["trades"] > 0:
                regime_metrics_list.append(metrics)

        evaluation = get_active_fitness_fn()(regime_metrics_list)

        trial.set_user_attr("total_trades", evaluation["total_trades"])
        trial.set_user_attr("avg_pf", evaluation["avg_pf"])
        trial.set_user_attr("min_p5_pct", evaluation["min_p5"])

        return evaluation["fitness_score"]
    
    return objective

# =====================================================================
# 3. DYNAMIC VALIDATION ENGINE
# =====================================================================
def run_validation_backtest(universe_logic, best_params, phase_name):
    if phase_name == "TRAINING_2":
        base_regimes = control.REGIME_WINDOWS_TRAIN_2
    else:
        base_regimes = control.REGIME_WINDOWS_FINAL_TEST

    if "ALL" in [t.upper() for t in TARGET_REGIME_TAGS]:
        regimes = base_regimes
    else:
        regimes = {k: v for k, v in base_regimes.items() if v.get("tag", "").upper() in [t.upper() for t in TARGET_REGIME_TAGS]}

    regime_metrics_list = []
    
    for regime_name, regime_config in regimes.items():
        df_regime = preload_regime_data(regime_name, regime_config)
        if df_regime.empty: continue
        
        u_tickers = regime_config.get("universes", {}).get(universe_logic, [])
        if not u_tickers: continue

        df_universe = df_regime[df_regime['symbol'].isin(u_tickers)]
        
        metrics = simulate_strategy_on_universe(df_universe, **best_params)
        if metrics["trades"] > 0:
            regime_metrics_list.append(metrics)

    evaluation = get_active_fitness_fn()(regime_metrics_list)
    return evaluation["fitness_score"]

# =====================================================================
# 4. MASTER ORCHESTRATOR PIPELINE
# =====================================================================
if __name__ == "__main__":
    console.rule(
        f"[bold white]🚀 QUANT EXECUTION MASTER ORCHESTRATOR | "
        f"STRATEGY: {ACTIVE_STRAT.__name__} | FITNESS: {ACTIVE_FITNESS_ENGINE}[/bold white]"
    )
    get_active_fitness_fn()  # fail fast at startup if ACTIVE_FITNESS_ENGINE is misconfigured

    optuna.logging.set_verbosity(optuna.logging.WARNING)
    
    studies = {
        u_logic: optuna.create_study(direction="maximize", sampler=optuna.samplers.TPESampler(seed=42))
        for u_logic in ALL_UNIVERSES
    }
    
    progress = Progress(
        SpinnerColumn(),
        TextColumn("[bold cyan]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TextColumn("•"),
        TimeElapsedColumn(),
        TextColumn("• ETA:"),
        TimeRemainingColumn(),
        auto_refresh=False
    )

    def render():
        return Group(progress, build_monitor_group())

    with Live(render(), console=console, refresh_per_second=4) as live:

        total_steps = len(ALL_UNIVERSES) + UNIVERSES_TO_KEEP + UNIVERSES_TO_KEEP
        master_task = progress.add_task("Total Pipeline Progress", total=total_steps)
        
        # ---------------------------------------------------------
        # STAGE 1: INITIAL EXPLORATION
        # ---------------------------------------------------------
        console.print(f"\n[bold yellow]STAGE 1: BROAD EXPLORATION ({STAGE_1_TRIALS} Trials / Universe)[/bold yellow]")
        
        for u_logic in ALL_UNIVERSES:
            trial_task = progress.add_task(f"Exploring {u_logic}", total=STAGE_1_TRIALS)
            
            def s1_callback(study, trial, u_logic=u_logic):
                progress.update(trial_task, advance=1)
                if trial.value is not None:
                    is_dup = trial.user_attrs.get("is_duplicate", False)
                    record_trial_result(u_logic, trial.number, trial.value, is_duplicate=is_dup)
                
                live.update(render())
                
            objective = create_objective(u_logic, "TRAINING_1")
            studies[u_logic].optimize(objective, n_trials=STAGE_1_TRIALS, callbacks=[s1_callback])
            
            progress.update(master_task, advance=1)
            progress.remove_task(trial_task)

        # # ---------------------------------------------------------
        # # STAGE 2: CONSISTENCY TOURNAMENT
        # # ---------------------------------------------------------
        # console.print(f"\n[bold yellow]STAGE 2: NARROWING TO TOP {UNIVERSES_TO_KEEP} (Median - StdDev Filter)[/bold yellow]")
        
        # consistency_scores = {}
        # for u_logic, study in studies.items():
        #     completed_trials = [t.value for t in study.trials if t.value is not None]
            
        #     if len(completed_trials) > 0:
        #         consistency_score = np.median(completed_trials) - np.std(completed_trials)
        #         consistency_scores[u_logic] = consistency_score
        #         console.print(f"   📊 {u_logic}: Median {np.median(completed_trials):.2f} | StdDev {np.std(completed_trials):.2f}")
        #     else:
        #         consistency_scores[u_logic] = -10.0
                
        # sorted_universes = sorted(consistency_scores.items(), key=lambda x: x[1], reverse=True)
        # top_5_logics = [x[0] for x in sorted_universes[:UNIVERSES_TO_KEEP]]
        
        # for u_logic, score in sorted_universes:
        #     if u_logic in top_5_logics:
        #         console.print(f"   [green]✔️ ADVANCED:[/green] {u_logic} (Score: {score:.2f})")
        #     else:
        #         console.print(f"   [red]❌ CULLED:[/red] {u_logic} (Score: {score:.2f})")

        # ---------------------------------------------------------
        # STAGE 2: CONSISTENCY TOURNAMENT
        # ---------------------------------------------------------
        console.print(f"\n[bold yellow]STAGE 2: NARROWING TO TOP {UNIVERSES_TO_KEEP} (Top-3 Valid Average)[/bold yellow]")
        
        consistency_scores = {}
        for u_logic, study in studies.items():
            # 1. Extract only valid trials (ignore the -10.0 penalties)
            valid_trials = [t.value for t in study.trials if t.value is not None and t.value > -9.0]
            
            if len(valid_trials) > 0:
                # 2. Sort descending so the highest fitness scores are first
                valid_trials.sort(reverse=True)
                
                # 3. Take the top 3 best performing trials (or fewer if 3 aren't available)
                top_k = valid_trials[:3]
                consistency_score = float(np.mean(top_k))
                
                consistency_scores[u_logic] = consistency_score
                console.print(f"   📊 {u_logic}: Top-{len(top_k)} Avg {consistency_score:.2f} | Valid Trials: {len(valid_trials)}/{STAGE_1_TRIALS}")
            else:
                # If Optuna failed every single trial, the universe is dead
                consistency_scores[u_logic] = -10.0
                console.print(f"   📊 {u_logic}: FAILED (All {STAGE_1_TRIALS} trials hit penalty)")
                
        sorted_universes = sorted(consistency_scores.items(), key=lambda x: x[1], reverse=True)
        top_5_logics = [x[0] for x in sorted_universes[:UNIVERSES_TO_KEEP]]
        
        for u_logic, score in sorted_universes:
            if u_logic in top_5_logics:
                console.print(f"   [green]✔️ ADVANCED:[/green] {u_logic} (Score: {score:.2f})")
            else:
                console.print(f"   [red]❌ CULLED:[/red] {u_logic} (Score: {score:.2f})")

        # ---------------------------------------------------------
        # STAGE 3: DEEP OPTIMIZATION
        # ---------------------------------------------------------
        console.print(f"\n[bold yellow]STAGE 3: DEEP OPTIMIZATION ({STAGE_2_TRIALS} More Trials / Survivor)[/bold yellow]")
        
        for u_logic in top_5_logics:
            trial_task = progress.add_task(f"Deep Tuning {u_logic}", total=STAGE_2_TRIALS)
            
            def s2_callback(study, trial, u_logic=u_logic):
                progress.update(trial_task, advance=1)
                if trial.value is not None:
                    is_dup = trial.user_attrs.get("is_duplicate", False)
                    record_trial_result(u_logic, trial.number, trial.value, is_duplicate=is_dup)
                
                live.update(render())
                
            objective = create_objective(u_logic, "TRAINING_1")
            studies[u_logic].optimize(objective, n_trials=STAGE_2_TRIALS, callbacks=[s2_callback])
            
            final_best_fitness = studies[u_logic].best_value
            console.print(f"   🎯 {u_logic} Locked! Final Train Fitness: {final_best_fitness:.2f}")
            
            progress.update(master_task, advance=1)
            progress.remove_task(trial_task)

        # ---------------------------------------------------------
        # STAGE 4: OUT-OF-SAMPLE VALIDATION
        # ---------------------------------------------------------
        console.print("\n[bold yellow]STAGE 4: OUT-OF-SAMPLE VALIDATION ON TRAINING_2...[/bold yellow]")
        final_results = []

        for u_logic in top_5_logics:
            val_task = progress.add_task(f"Validating {u_logic} OOS", total=1)
            
            best_params = studies[u_logic].best_params
            train_fitness = studies[u_logic].best_value
            
            console.print(f"   🔬 Testing {u_logic} out-of-sample...")
            val_fitness = run_validation_backtest(u_logic, best_params, "TRAINING_2")
            
            degradation = val_fitness - train_fitness
            
            final_results.append({
                "Universe Logic": u_logic,
                "Train Fitness": train_fitness,
                "Validate Fitness": val_fitness,
                "Degradation": degradation,
                "Best Params": best_params
            })
            
            progress.update(val_task, advance=1)
            progress.update(master_task, advance=1)
            progress.remove_task(val_task)
            live.update(render())

    # =====================================================================
    # FINAL REPORTING & COMPREHENSIVE DATA EXPORT
    # =====================================================================
    console.print("\n")
    table = Table(title=f"🏆 TOURNAMENT VALIDATION ({ACTIVE_STRAT.__name__})", show_lines=True)
    table.add_column("Universe Logic", style="cyan")
    table.add_column("Train", justify="right")
    table.add_column("Validate", justify="right")
    table.add_column("Degradation", justify="right")
    table.add_column("Best Parameters", justify="left")

    final_results = sorted(final_results, key=lambda x: x["Validate Fitness"], reverse=True)

    for res in final_results:
        deg_color = "green" if res["Degradation"] >= 0 else "red"
        param_str = ", ".join([f"{k}: {v:.2f}" if isinstance(v, float) else f"{k}: {v}" for k, v in res['Best Params'].items()])
        
        table.add_row(
            res["Universe Logic"],
            f"{res['Train Fitness']:.2f}",
            f"{res['Validate Fitness']:.2f}",
            f"[{deg_color}]{res['Degradation']:+.2f}[/{deg_color}]",
            param_str
        )

    console.print(table)
    
    if final_results:
        top_logic = final_results[0]["Universe Logic"]
        console.print(Panel.fit(
            f"👑 [bold green]TOURNAMENT CHAMPION:[/bold green] {top_logic}\n"
            f"This universe alignment provided the most robust OOS edge for {ACTIVE_STRAT.__name__}.", 
            border_style="green"
        ))

    console.print("\n📁 Exporting all orchestration data and trial history...")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = os.path.join("archive", f"orchestrator_results_{timestamp}")
    os.makedirs(out_dir, exist_ok=True)

    summary_df = pd.DataFrame([{
        "Universe Logic": r["Universe Logic"],
        "Train Fitness": r["Train Fitness"],
        "Validate Fitness": r["Validate Fitness"],
        "Degradation": r["Degradation"],
        **r["Best Params"]
    } for r in final_results])
    summary_csv_path = os.path.join(out_dir, "orchestrator_tournament_results.csv")
    summary_df.to_csv(summary_csv_path, index=False)

    all_trials_data = {}
    for u_logic, study in studies.items():
        all_trials_data[u_logic] = [
            {
                "trial_number": t.number,
                "value": t.value,
                "params": t.params,
                "state": str(t.state),
                "is_duplicate": t.user_attrs.get("is_duplicate", False)
            }
            for t in study.trials
        ]
    
    dump_path = os.path.join(out_dir, "orchestrator_study_dump.pkl")
    with open(dump_path, "wb") as f:
        pickle.dump({
            "strategy": ACTIVE_STRAT.__name__,
            "final_results": final_results,
            "all_studies_trials": all_trials_data
        }, f)

    console.print(f"Success! All orchestration data saved to: {out_dir}/")