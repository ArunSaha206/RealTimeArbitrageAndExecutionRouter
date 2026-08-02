from datetime import timedelta

import numpy as np
import pandas as pd
import yfinance as yf


def calculate_max_drawdown(equity_curve):
    peak = equity_curve[0] if len(equity_curve) > 0 else 0
    max_dd_dollars = 0.0
    max_dd_pct = 0.0

    for val in equity_curve:
        if val > peak:
            peak = val
        dd = peak - val
        dd_pct = (dd / peak * 100) if peak > 0 else 0.0

        if dd > max_dd_dollars:
            max_dd_dollars = dd
        if dd_pct > max_dd_pct:
            max_dd_pct = dd_pct

    return max_dd_dollars, max_dd_pct

def calculate_sharpe_ratio(equity_curve, periods_per_year=19500, risk_free_rate=0.04):
    if len(equity_curve) < 2:
        return 0.0

    returns = np.diff(equity_curve) / equity_curve[:-1]
    returns = returns[~np.isnan(returns)]

    if len(returns) == 0 or np.std(returns) == 0:
        return 0.0

    rf_per_period = (1 + risk_free_rate)**(1 / periods_per_year) - 1
    excess_returns = returns - rf_per_period

    sharpe = np.mean(excess_returns) / np.std(excess_returns) * np.sqrt(periods_per_year)
    return float(sharpe)

def get_beta_and_alpha(strategy_daily_returns, benchmark_symbol="SPY", risk_free_rate_annual=0.04):
    if strategy_daily_returns.empty or len(strategy_daily_returns) < 3:
        return None

    strat_returns = strategy_daily_returns.copy()
    strat_returns.index = pd.to_datetime(strat_returns.index).tz_localize(None).normalize()

    min_date = strat_returns.index.min()
    max_date = strat_returns.index.max()

    start_date = (min_date - timedelta(days=3)).strftime('%Y-%m-%d')
    end_date = (max_date + timedelta(days=3)).strftime('%Y-%m-%d')

    try:
        bench_data = yf.download(benchmark_symbol, start=start_date, end=end_date, progress=False)
    except Exception:
        return None

    if bench_data.empty:
        return None

    if isinstance(bench_data.columns, pd.MultiIndex):
        if 'Close' in bench_data.columns.get_level_values(0):
            bench_close = bench_data['Close']
            if isinstance(bench_close, pd.DataFrame):
                bench_close = bench_close.iloc[:, 0]
        else:
            bench_close = bench_data.iloc[:, 0]
    else:
        if 'Close' in bench_data.columns:
            bench_close = bench_data['Close']
            if isinstance(bench_close, pd.DataFrame):
                bench_close = bench_close.iloc[:, 0]
        else:
            bench_close = bench_data.iloc[:, 0]

    bench_close = bench_close.squeeze()
    if not isinstance(bench_close, pd.Series):
        return None

    bench_close.index = pd.to_datetime(bench_close.index).tz_localize(None).normalize()
    bench_returns = bench_close.pct_change().dropna()

    aligned = pd.concat([strat_returns, bench_returns], axis=1, join='inner').dropna()
    aligned.columns = ['strategy', 'benchmark']

    if len(aligned) < 3:
        return None

    cov_matrix = np.cov(aligned['strategy'], aligned['benchmark'])
    covariance = cov_matrix[0, 1]
    benchmark_variance = cov_matrix[1, 1]
    beta = covariance / benchmark_variance if benchmark_variance != 0 else 1.0

    strat_period_return = (1 + aligned['strategy']).prod() - 1
    bench_period_return = (1 + aligned['benchmark']).prod() - 1

    aligned_min_date = aligned.index.min()
    aligned_max_date = aligned.index.max()
    num_days = max((aligned_max_date - aligned_min_date).days, 1)
    risk_free_period = (1 + risk_free_rate_annual) ** (num_days / 365.0) - 1

    expected_return = risk_free_period + beta * (bench_period_return - risk_free_period)
    alpha = strat_period_return - expected_return

    return {
        "beta": float(beta),
        "alpha_pct": float(alpha * 100),
        "strat_return_pct": float(strat_period_return * 100),
        "bench_return_pct": float(bench_period_return * 100)
    }

def generate_all_metrics(equity_curve, timestamps, trades, periods_per_year, starting_cash, benchmark_symbol="SPY"):
    """
    MASTER WRAPPER: Generates a standardized dictionary of metrics.
    Add any future metric here, and it will instantly populate across the UI and CSVs.
    """
    metrics = {}
    
    # 1. P&L Math
    final_balance = equity_curve[-1] if equity_curve else starting_cash
    net_pnl = final_balance - starting_cash
    metrics["Net P&L"] = f"${net_pnl:,.2f}"
    metrics["Return (%)"] = f"{(net_pnl / starting_cash * 100):+.2f}%"

    # 2. Drawdown & Risk
    _, max_dd_pct = calculate_max_drawdown(equity_curve)
    metrics["Max Drawdown"] = f"-{max_dd_pct:.2f}%"
    
    sharpe = calculate_sharpe_ratio(equity_curve, periods_per_year=periods_per_year)
    metrics["Sharpe Ratio"] = f"{sharpe:.2f}"

    # 3. Trade Stats
    winning_trades = [t for t in trades if t["pnl_dollars"] > 0]
    losing_trades = [t for t in trades if t["pnl_dollars"] < 0]
    win_rate = (len(winning_trades) / len(trades) * 100) if trades else 0.0
    
    gross_profit = sum(t["pnl_dollars"] for t in winning_trades)
    gross_loss = abs(sum(t["pnl_dollars"] for t in losing_trades))
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else (float('inf') if gross_profit > 0 else 0.0)

    metrics["Win Rate"] = f"{win_rate:.1f}%"
    metrics["Profit Factor"] = f"{profit_factor:.2f}"
    metrics["Total Trades"] = str(len(trades))

    # 4. Beta/Alpha (Requires converting equity curve to daily returns)
    if equity_curve and timestamps:
        df = pd.DataFrame({"datetime": timestamps, "equity": equity_curve})
        df['date'] = pd.to_datetime(df['datetime']).dt.date
        daily_returns = df.groupby('date')['equity'].last().pct_change().dropna()
        
        beta_metrics = get_beta_and_alpha(daily_returns, benchmark_symbol)
        if beta_metrics:
            metrics["Beta (vs SPY)"] = f"{beta_metrics['beta']:.2f}"
            metrics["Alpha"] = f"{beta_metrics['alpha_pct']:+.2f}%"
        else:
            metrics["Beta (vs SPY)"] = "N/A"
            metrics["Alpha"] = "N/A"
    
    return metrics