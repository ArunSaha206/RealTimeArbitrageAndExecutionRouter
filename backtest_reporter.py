import os
import pickle
import numpy as np
import pandas as pd
from datetime import datetime, timezone

from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from console_theme import console

def print_strategy_header(strategy_name, bar_resolution, lookback, position_mode):
    # Slice off the module path to only show the strategy name
    display_name = strategy_name.split('.')[-1]
    console.print()
    console.rule(f"[header]NOW RUNNING STRATEGY: {display_name} | Res={bar_resolution} | Lookback={lookback} | Sizing={position_mode}[/header]")
    console.print()

def print_regime_header(regime_name, start_date, end_date):
    console.print()
    console.rule(f"📅 EXECUTING REGIME: [bold cyan]{regime_name.upper()}[/bold cyan] ({start_date} to {end_date})", style="white")
    console.print()

def print_monte_carlo_header(strategy_name, num_regimes):
    # Slice off the module path to keep the name clean
    display_name = strategy_name.split('.')[-1]
    console.print(f"\n[bold white]🎲 Running Vectorized Monte Carlo Simulations for [cyan]{num_regimes}[/cyan] Regimes on [cyan]{display_name}[/cyan]...[/bold white]\n")

def print_regime_summary(strategy_name, regime_name, target_universe_size, all_results_len, gross_pnl, gross_pnl_pct, 
                         enable_taxes, tax_label, tax_impact, aggregate_pnl, aggregate_pnl_pct, 
                         avg_buy_hold_pct, spy_metrics, total_trade_count, win_rate, wins_count, 
                         losses_count, profit_factor, gross_profit, gross_loss, 
                         portfolio_max_dd_dollars, portfolio_max_dd_pct, portfolio_sharpe):
    
    # Helper to ensure the +/- is strictly formatted before the dollar sign
    def fmt_money(val):
        if val == 0: return "$0.00"
        return f"{'+$' if val > 0 else '-$'}{abs(val):,.2f}"

    text = Text()
    text.append("\n")
    
    # 1. Overview & Stats
    text.append(f"🌍 Total Symbols Evaluated:       {all_results_len} / {target_universe_size}\n")
    text.append(f"🔄 Total Trades Executed:         {total_trade_count}\n")
    if total_trade_count < 100:
        text.append(f"⚠️  WARNING: Low sample size ({total_trade_count} trades). Sharpe may be statistically unreliable.\n", style="loss")
        
    text.append(f"🎯 Win Rate:                      {win_rate:.1f}% ({wins_count} W / {losses_count} L)\n")
    text.append(f"💰 Profit Factor:                 {profit_factor:.2f} (Gross Profit: ${gross_profit:,.2f} / Gross Loss: ${gross_loss:,.2f})\n\n")

    # 2. Financials
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
    
    # 3. Benchmarks
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
    
    # 4. Risk
    text.append("📉 Risk Metrics:\n", style="bold")
    text.append(f"   • Max Portfolio Drawdown:      -${portfolio_max_dd_dollars:,.2f}  (")
    text.append(f"-{portfolio_max_dd_pct:.2f}%", style="loss")
    text.append(")\n")
    text.append(f"   • Portfolio Sharpe Ratio:      {portfolio_sharpe:.2f}\n")

    display_name = strategy_name.split('.')[-1]
    panel = Panel(text, title=f"REGIME PORTFOLIO SUMMARY: {regime_name.upper()} ({display_name})", border_style="white", expand=False)
    console.print(panel)

