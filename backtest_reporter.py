import os
import pickle
import numpy as np
import pandas as pd
from datetime import datetime, timezone

def print_strategy_header(strategy_name, bar_resolution, lookback, position_mode):
    print("\n" + "█" * 175)
    print(f" 🚀 NOW RUNNING STRATEGY: {strategy_name} | Res={bar_resolution} | Lookback={lookback} | Sizing={position_mode} ".center(175))
    print("█" * 175 + "\n")

def print_regime_summary(regime_name, target_universe_size, all_results_len, gross_pnl, gross_pnl_pct, 
                         enable_taxes, tax_label, tax_impact, aggregate_pnl, aggregate_pnl_pct, 
                         avg_buy_hold_pct, spy_metrics, total_trade_count, win_rate, wins_count, 
                         losses_count, profit_factor, gross_profit, gross_loss, 
                         portfolio_max_dd_dollars, portfolio_max_dd_pct, portfolio_sharpe):
    """Prints the per-regime summary to the terminal."""
    print("\n" + "=" * 115)
    print(f"                     REGIME PORTFOLIO SUMMARY: {regime_name.upper()}                                 ")
    print("=" * 115)
    print(f" Total Symbols Evaluated:     {all_results_len} / {target_universe_size}")
    print(f" Pre-Tax Gross P&L:           ${gross_pnl:+,.2f} ({gross_pnl_pct:+.2f}%)")
    
    if enable_taxes:
        print(f" {tax_label}: {('+$' if tax_impact > 0 else '-$')}{abs(tax_impact):,.2f}")
        
    print(f" Post-Tax Net P&L:            ${aggregate_pnl:+,.2f} ({aggregate_pnl_pct:+.2f}%)")
    print(f" Benchmark Average Return:    {avg_buy_hold_pct:+.2f}%")
    print("-" * 115)
    
    if spy_metrics:
        print(f" Broad Market Beta (β vs SPY): {spy_metrics['beta']:.2f}")
        print(f" Jensen's Alpha (α vs SPY):    {spy_metrics['alpha_pct']:+.2f}%")
        print(f" SPY Benchmark Return:        {spy_metrics['bench_return_pct']:+.2f}%")
    else:
        print(f" Broad Market Beta (β vs SPY): N/A (Insufficient daily benchmark alignment)")
        
    print("-" * 115)
    print(f" Total Trades Executed:       {total_trade_count}")
    
    if total_trade_count < 100:
        print(f" ⚠️ WARNING: Low sample size ({total_trade_count} trades). Sharpe may be statistically unreliable.")
        
    print(f" Win Rate:                    {win_rate:.1f}% ({wins_count} W / {losses_count} L)")
    print(f" Profit Factor:               {profit_factor:.2f} (Gross Profit: ${gross_profit:,.2f} / Gross Loss: ${gross_loss:,.2f})")
    print(f" Max Portfolio Drawdown:      -${portfolio_max_dd_dollars:,.2f} (-{portfolio_max_dd_pct:.2f}%)")
    print(f" Portfolio Sharpe Ratio:      {portfolio_sharpe:.2f}")
    print("=" * 115 + "\n")

def print_global_summary(strategy_name, global_summary, enable_taxes, total_regimes):
    """Prints the aggregated summary across all regimes for a single strategy."""
    g_pnl_pre_tax = global_summary["total_ending_capital_pre_tax"] - global_summary["total_initial_capital"]
    g_pnl_pct_pre_tax = (g_pnl_pre_tax / global_summary["total_initial_capital"]) * 100 if global_summary["total_initial_capital"] > 0 else 0.0
    
    g_pnl_post_tax = global_summary["total_ending_capital_post_tax"] - global_summary["total_initial_capital"]
    g_pnl_pct_post_tax = (g_pnl_post_tax / global_summary["total_initial_capital"]) * 100 if global_summary["total_initial_capital"] > 0 else 0.0

    global_win_rate = (global_summary["total_wins"] / global_summary["total_trades"] * 100) if global_summary["total_trades"] > 0 else 0.0
    global_pf = (global_summary["total_gross_profit"] / global_summary["total_gross_loss"]) if global_summary["total_gross_loss"] > 0 else 0.0
    avg_global_bh = np.mean(global_summary["bh_returns"]) if global_summary["bh_returns"] else 0.0

    print("\n" + "★" * 175)
    print(f"{'🌟 MULTI-REGIME SUMMARY FOR: ' + strategy_name + ' (PRE-TAX VS. POST-TAX) 🌟':^175}")
    print("★" * 175)

    print(f"{'REGIME':<18} | {'PRE-TAX P&L ($)':>15} | {'PRE-TAX (%)':>11} | {'TAX IMPACT ($)':>14} | {'POST-TAX P&L ($)':>16} | {'POST-TAX (%)':>12} | {'B&H (%)':>8} | {'TRADES':>6} | {'WIN %':>6} | {'PF':>5} | {'SHARPE':>6} | {'MAX DD':>8} | {'BETA':>5} | {'ALPHA (%)':>9}")
    print("-" * 175)
    for rs in global_summary["regime_summaries"]:
        r_name = rs['name'][:18]
        beta_str = f"{rs['beta']:>5.2f}" if rs['beta'] is not None else " N/A "
        alpha_str = f"{rs['alpha']:>8.2f}%" if rs['alpha'] is not None else "  N/A   "
        
        t_imp = rs['tax_impact']
        tax_str = f"{'+$' if t_imp > 0 else '-$'}{abs(t_imp):>9,.2f}" if enable_taxes else "$0.00"
        
        print(f"{r_name:<18} | ${rs['pre_tax_pnl']:>14,.2f} | {rs['pre_tax_pnl_pct']:>10.2f}% | {tax_str:>14} | ${rs['post_tax_pnl']:>15,.2f} | {rs['post_tax_pnl_pct']:>11.2f}% | {rs['bh_pct']:>7.2f}% | {rs['trades']:>6} | {rs['win_rate']:>5.1f}% | {rs['pf']:>4.2f} | {rs['sharpe']:>6.2f} | -{rs['max_dd_pct']:>6.2f}% | {beta_str} | {alpha_str}")
    print("-" * 175)

    print(f" Total Regimes Tested:        {total_regimes}")
    print(f" Total Symbols Evaluated:     {global_summary['total_symbols_evaluated']}")
    print(f" Total Cumulative Capital:    ${global_summary['total_initial_capital']:,.2f}")
    print("-" * 175)
    print(f" Global Gross P&L (PRE-TAX):  ${g_pnl_pre_tax:+,.2f} ({g_pnl_pct_pre_tax:+.2f}%)")
    if enable_taxes:
        net_tax = global_summary['total_tax_impact']
        print(f" Global Net Tax Impact:       {('+$' if net_tax > 0 else '-$')}{abs(net_tax):,.2f} {( '(Net Credit)' if net_tax > 0 else '(Net Paid)' )}")
    print(f" Global Net P&L (POST-TAX):   ${g_pnl_post_tax:+,.2f} ({g_pnl_pct_post_tax:+.2f}%)")
    print(f" Global Average B&H Return:   {avg_global_bh:+.2f}%")
    print("-" * 175)
    print(f" Total Trades Executed:       {global_summary['total_trades']}")
    print(f" Global Win Rate:             {global_win_rate:.1f}% ({global_summary['total_wins']} W / {global_summary['total_losses']} L)")
    print(f" Global Profit Factor:        {global_pf:.2f}")
    print("★" * 175 + "\n")


