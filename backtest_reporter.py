import os
import pickle
import numpy as np
import pandas as pd
from datetime import datetime, timezone

from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich import box
from console_theme import console

def print_strategy_header(strategy_name, bar_resolution, lookback, position_mode):
    console.print()
    console.rule(f"[header]NOW RUNNING STRATEGY: {strategy_name} | Res={bar_resolution} | Lookback={lookback} | Sizing={position_mode}[/header]")
    console.print()

def print_regime_header(regime_name, start_date, end_date):
    console.print()
    console.rule(f"📅 EXECUTING REGIME: [bold cyan]{regime_name.upper()}[/bold cyan] ({start_date} to {end_date})", style="white")
    console.print()

def print_monte_carlo_header(strategy_name, num_regimes):
    console.print(f"\n[bold white]🎲 Running Vectorized Monte Carlo Simulations for [cyan]{num_regimes}[/cyan] Regimes on [cyan]{strategy_name}[/cyan]...[/bold white]\n")

def print_regime_summary(strategy_name, regime_name, target_universe_size, all_results_len, gross_pnl, gross_pnl_pct, 
                         enable_taxes, tax_label, tax_impact, aggregate_pnl, aggregate_pnl_pct, 
                         avg_buy_hold_pct, spy_metrics, total_trade_count, win_rate, wins_count, 
                         losses_count, profit_factor, gross_profit, gross_loss, 
                         portfolio_max_dd_dollars, portfolio_max_dd_pct, portfolio_sharpe):
    
    def fmt_money(val):
        if val == 0: return "$0.00"
        return f"{'+$' if val > 0 else '-$'}{abs(val):,.2f}"

    text = Text()
    text.append("\n")
    
    text.append(f"🌍 Total Symbols Evaluated:       {all_results_len} / {target_universe_size}\n")
    text.append(f"🔄 Total Trades Executed:         {total_trade_count}\n")
    if total_trade_count < 100:
        text.append(f"⚠️  WARNING: Low sample size ({total_trade_count} trades). Sharpe may be statistically unreliable.\n", style="loss")
        
    text.append(f"🎯 Win Rate:                      {win_rate:.1f}% ({wins_count} W / {losses_count} L)\n")
    text.append(f"💰 Profit Factor:                 {profit_factor:.2f} (Gross Profit: ${gross_profit:,.2f} / Gross Loss: ${gross_loss:,.2f})\n\n")

    text.append("📊 Portfolio Financials:\n", style="bold")
    
    pnl_style = "gain" if gross_pnl >= 0 else "loss"
    text.append(f"   • Pre-Tax Gross P&L:           {fmt_money(gross_pnl):>12}  (")
    text.append(f"{gross_pnl_pct:+.2f}%", style=pnl_style)
    text.append(")\n")
    
    if enable_taxes:
        text.append(f"   • {tax_label}:             {fmt_money(tax_impact):>12}\n")
        
    net_pnl_style = "gain" if aggregate_pnl >= 0 else "loss"
    text.append(f"   • Post-Tax Net P&L:            {fmt_money(aggregate_pnl):>12}  (")
    text.append(f"{aggregate_pnl_pct:+.2f}%", style=net_pnl_style)
    text.append(")\n\n")
    
    text.append("📈 Benchmark Comparisons:\n", style="bold")
    text.append(f"   • Benchmark Avg Return:        ")
    text.append(f"{avg_buy_hold_pct:+.2f}%\n", style="gain" if avg_buy_hold_pct >= 0 else "loss")
    
    if spy_metrics:
        text.append(f"   • SPY Benchmark Return:        ")
        text.append(f"{spy_metrics['bench_return_pct']:+.2f}%\n", style="gain" if spy_metrics['bench_return_pct'] >= 0 else "loss")
        text.append(f"   • Broad Market Beta (vs SPY):   {spy_metrics['beta']:.2f}\n")
        text.append(f"   • Jensen's Alpha (vs SPY):     ")
        text.append(f"{spy_metrics['alpha_pct']:+.2f}%\n", style="gain" if spy_metrics['alpha_pct'] >= 0 else "loss")
    else:
        text.append(f"   • SPY Benchmark Metrics:       N/A (Insufficient alignment)\n", style="muted")
    text.append("\n")
    
    text.append("📉 Risk Metrics:\n", style="bold")
    text.append(f"   • Max Portfolio Drawdown:      -${portfolio_max_dd_dollars:,.2f}  (")
    text.append(f"-{portfolio_max_dd_pct:.2f}%", style="loss")
    text.append(")\n")
    text.append(f"   • Portfolio Sharpe Ratio:      {portfolio_sharpe:.2f}\n")

    panel = Panel(text, title=f"REGIME PORTFOLIO SUMMARY: {regime_name.upper()} ({strategy_name})", border_style="white", expand=False)
    console.print(panel)