def print_global_summary(strategy_name, global_summary, enable_taxes, total_regimes):
    from rich import box
    
    # Helper for the summary panel at the bottom (keeps cents)
    def fmt_money(val):
        if val == 0: return "$0.00"
        return f"{'+$' if val > 0 else '-$'}{abs(val):,.2f}"

    # Helper for the table (drops cents to save horizontal space)
    def fmt_short_money(val):
        if val == 0: return "$0"
        return f"{'+$' if val > 0 else '-$'}{abs(val):,.0f}"

    display_name = strategy_name.split('.')[-1]
    console.print()
    
    # Matching the Vibe: Rounded box, white border, emojis in title
    table = Table(
        title=f"🌍 MULTI-REGIME SUMMARY FOR: {display_name}", 
        box=box.ROUNDED,
        border_style="white",
        title_style="bold",
        header_style="bold"
    )
    
    # Compact headers to prevent wrapping
    table.add_column("REGIME", style="cyan")
    table.add_column("PRE-$", justify="right")
    table.add_column("PRE-%", justify="right")
    table.add_column("TAX", justify="right")
    table.add_column("POST-$", justify="right")
    table.add_column("POST-%", justify="right")
    table.add_column("B&H%", justify="right")
    table.add_column("TRADES", justify="right")
    table.add_column("WIN%", justify="right")
    table.add_column("PF", justify="right")
    table.add_column("SHARPE", justify="right")
    table.add_column("MAX DD", justify="right")
    table.add_column("BETA", justify="right")
    table.add_column("ALPHA", justify="right")

    for rs in global_summary["regime_summaries"]:
        beta_str = f"{rs['beta']:.2f}" if rs['beta'] is not None else "N/A"
        
        # Colorize Alpha and B&H
        if rs['alpha'] is not None:
            alpha_str = f"[{'gain' if rs['alpha'] >= 0 else 'loss'}]{rs['alpha']:+.1f}%[/]"
        else:
            alpha_str = "N/A"
            
        bh_str = f"[{'gain' if rs['bh_pct'] >= 0 else 'loss'}]{rs['bh_pct']:+.1f}%[/]"
        
        t_imp = rs['tax_impact']
        tax_str = fmt_short_money(t_imp) if enable_taxes else "$0"
        
        pre_color = "gain" if rs['pre_tax_pnl'] >= 0 else "loss"
        post_color = "gain" if rs['post_tax_pnl'] >= 0 else "loss"

        table.add_row(
            rs['name'][:18],
            fmt_short_money(rs['pre_tax_pnl']),
            f"[{pre_color}]{rs['pre_tax_pnl_pct']:+.1f}%[/]",
            tax_str,
            fmt_short_money(rs['post_tax_pnl']),
            f"[{post_color}]{rs['post_tax_pnl_pct']:+.1f}%[/]",
            bh_str,
            str(rs['trades']),
            f"{rs['win_rate']:.1f}%",
            f"{rs['pf']:.2f}",
            f"{rs['sharpe']:.2f}",
            f"[loss]-{rs['max_dd_pct']:.1f}%[/]",
            beta_str,
            alpha_str
        )

    console.print(table)
    
    # ---------------------------------------------------------
    # GLOBAL AGGREGATES PANEL
    # ---------------------------------------------------------
    g_pnl_pre_tax = global_summary["total_ending_capital_pre_tax"] - global_summary["total_initial_capital"]
    g_pnl_pct_pre_tax = (g_pnl_pre_tax / global_summary["total_initial_capital"]) * 100 if global_summary["total_initial_capital"] > 0 else 0.0
    g_pnl_post_tax = global_summary["total_ending_capital_post_tax"] - global_summary["total_initial_capital"]
    g_pnl_pct_post_tax = (g_pnl_post_tax / global_summary["total_initial_capital"]) * 100 if global_summary["total_initial_capital"] > 0 else 0.0
    global_win_rate = (global_summary["total_wins"] / global_summary["total_trades"] * 100) if global_summary["total_trades"] > 0 else 0.0
    global_pf = (global_summary["total_gross_profit"] / global_summary["total_gross_loss"]) if global_summary["total_gross_loss"] > 0 else 0.0
    avg_global_bh = np.mean(global_summary["bh_returns"]) if global_summary["bh_returns"] else 0.0

    agg_text = Text()
    agg_text.append("\n")
    agg_text.append(f"🌍 Total Symbols Evaluated:       {global_summary['total_symbols_evaluated']}\n")
    agg_text.append(f"🔄 Total Trades Executed:         {global_summary['total_trades']}\n")
    agg_text.append(f"🎯 Global Win Rate:               {global_win_rate:.1f}% ({global_summary['total_wins']} W / {global_summary['total_losses']} L)\n")
    agg_text.append(f"💰 Global Profit Factor:          {global_pf:.2f}\n\n")

    agg_text.append("📊 Global Financials:\n", style="bold")
    agg_text.append(f"   • Total Initial Capital:       ${global_summary['total_initial_capital']:,.2f}\n")
    
    agg_text.append(f"   • Global Pre-Tax P&L:          {fmt_money(g_pnl_pre_tax):>13}  (")
    agg_text.append(f"{g_pnl_pct_pre_tax:+.2f}%", style="gain" if g_pnl_pre_tax >= 0 else "loss")
    agg_text.append(")\n")
    
    if enable_taxes:
        net_tax = global_summary['total_tax_impact']
        agg_text.append(f"   • Global Net Tax Impact:       {fmt_money(net_tax):>13}  ({ '(Credit)' if net_tax > 0 else '(Paid)' })\n")
        
    agg_text.append(f"   • Global Post-Tax P&L:         {fmt_money(g_pnl_post_tax):>13}  (")
    agg_text.append(f"{g_pnl_pct_post_tax:+.2f}%", style="gain" if g_pnl_post_tax >= 0 else "loss")
    agg_text.append(")\n\n")
    
    agg_text.append("📈 Benchmark Comparisons:\n", style="bold")
    agg_text.append(f"   • Global Avg B&H Return:       ")
    agg_text.append(f"{avg_global_bh:+.2f}%\n", style="gain" if avg_global_bh >= 0 else "loss")

    console.print(Panel(agg_text, title=f"GLOBAL AGGREGATES ({display_name})", border_style="white", expand=False))

