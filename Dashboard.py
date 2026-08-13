import os
import pickle
import pandas as pd
import numpy as np
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go

# -----------------------------------------------------------------------------
# PAGE CONFIG
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="Quant Execution Router",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

RESULTS_CACHE_DIR = "results_cache"
SUMMARY_REPORT_PATH = os.path.join(RESULTS_CACHE_DIR, "summary_report.pkl")

# -----------------------------------------------------------------------------
# FAST CACHED DATA LOADERS
# -----------------------------------------------------------------------------

@st.cache_resource(show_spinner="Loading cached backtest files into memory...")
def load_all_cached_results():
    if not os.path.exists(RESULTS_CACHE_DIR):
        return []

    latest_by_key = {} 

    for filename in os.listdir(RESULTS_CACHE_DIR):
        if not filename.endswith(".pkl") or filename == "summary_report.pkl":
            continue
        filepath = os.path.join(RESULTS_CACHE_DIR, filename)
        try:
            mtime = os.path.getmtime(filepath)
            with open(filepath, 'rb') as f:
                res = pickle.load(f)

            if "strategy_used" not in res:
                if res.get("trades"):
                    res["strategy_used"] = res["trades"][0].get("strategy_used", "Unknown")
                else:
                    res["strategy_used"] = "Unknown"

            if "regime_name" not in res or not res.get("regime_name"):
                res["regime_name"] = "unknown_regime"

            key = (res.get("symbol", "UNKNOWN_SYMBOL"), res["strategy_used"], res["regime_name"])

            if key not in latest_by_key or mtime > latest_by_key[key][0]:
                latest_by_key[key] = (mtime, res)

        except Exception as e:
            print(f"Failed to load {filename}: {e}")

    return [entry[1] for entry in latest_by_key.values()]


@st.cache_data(show_spinner="Aggregating portfolio equity curves...")
def compute_portfolio_metrics(_strat_data, strategy_name, regime_name, data_fingerprint):
    if not _strat_data:
        return None, None, 0.0, 0.0, 0, 0.0, []

    daily_series = []
    all_trades = []
    starting_cash = _strat_data[0]["equity_curve"][0] if _strat_data else 100000.0

    for r in _strat_data:
        all_trades.extend(r.get("trades", []))
        temp_df = pd.DataFrame({"datetime": r["timestamps"], "equity": r["equity_curve"]})
        temp_df['date'] = pd.to_datetime(temp_df['datetime']).dt.date

        daily_close = temp_df.groupby('date')['equity'].last()
        daily_series.append(daily_close)

    if not daily_series:
        return None, None, 0.0, 0.0, 0, 0.0, []

    port_df = pd.concat(daily_series, axis=1).ffill().fillna(starting_cash)
    daily_port_equity = port_df.sum(axis=1)

    running_max = daily_port_equity.cummax()
    drawdown_pct = ((daily_port_equity - running_max) / running_max) * 100

    total_start = len(_strat_data) * starting_cash
    total_end = daily_port_equity.iloc[-1]
    net_pnl = total_end - total_start
    net_pct = (net_pnl / total_start) * 100 if total_start > 0 else 0.0

    wins = len([t for t in all_trades if t['pnl_dollars'] > 0])
    win_rate = (wins / len(all_trades) * 100) if all_trades else 0.0

    return daily_port_equity, drawdown_pct, net_pnl, net_pct, len(all_trades), win_rate, all_trades


def get_report_mtime():
    return os.path.getmtime(SUMMARY_REPORT_PATH) if os.path.exists(SUMMARY_REPORT_PATH) else None


@st.cache_data(show_spinner="Loading full backtest report...")
def load_summary_report(report_mtime):
    if not os.path.exists(SUMMARY_REPORT_PATH):
        return None
    try:
        with open(SUMMARY_REPORT_PATH, "rb") as f:
            return pickle.load(f)
    except Exception:
        return None


# -----------------------------------------------------------------------------
# INITIAL DATA CHECK
# -----------------------------------------------------------------------------
raw_data = load_all_cached_results()

if not raw_data:
    st.title("📈 Quant Execution Router")
    st.warning(f"No cached results found in `{RESULTS_CACHE_DIR}/`. Run your `backtest.py` engine first.")
    st.stop()

