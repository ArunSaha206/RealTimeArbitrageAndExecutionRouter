import numpy as np

def run_monte_carlo_simulation(all_trades, starting_capital, avg_buy_hold_pct=0.0, spy_return_pct=None, num_simulations=1000, ruin_threshold_pct=20.0, title="ADVANCED MONTE CARLO STRESS TEST"):
    """
    Runs the vectorized Monte Carlo stress test AND returns its computed
    stats as a dict, so callers (like the dashboard report) can persist
    the results instead of them only living in the terminal print-out.
    """
    if not all_trades:
        print("⚠️ No trades available for Monte Carlo simulation.")
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

    print("\n" + "=" * 115)
    print(f"                            {title} ({num_simulations:,} Iterations)           ")
    print("=" * 115)
    print(f" 🎯 Overall Win Probability:     {prob_profitable:.1f}% of outcomes ended in net profit")
    print(f" 📈 Prob. of Beating Tickers B&H: {prob_beat_bh:.1f}% (vs Avg B&H: {avg_buy_hold_pct:+.2f}%)")
    if prob_beat_spy is not None:
        print(f" 🏆 Prob. of Beating SPY:         {prob_beat_spy:.1f}% (vs SPY: {spy_return_pct:+.2f}%)")
    else:
        print(f" 🏆 Prob. of Beating SPY:         N/A (SPY data unavailable)")
    print(f" ⚠️ Risk of Ruin (≥{ruin_threshold_pct:.0f}% Drawdown): {risk_of_ruin:.1f}% chance of hitting account distress")
    print("-" * 115)
    print(" 📊 EXPECTED RETURN DISTRIBUTION (Pre-Tax basis for probabilistic modeling):")
    print(f"    • 95th Percentile (Optimistic): ${p95_final:,.2f}  (+{(p95_final-starting_capital)/starting_capital*100:+.2f}%)")
    print(f"    • 75th Percentile:              ${p75_final:,.2f}  (+{(p75_final-starting_capital)/starting_capital*100:+.2f}%)")
    print(f"    • 50th Percentile (Median):     ${p50_final:,.2f}  (+{(p50_final-starting_capital)/starting_capital*100:+.2f}%)")
    print(f"    • 25th Percentile:              ${p25_final:,.2f}  (+{(p25_final-starting_capital)/starting_capital*100:+.2f}%)")
    print(f"    • 5th Percentile  (Pessimistic): ${p5_final:,.2f}  (+{(p5_final-starting_capital)/starting_capital*100:+.2f}%)")
    print("-" * 115)
    print(" 📉 RISK & STREAK METRICS:")
    print(f"    • Median Drawdown vs. 95% Worst Case:   -{p50_dd:.2f}%  |  95th %ile: -{p95_dd:.2f}%")
    print(f"    • Median Loss Streak vs. 95% Worst Case: {p50_streak} losses in a row  |  95th %ile: {p95_streak} in a row")
    print("=" * 115 + "\n")

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