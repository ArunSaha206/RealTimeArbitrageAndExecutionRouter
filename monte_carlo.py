import numpy as np
from rich.panel import Panel
from rich.text import Text
from console_theme import console

def run_monte_carlo_simulation(all_trades, starting_capital, avg_buy_hold_pct=0.0, spy_return_pct=None, num_simulations=1000, ruin_threshold_pct=20.0, title="ADVANCED MONTE CARLO STRESS TEST"):
    """
    Runs the vectorized Monte Carlo stress test AND returns its computed
    stats as a dict, so callers (like the dashboard report) can persist
    the results instead of them only living in the terminal print-out.
    """
    if not all_trades:
        console.print("[warning]⚠️ No trades available for Monte Carlo simulation.[/warning]")
        return None

    trade_pnl_dollars = np.array([t["pnl_dollars"] for t in all_trades])
    num_trades = len(trade_pnl_dollars)

    simulated_pnl = np.random.choice(trade_pnl_dollars, size=(num_simulations, num_trades), replace=True)
    equity_curves = starting_capital + np.cumsum(simulated_pnl, axis=1)
    
    final_balances = equity_curves[:, -1]
    running_max = np.maximum.accumulate(equity_curves, axis=1)
    running_max = np.maximum(starting_capital, running_max)
    
    drawdowns = (running_max - equity_curves) / running_max * 100
    max_drawdowns_pct = np.max(drawdowns, axis=1)
    
    hit_ruin = max_drawdowns_pct >= ruin_threshold_pct
    ruin_count = np.sum(hit_ruin)
    
    sim_return_pct = ((final_balances - starting_capital) / starting_capital) * 100
    
    beat_bh_count = np.sum(sim_return_pct > avg_buy_hold_pct)
    beat_spy_count = np.sum(sim_return_pct > spy_return_pct) if spy_return_pct is not None else None
    
    is_loss = simulated_pnl < 0
    max_streaks = np.zeros(num_simulations, dtype=int)
    for i in range(num_simulations):
        streak = 0
        max_s = 0
        for val in is_loss[i]:
            if val:
                streak += 1
                if streak > max_s:
                    max_s = streak
            else:
                streak = 0
        max_streaks[i] = max_s

    pnl_array = final_balances - starting_capital
    prob_profitable = (np.sum(pnl_array > 0) / num_simulations) * 100
    prob_beat_bh = (beat_bh_count / num_simulations) * 100
    prob_beat_spy = (beat_spy_count / num_simulations) * 100 if beat_spy_count is not None else None
    risk_of_ruin = (ruin_count / num_simulations) * 100

    p5_final = np.percentile(final_balances, 5)
    p25_final = np.percentile(final_balances, 25)
    p50_final = np.percentile(final_balances, 50)
    p75_final = np.percentile(final_balances, 75)
    p95_final = np.percentile(final_balances, 95)
    p50_dd = np.percentile(max_drawdowns_pct, 50)
    p95_dd = np.percentile(max_drawdowns_pct, 95)
    p50_streak = int(np.percentile(max_streaks, 50))
    p95_streak = int(np.percentile(max_streaks, 95))

    # =====================================================================
    # NEW RICH UI FORMATTING
    # =====================================================================
    text = Text()
    
    text.append("\n")
    text.append(f"🎯 Overall Win Prob:                 {prob_profitable:.1f}% of outcomes ended in net profit\n")
    
    text.append(f"📈 Prob of Beating Avg Buy & Hold:   {prob_beat_bh:.1f}% (vs Avg B&H: ")
    text.append(f"{avg_buy_hold_pct:+.2f}%", style="gain" if avg_buy_hold_pct >= 0 else "loss")
    text.append(")\n")
    
    if prob_beat_spy is not None:
        text.append(f"🏆 Prob of Beating SPY:              {prob_beat_spy:.1f}% (vs SPY: ")
        text.append(f"{spy_return_pct:+.2f}%", style="gain" if spy_return_pct >= 0 else "loss")
        text.append(")\n")
    else:
        text.append(f"🏆 Prob of Beating SPY:              N/A (SPY data unavailable)\n", style="muted")
        
    # Unhighlighted risk of ruin text label, colored metric
    text.append(f"❗ Risk of Ruin (≥{ruin_threshold_pct:.0f}% DD):           ")
    text.append(f"{risk_of_ruin:.1f}% chance of hitting account distress\n\n")
    
    text.append("📊 Return Percentile Distribution (Pre-Tax):\n", style="bold")
    
    val95 = f"${p95_final:,.2f}"
    val75 = f"${p75_final:,.2f}"
    val50 = f"${p50_final:,.2f}"
    val25 = f"${p25_final:,.2f}"
    val5 = f"${p5_final:,.2f}"

    pct95 = (p95_final - starting_capital) / starting_capital * 100
    pct75 = (p75_final - starting_capital) / starting_capital * 100
    pct50 = (p50_final - starting_capital) / starting_capital * 100
    pct25 = (p25_final - starting_capital) / starting_capital * 100
    pct5 = (p5_final - starting_capital) / starting_capital * 100

    text.append(f"   • 95th:       {val95:>11}  (")
    text.append(f"{pct95:+.2f}%", style="gain" if pct95 >= 0 else "loss")
    text.append(")\n")
    
    text.append(f"   • 75th:       {val75:>11}  (")
    text.append(f"{pct75:+.2f}%", style="gain" if pct75 >= 0 else "loss")
    text.append(")\n")
    
    text.append(f"   • 50th:       {val50:>11}  (")
    text.append(f"{pct50:+.2f}%", style="gain" if pct50 >= 0 else "loss")
    text.append(")\n")
    
    text.append(f"   • 25th:       {val25:>11}  (")
    text.append(f"{pct25:+.2f}%", style="gain" if pct25 >= 0 else "loss")
    text.append(")\n")
    
    text.append(f"   •  5th:       {val5:>11}  (")
    text.append(f"{pct5:+.2f}%", style="gain" if pct5 >= 0 else "loss")
    text.append(")\n\n")

    text.append("📉 Risk & Streak Metrics:\n", style="bold")
    
    text.append("   • Median  |  95th Percentile Drawdown:       ")
    text.append(f"-{p50_dd:.2f}%".rjust(11), style="loss")
    text.append("  |  ")
    text.append(f"-{p95_dd:.2f}%\n", style="loss")
    
    text.append("   • Median  |  95th Percentile Loss Streak:    ")
    text.append(f"{p50_streak} in a row".rjust(11))
    text.append(f"  |  {p95_streak} in a row\n")

    panel = Panel(text, title=f"{title} ({num_simulations:,} Iterations)", border_style="white", expand=False)
    console.print()
    console.print(panel)
    console.print()
    # =====================================================================

    return {
        "title": title,
        "num_simulations": num_simulations,
        "prob_profitable": float(prob_profitable),
        "prob_beat_bh": float(prob_beat_bh),
        "avg_buy_hold_pct": float(avg_buy_hold_pct),
        "prob_beat_spy": float(prob_beat_spy) if prob_beat_spy is not None else None,
        "spy_return_pct": float(spy_return_pct) if spy_return_pct is not None else None,
        "risk_of_ruin": float(risk_of_ruin),
        "ruin_threshold_pct": float(ruin_threshold_pct),
        "starting_capital": float(starting_capital),
        "percentiles": {
            "p5": float(p5_final), "p25": float(p25_final), "p50": float(p50_final),
            "p75": float(p75_final), "p95": float(p95_final),
        },
        "drawdown_percentiles": {"p50": float(p50_dd), "p95": float(p95_dd)},
        "streak_percentiles": {"p50": p50_streak, "p95": p95_streak},
    }