def generate_comparison_matrix(multi_strategy_results):
    """Generates and prints the final comparison matrix, returning rows for CSV export."""
    export_summary_rows = []
    
    if len(multi_strategy_results) <= 1:
        return export_summary_rows

    all_regime_names = []
    for res in multi_strategy_results:
        for rs in res["global_summary"]["regime_summaries"]:
            if rs["name"] not in all_regime_names:
                all_regime_names.append(rs["name"])

    regime_headers_str = " | ".join([f"{(r[:10] + ' W%'):>14}" for r in all_regime_names])

    print("\n" + "🏆" * 95)
    print(f"{'ULTIMATE STRATEGY COMPARISON MATRIX':^190}")
    print("🏆" * 95)
    print(f"{'STRATEGY':<18} | {'PRE-TAX ($)':>12} | {'PRE-TAX (%)':>11} | {'POST-TAX ($)':>13} | {'POST-TAX (%)':>12} | {'OVERALL W%':>10} | {regime_headers_str} | {'PF':>5} | {'AVG SHARPE':>10} | {'AVG MAX DD':>10} | {'AVG BETA':>8}")
    print("-" * 190)

    for res in multi_strategy_results:
        name = res["name"][:18]
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
        regime_win_cells = []
        row_export_dict = {
            "Strategy": res["name"],
            "Pre-Tax PnL ($)": round(g_pnl_pre, 2),
            "Pre-Tax PnL (%)": round(g_pnl_pct_pre, 2),
            "Post-Tax PnL ($)": round(g_pnl_post, 2),
            "Post-Tax PnL (%)": round(g_pnl_pct_post, 2),
            "Overall Win Rate (%)": round(overall_win_rate, 2),
        }

        for r_name in all_regime_names:
            if r_name in regime_win_map:
                w_val = regime_win_map[r_name]
                regime_win_cells.append(f"{w_val:>13.1f}%")
                row_export_dict[f"{r_name} Win %"] = round(w_val, 2)
            else:
                regime_win_cells.append("          N/A ")
                row_export_dict[f"{r_name} Win %"] = "N/A"

        row_export_dict.update({
            "Profit Factor": round(pf, 2),
            "Avg Sharpe": round(avg_sharpe, 2),
            "Avg Max Drawdown (%)": round(avg_dd, 2),
            "Avg Beta": round(avg_beta, 2),
            "Total Trades Executed": g_sum["total_trades"]
        })
        export_summary_rows.append(row_export_dict)

        regime_win_row_str = " | ".join(regime_win_cells)
        print(f"{name:<18} | ${g_pnl_pre:>11,.2f} | {g_pnl_pct_pre:>10.2f}% | ${g_pnl_post:>12,.2f} | {g_pnl_pct_post:>11.2f}% | {overall_win_rate:>9.1f}% | {regime_win_row_str} | {pf:>4.2f} | {avg_sharpe:>10.2f} | -{avg_dd:>9.2f}% | {avg_beta:>8.2f}")
        
    print("-" * 190 + "\n")
    return export_summary_rows

def save_and_export_data(enable_taxes, tax_rate, starting_cash, multi_strategy_results, export_summary_rows, master_trade_log, cache_dir):
    """Saves the Dashboard Pickle and dumps CSV logs."""
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
        print(f"📝 Full report saved for dashboard access: {report_path}")
    except Exception as e:
        print(f"⚠️ Failed to save summary report: {e}")

    if master_trade_log:
        print(f"💾 EXPORTING DATA TO CSV...")
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
        print(f"✅ Success! Your backtest results and raw trade logs have been saved to the folder: {out_dir}/")