def print_global_summary(strategy_name, global_summary, enable_taxes, total_regimes):
    def fmt_money(val):
        if val == 0: return "$0.00"
        return f"{'+$' if val > 0 else '-$'}{abs(val):,.2f}"

    def fmt_short_money(val):
        if val == 0: return "$0"
        return f"{'+$' if val > 0 else '-$'}{abs(val):,.0f}"

    console.print()
    
    table = Table(
        title=f"🌍 MULTI-REGIME SUMMARY FOR: {strategy_name}", 
        box=box.ROUNDED, border_style="white", title_style="bold", header_style="bold"
    )
    
    table.add_column("REGIME", style="cyan")
    table.add_column("PRE-$", justify="right")
    table.add_column("PRE-%", justify="right")
    table.add_column("POST-$", justify="right")
    table.add_column("POST-%", justify="right")
    table.add_column("B&H%", justify="right")
    table.add_column("TRADES", justify="right")
    table.add_column("WIN%", justify="right")
    table.add_column("PF", justify="right")
    table.add_column("SHARPE", justify="right")
    table.add_column("MAX DD", justify="right")

    for rs in global_summary["regime_summaries"]:
        bh_str = f"[{'gain' if rs['bh_pct'] >= 0 else 'loss'}]{rs['bh_pct']:+.1f}%[/]"
        pre_color = "gain" if rs['pre_tax_pnl'] >= 0 else "loss"
        post_color = "gain" if rs['post_tax_pnl'] >= 0 else "loss"

        table.add_row(
            rs['name'][:18],
            fmt_short_money(rs['pre_tax_pnl']),
            f"[{pre_color}]{rs['pre_tax_pnl_pct']:+.1f}%[/]",
            fmt_short_money(rs['post_tax_pnl']),
            f"[{post_color}]{rs['post_tax_pnl_pct']:+.1f}%[/]",
            bh_str,
            str(rs['trades']),
            f"{rs['win_rate']:.1f}%",
            f"{rs['pf']:.2f}",
            f"{rs['sharpe']:.2f}",
            f"[loss]-{rs['max_dd_pct']:.1f}%[/]"
        )

    console.print(table)
    
    g_pnl_pre_tax = global_summary["total_ending_capital_pre_tax"] - global_summary["total_initial_capital"]
    g_pnl_pct_pre_tax = (g_pnl_pre_tax / global_summary["total_initial_capital"]) * 100 if global_summary["total_initial_capital"] > 0 else 0.0
    g_pnl_post_tax = global_summary["total_ending_capital_post_tax"] - global_summary["total_initial_capital"]
    g_pnl_pct_post_tax = (g_pnl_post_tax / global_summary["total_initial_capital"]) * 100 if global_summary["total_initial_capital"] > 0 else 0.0
    global_win_rate = (global_summary["total_wins"] / global_summary["total_trades"] * 100) if global_summary["total_trades"] > 0 else 0.0
    global_pf = (global_summary["total_gross_profit"] / global_summary["total_gross_loss"]) if global_summary["total_gross_loss"] > 0 else 0.0
    
    true_sharpe = global_summary.get("true_global_sharpe", 0.0)
    true_dd = global_summary.get("true_global_max_dd_pct", 0.0)

    agg_text = Text()
    agg_text.append("\n")
    agg_text.append(f"🌍 Total Symbols Evaluated:       {global_summary['total_symbols_evaluated']}\n")
    agg_text.append(f"🔄 Total Trades Executed:         {global_summary['total_trades']}\n")
    agg_text.append(f"🎯 Global Win Rate:               {global_win_rate:.1f}% ({global_summary['total_wins']} W / {global_summary['total_losses']} L)\n")
    agg_text.append(f"💰 Global Profit Factor:          {global_pf:.2f}\n\n")

    agg_text.append("📊 Global Financials:\n", style="bold")
    agg_text.append(f"   • Total Initial Capital:       ${global_summary['total_initial_capital']:,.2f}\n")
    agg_text.append(f"   • Global Pre-Tax P&L:          {fmt_money(g_pnl_pre_tax):>13}  ({g_pnl_pct_pre_tax:+.2f}%)\n")
    agg_text.append(f"   • Global Post-Tax P&L:         {fmt_money(g_pnl_post_tax):>13}  ({g_pnl_pct_post_tax:+.2f}%)\n\n")

    agg_text.append("📉 True Stitched Risk:\n", style="bold")
    agg_text.append(f"   • True Global Sharpe:          {true_sharpe:.2f}\n")
    agg_text.append(f"   • True Global Max DD:          -{true_dd:.2f}%\n")

    console.print(Panel(agg_text, title=f"GLOBAL AGGREGATES ({strategy_name})", border_style="white", expand=False))