tab_live, tab_report = st.tabs(["📈 Live Explorer", "📋 Full Backtest Report"])

# =============================================================================
# TAB 1: LIVE EXPLORER
# =============================================================================
with tab_live:
    st.sidebar.title("Control Room")

    available_strategies = sorted(list(set([r.get("strategy_used", "Unknown") for r in raw_data])))
    selected_strategy = st.sidebar.selectbox("Select Strategy", available_strategies)

    strat_data_all_regimes = [r for r in raw_data if r.get("strategy_used", "Unknown") == selected_strategy]

    available_regimes = sorted(list(set([r.get("regime_name", "unknown_regime") for r in strat_data_all_regimes])))
    selected_regime = st.sidebar.selectbox("Select Regime", available_regimes)

    strat_data = [r for r in strat_data_all_regimes if r.get("regime_name", "unknown_regime") == selected_regime]

    available_tickers = sorted(list(set([r["symbol"] for r in strat_data])))
    selected_ticker = st.sidebar.selectbox("Select Ticker View", ["All Portfolio (Aggregated)"] + available_tickers)

    st.sidebar.caption(f"{len(raw_data)} unique symbol/strategy/regime results loaded from cache.")

    st.title(f"Strategy: {selected_strategy}")
    st.caption(f"Regime: {selected_regime}")

    if selected_ticker == "All Portfolio (Aggregated)":
        st.subheader("Portfolio Equity & Risk Metrics")

        fingerprint = (len(strat_data), sum(len(r.get("trades", [])) for r in strat_data))

        daily_equity, drawdown_pct, net_pnl, net_pct, total_trades, win_rate, all_trades = compute_portfolio_metrics(
            _strat_data=strat_data, strategy_name=selected_strategy, regime_name=selected_regime, data_fingerprint=fingerprint
        )

        if daily_equity is not None:
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Net Portfolio P&L", f"${net_pnl:,.2f}", f"{net_pct:+.2f}%")
            col2.metric("Total Trades Executed", f"{total_trades:,}")
            col3.metric("Overall Win Rate", f"{win_rate:.1f}%")
            col4.metric("Max Portfolio Drawdown", f"{drawdown_pct.min():.2f}%", delta_color="inverse")

            st.markdown("---")

            fig_eq = go.Figure()
            fig_eq.add_trace(go.Scatter(
                x=daily_equity.index, y=daily_equity.values, mode='lines', name='Portfolio Value', line=dict(color='#00E676', width=2)
            ))
            fig_eq.update_layout(
                title=f"Portfolio Cumulative Growth — {selected_regime}", height=350, template="plotly_dark",
                margin=dict(l=20, r=20, t=40, b=20), hovermode="x unified"
            )
            st.plotly_chart(fig_eq, use_container_width=True)

            fig_dd = go.Figure()
            fig_dd.add_trace(go.Scatter(
                x=drawdown_pct.index, y=drawdown_pct.values, fill='tozeroy', mode='lines', name='Drawdown %', line=dict(color='#FF5252', width=1)
            ))
            fig_dd.update_layout(
                title="Portfolio Underwater Drawdown Profile (%)", height=220, template="plotly_dark",
                margin=dict(l=20, r=20, t=40, b=20), hovermode="x unified"
            )
            st.plotly_chart(fig_dd, use_container_width=True)
        else:
            st.info("No portfolio data available for this strategy/regime.")

    else:
        st.subheader(f"Ticker Deep Dive: {selected_ticker}")
        t_data = next((r for r in strat_data if r["symbol"] == selected_ticker), None)

        if t_data:
            ticker_metrics = t_data.get("metrics", {})
            if ticker_metrics:
                cols = st.columns(len(ticker_metrics))
                for idx, (metric_name, metric_value) in enumerate(ticker_metrics.items()):
                    delta_color = "inverse" if "Drawdown" in metric_name else "normal"
                    cols[idx].metric(metric_name, metric_value, delta_color=delta_color)

            st.markdown("---")

            eq_df = pd.DataFrame({"Time": t_data["timestamps"], "Equity": t_data["equity_curve"]})
            fig = px.line(eq_df, x="Time", y="Equity", title=f"{selected_ticker} Strategy Equity Curve", template="plotly_dark")
            fig.update_traces(line_color='#00E676')
            fig.update_layout(height=350)
            st.plotly_chart(fig, use_container_width=True)

            st.markdown("### Trade Logs")
            if t_data["trades"]:
                trades_df = pd.DataFrame(t_data["trades"])
                display_df = trades_df[['entry_time', 'exit_time', 'entry_price', 'exit_price', 'pnl_dollars', 'pnl_pct', 'bars_held']].copy()
                display_df.columns = ['Entry Time', 'Exit Time', 'Entry ($)', 'Exit ($)', 'P&L ($)', 'P&L (%)', 'Bars Held']

                st.dataframe(
                    display_df.style.format({
                        'Entry ($)': '${:.2f}', 'Exit ($)': '${:.2f}', 'P&L ($)': '${:+.2f}', 'P&L (%)': '{:+.2f}%'
                    }),
                    use_container_width=True, height=300
                )
            else:
                st.info("No trades executed for this ticker.")
        else:
            st.warning(f"No cached result found for {selected_ticker}.")

