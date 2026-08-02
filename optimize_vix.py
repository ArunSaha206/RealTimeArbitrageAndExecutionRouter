import optuna
import pandas as pd
import plotly.express as px

# Import your backtest engine runner
from backtest import run_backtest 

# Suppress excessive logging during optimization loops
optuna.logging.set_verbosity(optuna.logging.WARN)

RUNS = 30

def objective(trial):
    # Search space for VIX exponential parameters
    divisor = trial.suggest_float("divisor", 2, 30)
    exponent = trial.suggest_float("exponent", 1.0, 5.0)
    
    # ---------------------------------------------------------
    # ⚙️ ENFORCEMENT PARAMETERS
    # ---------------------------------------------------------
    MIN_TRADES_PER_REGIME = 1000  # Minimum trades required per regime
    FIFTH_PERCENTILE_THRESHOLD = -1500  # Minimum 5th percentile Monte Carlo profit
    # ---------------------------------------------------------s

    print(f"\n[Trial {trial.number}] Testing -> Divisor: {divisor:.2f}, Exponent: {exponent:.2f}")

    try:
        # Inject parameters into the strategy to bypass multiprocessing silo & cache
        from strategies.FiveMinute.Support import M5vixsupport
        
        # 1. Grab the strategy's base configuration
        base_params = M5vixsupport.get_params()
        
        # 2. Monkey-patch get_params() to inject our Optuna trial variables dynamically.
        # This guarantees the cache hash changes and the worker CPUs receive the variables.
        def injected_get_params():
            params = base_params.copy()
            params["vix_divisor"] = divisor
            params["vix_exponent"] = exponent
            return params
            
        M5vixsupport.get_params = injected_get_params
        
        # Clear main process cache just to be safe
        if hasattr(M5vixsupport, '_VIX_DAILY_CACHE'):
            M5vixsupport._VIX_DAILY_CACHE.clear()

        # ---------------------------------------------------------
        # 🛑 DEFINE THE EARLY STOPPING CALLBACK
        # ---------------------------------------------------------
        def early_stopper(regime_name, regime_trades, regime_pnl):
            if regime_trades < MIN_TRADES_PER_REGIME:
                print(f"[Trial {trial.number}] Pruned Early: {regime_name} only had {regime_trades} trades (Requires {MIN_TRADES_PER_REGIME}+).")
                raise optuna.TrialPruned()
                
            if regime_pnl <= FIFTH_PERCENTILE_THRESHOLD:
                print(f"[Trial {trial.number}] Pruned Early: {regime_name} had negative Net P&L (${regime_pnl:,.2f}).")
                raise optuna.TrialPruned()

        # Run the backtest engine, restricted to M5vixsupport only — this
        # both skips fully backtesting any OTHER strategy in
        # ACTIVE_STRATEGIES (wasted compute every trial) and guarantees the
        # returned stats are matched by name, not by list position, so
        # reordering ACTIVE_STRATEGIES (or M5supportsafe producing results
        # while M5vixsupport produces none) can no longer silently score
        # the wrong strategy.
        results = run_backtest(regime_evaluator=early_stopper, target_strategy_name=M5vixsupport.__name__)
        
        # Extract global metrics
        summary = results.get("global_summary", {})
        net_pnl = summary.get("total_ending_capital_post_tax", 0.0) - summary.get("total_initial_capital", 0.0)
        total_trades = results.get("total_trades", 0)
        win_rate = results.get("win_rate", 0.0)

        # =====================================================================
        # 🛡️ STRICT CONSTRAINTS: POSITIVE P5 ACROSS ALL REGIMES
        # (Minimum trades & profitability are handled by the early_stopper)
        # =====================================================================
        regimes = summary.get("regime_summaries", [])
        
        if not regimes:
            print(f"[Trial {trial.number}] Pruned: No regime summaries found.")
            raise optuna.TrialPruned()
            
        for rs in regimes:
            regime_name = rs.get("name", "UNKNOWN")
                
            # CONSTRAINT 2: Every regime must have a positive 5th percentile Monte Carlo profit
            mc = rs.get("monte_carlo")
            if mc:
                p5_profit = mc["percentiles"]["p5"] - mc["starting_capital"]
                if p5_profit <= FIFTH_PERCENTILE_THRESHOLD:
                    print(f"[Trial {trial.number}] Pruned: {regime_name} failed 5th %ile Constraint (${p5_profit:,.2f})")
                    raise optuna.TrialPruned()
            else:
                # If a regime didn't generate MC stats, discard the trial
                print(f"[Trial {trial.number}] Pruned: {regime_name} missing Monte Carlo data.")
                raise optuna.TrialPruned()
        # =====================================================================

        print(f"[Trial {trial.number}] Success -> Win Rate: {win_rate:.2f}% | Net Profit: ${net_pnl:,.2f}")

        # Stash trial attributes for easy plotting later
        trial.set_user_attr("divisor", divisor)
        trial.set_user_attr("exponent", exponent)
        trial.set_user_attr("total_trades", total_trades)
        trial.set_user_attr("net_pnl", net_pnl)

        # Return BOTH metrics to construct the Pareto Frontier
        return win_rate, net_pnl

    except optuna.TrialPruned:
        raise
    except Exception as e:
        print(f"[Trial {trial.number}] Failed with error: {e}")
        return 0.0, -999999.0

if __name__ == "__main__":
    print("=== STARTING MULTI-OBJECTIVE VIX HYPERPARAMETER OPTIMIZATION ===")
    
    # Enable dual-objective maximization for Win Rate AND Net P&L
    study = optuna.create_study(directions=["maximize", "maximize"])
    
    # Run optimization for a designated number of trials
    study.optimize(objective, n_trials = RUNS)

    print("\n==============================================")
    print("        PARETO OPTIMIZATION COMPLETE          ")
    print("==============================================")

    # Collect trial results into a DataFrame for plotting
    trials_data = []
    for t in study.trials:
        if t.state == optuna.trial.TrialState.COMPLETE:
            trials_data.append({
                "Trial": t.number,
                "Win Rate (%)": t.values[0],
                "Net Profit ($)": t.values[1],
                "Divisor": t.user_attrs.get("divisor"),
                "Exponent": t.user_attrs.get("exponent"),
                "Total Trades": t.user_attrs.get("total_trades"),
                "Is Pareto Optimal": t in study.best_trials
            })

    if trials_data:
        df_trials = pd.DataFrame(trials_data)
        df_trials.to_csv("vix_pareto_results.csv", index=False)
        print(f"✅ Saved {len(df_trials)} valid trial results to 'vix_pareto_results.csv'")

        # Generate Interactive Plotly Scatter Plot
        fig = px.scatter(
            df_trials,
            x="Win Rate (%)",
            y="Net Profit ($)",
            color="Is Pareto Optimal",
            size="Total Trades",
            hover_data=["Trial", "Divisor", "Exponent", "Total Trades"],
            title="<b>VIX Strategy Isoquant: Win Rate vs. Net Profit Pareto Frontier</b>",
            color_discrete_map={True: "#00E676", False: "#37474F"}
        )
        
        fig.update_layout(template="plotly_dark", height=600)
        fig.write_html("pareto_frontier.html")
        print("📊 Generated interactive graph: open 'pareto_frontier.html' in your browser!")
        fig.show()
    else:
        print("⚠️ No trials successfully passed the strict regime constraints. Consider loosening the bounds or min trades.")