def generate_comparison_matrix(multi_strategy_results):
    from rich import box
    export_summary_rows = []
    
    if len(multi_strategy_results) <= 1:
        return export_summary_rows

    all_regime_names = []
    for res in multi_strategy_results:
        for rs in res["global_summary"]["regime_summaries"]:
            if rs["name"] not in all_regime_names:
                all_regime_names.append(rs["name"])

    console.print()
    
    # Matching the Vibe: Rounded box, white border, emojis in title
    matrix_table = Table(
        title="🏆 ULTIMATE STRATEGY COMPARISON MATRIX", 
        box=box.ROUNDED, 
        border_style="white",
        title_style="bold",
        header_style="bold"
    )
    
    # Compact headers to prevent terminal wrapping and truncation
    matrix_table.add_column("STRATEGY", style="cyan")
    matrix_table.add_column("PRE-$", justify="right")
    matrix_table.add_column("PRE-%", justify="right")
    matrix_table.add_column("POST-$", justify="right")
    matrix_table.add_column("POST-%", justify="right")
    matrix_table.add_column("WIN%", justify="right")
    
    for r in all_regime_names:
        # Extract the first word of the regime (e.g., 'COVID' from 'COVID_CRASH_2020')
        short_r = r.split('_')[0].upper()
        matrix_table.add_column(f"{short_r} W%", justify="right")
        
    matrix_table.add_column("PF", justify="right")
    matrix_table.add_column("SHARPE", justify="right")
    matrix_table.add_column("MAX DD", justify="right")
    matrix_table.add_column("BETA", justify="right")

    for res in multi_strategy_results:
        # Isolate the clean display name for rendering only
        display_name = res["name"].split('.')[-1]
        
        g_sum = res["global_summary"]
        
        if g_sum["total_symbols_evaluated"] == 0:
            continue
            
        if g_sum["regime_summaries"]:
            avg_sharpe = np.mean([r["sharpe"] for r in g_sum["regime_summaries"]])
            avg_dd = np.mean([r["max_dd_pct"] for r in g_sum["regime_summaries"]])
            valid_betas = [r["beta"] for r in g_sum["regime_summaries"] if r["beta"] is not None]
            avg_beta = np.mean(valid_betas) if valid_betas else 0.0
        else:
            avg_sharpe, avg_dd, avg_beta = 0.0, 0.0, 0.0
        
        g_pnl_pre = g_sum["total_ending_capital_pre_tax"] - g_sum["total_initial_capital"]
        g_pnl_post = g_sum["total_ending_capital_post_tax"] - g_sum["total_initial_capital"]
        g_pnl_pct_pre = (g_pnl_pre / g_sum["total_initial_capital"]) * 100 if g_sum["total_initial_capital"] > 0 else 0.0
        g_pnl_pct_post = (g_pnl_post / g_sum["total_initial_capital"]) * 100 if g_sum["total_initial_capital"] > 0 else 0.0
        overall_win_rate = (g_sum["total_wins"] / g_sum["total_trades"] * 100) if g_sum["total_trades"] > 0 else 0.0
        pf = (g_sum["total_gross_profit"] / g_sum["total_gross_loss"]) if g_sum["total_gross_loss"] > 0 else 0.0
        
        regime_win_map = {rs["name"]: rs["win_rate"] for rs in g_sum["regime_summaries"]}
        
        # Original name stays for safe downstream persistence
        row_export_dict = {
            "Strategy": res["name"],
            "Pre-Tax PnL ($)": round(g_pnl_pre, 2),
            "Pre-Tax PnL (%)": round(g_pnl_pct_pre, 2),
            "Post-Tax PnL ($)": round(g_pnl_post, 2),
            "Post-Tax PnL (%)": round(g_pnl_pct_post, 2),
            "Overall Win Rate (%)": round(overall_win_rate, 2),
        }

        pre_color = "gain" if g_pnl_pre >= 0 else "loss"
        post_color = "gain" if g_pnl_post >= 0 else "loss"

        # Drop cents (decimals) in the matrix to save horizontal space
        def fmt_short_money(val):
            if val == 0: return "$0"
            return f"{'+$' if val > 0 else '-$'}{abs(val):,.0f}"

        row_cells = [
            display_name,
            fmt_short_money(g_pnl_pre),
            f"[{pre_color}]{g_pnl_pct_pre:+.1f}%[/]",
            fmt_short_money(g_pnl_post),
            f"[{post_color}]{g_pnl_pct_post:+.1f}%[/]",
            f"{overall_win_rate:.1f}%"
        ]

        for r_name in all_regime_names:
            if r_name in regime_win_map:
                w_val = regime_win_map[r_name]
                row_cells.append(f"{w_val:.1f}%")
                row_export_dict[f"{r_name} Win %"] = round(w_val, 2)
            else:
                row_cells.append("N/A")
                row_export_dict[f"{r_name} Win %"] = "N/A"

        row_cells.extend([
            f"{pf:.2f}",
            f"{avg_sharpe:.2f}",
            f"[loss]-{avg_dd:.1f}%[/]",
            f"{avg_beta:.2f}"
        ])

        matrix_table.add_row(*row_cells)

        row_export_dict.update({
            "Profit Factor": round(pf, 2),
            "Avg Sharpe": round(avg_sharpe, 2),
            "Avg Max Drawdown (%)": round(avg_dd, 2),
            "Avg Beta": round(avg_beta, 2),
            "Total Trades Executed": g_sum["total_trades"]
        })
        export_summary_rows.append(row_export_dict)

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