def generate_comparison_matrix(multi_strategy_results):
    export_summary_rows = []
    if not multi_strategy_results: return export_summary_rows

    all_regime_names = []
    for res in multi_strategy_results:
        for rs in res["global_summary"]["regime_summaries"]:
            if rs["name"] not in all_regime_names:
                all_regime_names.append(rs["name"])

    # Define row labels vertically 
    metrics_list = [
        "Pre-Tax PnL ($)",
        "Pre-Tax PnL (%)",
        "Overall Win Rate (%)",
        "Profit Factor",
        "True Global Sharpe",
        "True Global Sortino",
        "True Global Max DD (%)",
    ]
    
    # Inject Expanded Metrics for each regime
    for r in all_regime_names:
        metrics_list.append(f"") # Visual spacer row for the terminal
        metrics_list.append(f"{r} WIN %")
        metrics_list.append(f"{r} PF")
        metrics_list.append(f"{r} Sharpe")
        metrics_list.append(f"{r} Sortino")
        metrics_list.append(f"{r} B&H %")
        metrics_list.append(f"{r} SPY B&H %")
        metrics_list.append(f"{r} MC 5th %")
        metrics_list.append(f"{r} MC 95th %")
        metrics_list.append(f"{r} MC Ruin %")
        
    metric_data = {m: [] for m in metrics_list}
    
    # Clean the strategy names (Strips out 'strategies.FifteenMinute.' but keeps the BPS tag)
    strat_names = []
    for res in multi_strategy_results:
        raw_name = res["name"]
        if " " in raw_name:
            strat_part, bps_part = raw_name.split(" ", 1)
            clean_name = f"{strat_part.split('.')[-1]} {bps_part}"
        else:
            clean_name = raw_name.split('.')[-1]
        strat_names.append(clean_name)
    
    for res in multi_strategy_results:
        g_sum = res["global_summary"]
        
        g_pnl_pre = g_sum["total_ending_capital_pre_tax"] - g_sum["total_initial_capital"]
        g_pnl_pct_pre = (g_pnl_pre / g_sum["total_initial_capital"]) * 100 if g_sum["total_initial_capital"] > 0 else 0.0
        overall_win_rate = (g_sum["total_wins"] / g_sum["total_trades"] * 100) if g_sum["total_trades"] > 0 else 0.0
        pf = (g_sum["total_gross_profit"] / g_sum["total_gross_loss"]) if g_sum["total_gross_loss"] > 0 else 0.0
        true_sharpe = g_sum.get("true_global_sharpe", 0.0)
        true_sortino = g_sum.get("true_global_sortino", 0.0)
        true_dd = g_sum.get("true_global_max_dd_pct", 0.0)
        
        def fmt_short_money(val):
            if val == 0: return "$0"
            return f"{'+$' if val > 0 else '-$'}{abs(val):,.0f}"

        pre_color = "gain" if g_pnl_pre >= 0 else "loss"

        # Populate Global Metrics
        metric_data["Pre-Tax PnL ($)"].append(fmt_short_money(g_pnl_pre))
        metric_data["Pre-Tax PnL (%)"].append(f"[{pre_color}]{g_pnl_pct_pre:+.1f}%[/]")
        metric_data["Overall Win Rate (%)"].append(f"{overall_win_rate:.1f}%")
        metric_data["Profit Factor"].append(f"{pf:.2f}")
        metric_data["True Global Sharpe"].append(f"{true_sharpe:.2f}")
        metric_data["True Global Sortino"].append(f"{true_sortino:.2f}") # <--- NOW APPENDED CORRECTLY
        metric_data["True Global Max DD (%)"].append(f"[loss]-{true_dd:.1f}%[/]")

        # Populate Regime Metrics
        regime_map = {rs["name"]: rs for rs in g_sum["regime_summaries"]}

        for r in all_regime_names:
            metric_data[""].append("") # Empty spacer
            if r in regime_map:
                rs = regime_map[r]
                
                # Standard Regime Metrics
                metric_data[f"{r} WIN %"].append(f"{rs['win_rate']:.1f}%")
                metric_data[f"{r} PF"].append(f"{rs['pf']:.2f}")
                metric_data[f"{r} Sharpe"].append(f"{rs['sharpe']:.2f}")
                
                sortino_val = rs.get('sortino', 0.0)
                metric_data[f"{r} Sortino"].append(f"{sortino_val:.2f}") # <--- REGIME SORTINO EXTRACTED
                
                bh_pct = rs.get("bh_pct", 0.0)
                metric_data[f"{r} B&H %"].append(f"[{'gain' if bh_pct >= 0 else 'loss'}]{bh_pct:+.1f}%[/]")
                
                # Monte Carlo & SPY Metrics
                mc = rs.get("monte_carlo")
                if mc:
                    cap = mc["starting_capital"]
                    p5 = ((mc["percentiles"]["p5"] - cap) / cap) * 100
                    p95 = ((mc["percentiles"]["p95"] - cap) / cap) * 100
                    ruin = mc["risk_of_ruin"]
                    spy_ret = mc.get("spy_return_pct")
                    
                    str_5th = f"[{'gain' if p5 >= 0 else 'loss'}]{p5:+.1f}%[/]"
                    str_95th = f"[{'gain' if p95 >= 0 else 'loss'}]{p95:+.1f}%[/]"
                    str_ruin = f"[loss]{ruin:.1f}%[/]" if ruin > 0 else "0.0%"
                    
                    if spy_ret is not None:
                        str_spy = f"[{'gain' if spy_ret >= 0 else 'loss'}]{spy_ret:+.1f}%[/]"
                    else:
                        str_spy = "N/A"
                    
                    metric_data[f"{r} SPY B&H %"].append(str_spy)
                    metric_data[f"{r} MC 5th %"].append(str_5th)
                    metric_data[f"{r} MC 95th %"].append(str_95th)
                    metric_data[f"{r} MC Ruin %"].append(str_ruin)
                else:
                    metric_data[f"{r} SPY B&H %"].append("N/A")
                    metric_data[f"{r} MC 5th %"].append("N/A")
                    metric_data[f"{r} MC 95th %"].append("N/A")
                    metric_data[f"{r} MC Ruin %"].append("N/A")
            else:
                metric_data[f"{r} WIN %"].append("N/A")
                metric_data[f"{r} PF"].append("N/A")
                metric_data[f"{r} Sharpe"].append("N/A")
                metric_data[f"{r} Sortino"].append("N/A") # <--- FALLBACK ADDED
                metric_data[f"{r} B&H %"].append("N/A")
                metric_data[f"{r} SPY B&H %"].append("N/A")
                metric_data[f"{r} MC 5th %"].append("N/A")
                metric_data[f"{r} MC 95th %"].append("N/A")
                metric_data[f"{r} MC Ruin %"].append("N/A")

    console.print()
    matrix_table = Table(
        title="🏆 TRANSPOSED STRATEGY COMPARISON MATRIX (MULTI-BPS)", 
        box=box.ROUNDED, border_style="white", title_style="bold", header_style="bold"
    )
    
    # Adding no_wrap=True to BOTH the metric column and the strategy columns
    matrix_table.add_column("METRIC", style="cyan", justify="left", no_wrap=True)
    for s in strat_names:
        matrix_table.add_column(s, justify="right", no_wrap=True)
        
    for m in metrics_list:
        row_cells = [m] + metric_data[m]
        matrix_table.add_row(*row_cells)
        
        # Strip the Rich color tags so the CSV and Streamlit charts render cleanly
        if m != "":
            clean_row = {"Metric": m}
            for i, s in enumerate(strat_names):
                raw_val = metric_data[m][i]
                clean_val = raw_val.replace("[gain]", "").replace("[loss]", "").replace("[/]", "")
                clean_row[s] = clean_val
            export_summary_rows.append(clean_row)

    console.print(matrix_table)
    return export_summary_rows