# =============================================================================
# TAB 2: FULL BACKTEST REPORT 
# =============================================================================
with tab_report:
    report_mtime = get_report_mtime()

    if report_mtime is None:
        st.info("No full report found yet. Run `backtest.py` to generate `results_cache/summary_report.pkl`.")
    else:
        report = load_summary_report(report_mtime)

        if not report:
            st.warning("Report file exists but could not be loaded.")
        else:
            st.title("📋 Full Backtest Report")
            st.caption(f"Generated: {report['generated_at']}")

            tax_note = f"{int(report['tax_rate'] * 100)}% Federal Ordinary Income" if report["enable_taxes"] else "Disabled"
            st.caption(f"Starting cash/ticker: ${report['starting_cash_per_ticker']:,.2f} | Taxes: {tax_note}")

            for strat in report["strategies"]:
                g = strat["global_summary"]
                if g["total_symbols_evaluated"] == 0:
                    continue

                st.markdown(f"## {strat['name']}")

                g_pnl_pre = g["total_ending_capital_pre_tax"] - g["total_initial_capital"]
                g_pnl_post = g["total_ending_capital_post_tax"] - g["total_initial_capital"]
                g_pnl_pct_pre = (g_pnl_pre / g["total_initial_capital"] * 100) if g["total_initial_capital"] > 0 else 0.0
                g_pnl_pct_post = (g_pnl_post / g["total_initial_capital"] * 100) if g["total_initial_capital"] > 0 else 0.0
                global_win_rate = (g["total_wins"] / g["total_trades"] * 100) if g["total_trades"] > 0 else 0.0
                global_pf = (g["total_gross_profit"] / g["total_gross_loss"]) if g["total_gross_loss"] > 0 else 0.0
                
                true_sharpe = g.get("true_global_sharpe", 0.0)
                true_dd = g.get("true_global_max_dd_pct", 0.0)

                c1, c2, c3, c4 = st.columns(4)
                c1.metric("Global Post-Tax P&L", f"${g_pnl_post:,.2f}", f"{g_pnl_pct_post:+.2f}%")
                c2.metric("Global Win Rate", f"{global_win_rate:.1f}%")
                c3.metric("Global Profit Factor", f"{global_pf:.2f}")
                c4.metric("True Global Sharpe", f"{true_sharpe:.2f}", f"-{true_dd:.2f}% DD", delta_color="inverse")

                regime_rows = []
                for rs in g["regime_summaries"]:
                    regime_rows.append({
                        "Regime": rs["name"],
                        "Pre-Tax P&L ($)": rs["pre_tax_pnl"],
                        "Pre-Tax (%)": rs["pre_tax_pnl_pct"],
                        "Tax Impact ($)": rs["tax_impact"],
                        "Post-Tax P&L ($)": rs["post_tax_pnl"],
                        "Post-Tax (%)": rs["post_tax_pnl_pct"],
                        "B&H (%)": rs["bh_pct"],
                        "Trades": rs["trades"],
                        "Win %": rs["win_rate"],
                        "PF": rs["pf"],
                        "Sharpe": rs["sharpe"],
                        "Max DD (%)": rs["max_dd_pct"],
                        "Beta": rs["beta"],
                        "Alpha (%)": rs["alpha"],
                    })

                if regime_rows:
                    regime_df = pd.DataFrame(regime_rows).set_index("Regime")
                    st.dataframe(
                        regime_df.style.format({
                            "Pre-Tax P&L ($)": "${:,.2f}", "Pre-Tax (%)": "{:+.2f}%", "Tax Impact ($)": "${:,.2f}",
                            "Post-Tax P&L ($)": "${:,.2f}", "Post-Tax (%)": "{:+.2f}%", "B&H (%)": "{:+.2f}%",
                            "Win %": "{:.1f}%", "PF": "{:.2f}", "Sharpe": "{:.2f}", "Max DD (%)": "-{:.2f}%",
                            "Beta": "{:.2f}", "Alpha (%)": "{:+.2f}%",
                        }, na_rep="N/A"),
                        use_container_width=True
                    )

                for rs in g["regime_summaries"]:
                    mc = rs.get("monte_carlo")
                    if not mc:
                        continue
                    with st.expander(f"🎲 Monte Carlo Stress Test — {rs['name']} ({mc['num_simulations']:,} sims)"):
                        m1, m2, m3 = st.columns(3)
                        m1.metric("Win Probability", f"{mc['prob_profitable']:.1f}%")
                        m2.metric("Prob. Beat Tickers B&H", f"{mc['prob_beat_bh']:.1f}%", f"vs {mc['avg_buy_hold_pct']:+.2f}%")
                        if mc["prob_beat_spy"] is not None:
                            m3.metric("Prob. Beat SPY", f"{mc['prob_beat_spy']:.1f}%", f"vs {mc['spy_return_pct']:+.2f}%")
                        else:
                            m3.metric("Prob. Beat SPY", "N/A")

                        st.markdown(f"**Risk of Ruin (≥{mc['ruin_threshold_pct']:.0f}% Drawdown):** {mc['risk_of_ruin']:.1f}%")

                        pct = mc["percentiles"]
                        cap = mc["starting_capital"]
                        pct_df = pd.DataFrame({
                            "Percentile": ["95th (Optimistic)", "75th", "50th (Median)", "25th", "5th (Pessimistic)"],
                            "Ending Balance ($)": [pct["p95"], pct["p75"], pct["p50"], pct["p25"], pct["p5"]],
                            "Return (%)": [
                                (pct["p95"] - cap) / cap * 100, (pct["p75"] - cap) / cap * 100,
                                (pct["p50"] - cap) / cap * 100, (pct["p25"] - cap) / cap * 100, (pct["p5"] - cap) / cap * 100,
                            ]
                        }).set_index("Percentile")
                        st.dataframe(pct_df.style.format({"Ending Balance ($)": "${:,.2f}", "Return (%)": "{:+.2f}%"}), use_container_width=True)

                        dd = mc["drawdown_percentiles"]
                        streak = mc["streak_percentiles"]
                        st.caption(f"Median drawdown: -{dd['p50']:.2f}% | 95th %ile: -{dd['p95']:.2f}% — Median loss streak: {streak['p50']} | 95th %ile: {streak['p95']}")

                st.markdown("---")

            if report.get("comparison_matrix"):
                st.markdown("## 🏆 Transposed Strategy Comparison Matrix")
                
                comp_df = pd.DataFrame(report["comparison_matrix"]).set_index("Metric")
                st.dataframe(comp_df, use_container_width=True)
                
                st.markdown("### Visual Analytics")
                col1, col2 = st.columns(2)

                def clean_for_chart(val):
                    if isinstance(val, str):
                        val = val.replace("$", "").replace("%", "").replace(",", "").replace("+", "")
                    try:
                        return float(val)
                    except:
                        return 0.0
                
                with col1:
                    st.write("**Profit Factor vs Friction**")
                    if "Profit Factor" in comp_df.index:
                        pf_series = comp_df.loc["Profit Factor"].apply(clean_for_chart)
                        st.bar_chart(pf_series)
                    
                with col2:
                    st.write("**True Global Sharpe vs Friction**")
                    if "True Global Sharpe" in comp_df.index:
                        sharpe_series = comp_df.loc["True Global Sharpe"].apply(clean_for_chart)
                        st.bar_chart(sharpe_series)