def save_and_export_data(enable_taxes, tax_rate, starting_cash, multi_strategy_results, export_summary_rows, master_trade_log, cache_dir):
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "enable_taxes": enable_taxes,
        "tax_rate": tax_rate,
        "starting_cash_per_ticker": starting_cash,
        "strategies": multi_strategy_results,
        "comparison_matrix": export_summary_rows,
    }
    report_path = os.path.join(cache_dir, "summary_report.pkl")
    try:
        with open(report_path, "wb") as f:
            pickle.dump(report, f)
        console.print(f"Report saved for dashboard access: {report_path}")
    except Exception as e:
        console.print(f"Failed to save summary report: {e}")

    if master_trade_log:
        console.print("Exporting data to CSV...")
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_dir = os.path.join("archive", f"backtest_results_{timestamp}")
        os.makedirs(out_dir, exist_ok=True)

        if len(multi_strategy_results) > 1 and export_summary_rows:
            summary_df = pd.DataFrame(export_summary_rows)
            summary_path = os.path.join(out_dir, "strategy_comparison.csv")
            summary_df.to_csv(summary_path, index=False)

        trades_df = pd.DataFrame(master_trade_log)
        trades_path = os.path.join(out_dir, "all_trades_log.csv")
        
        for col in ['entry_time', 'exit_time']:
            if col in trades_df.columns:
                trades_df[col] = trades_df[col].apply(lambda x: x.strftime('%Y-%m-%d %H:%M:%S') if isinstance(x, datetime) else x)
        
        trades_df.to_csv(trades_path, index=False)
        console.print(f"Success! Backtest results and raw logs saved to: {out_dir}/")