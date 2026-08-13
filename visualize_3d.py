import pandas as pd
import plotly.express as px

# 1. Load the data
df = pd.read_csv("optuna_zscore_trials_log_train1.csv")

# 2. Clean the data
# Filter out the -999.0 penalty scores so they don't skew the color scale
df = df[df['value'] > -10].copy()

# Rename columns from Optuna's default export format to clean labels
df = df.rename(columns={
    'value': 'Fitness Score',
    'params_z_period': 'Z-Period',
    'params_entry_z_score': 'Entry Z-Score',
    'params_stop_distance': 'Stop Distance',
    'user_attrs_total_trades': 'Total Trades',
    'user_attrs_avg_dd_pct': 'Average DD (%)',
    'user_attrs_min_sharpe': 'Worst Regime Sharpe'
})

# Calculate the actual Stop Z-Score for the tooltip (Entry - Stop Distance)
df['Stop Z-Score'] = df['Entry Z-Score'] - df['Stop Distance']

# 3. Build the 3D Scatter Plot (Heatmap)
fig = px.scatter_3d(
    df,
    x='Z-Period',
    y='Entry Z-Score',
    z='Stop Z-Score',
    color='Fitness Score',
    color_continuous_scale='Turbo',  # Turbo provides a stark blue (cold) to red (hot) contrast
    title='Strategy Parameter Hotspots (Hover for Details)',
    hover_data=['Fitness Score', 'Total Trades', 'Average DD (%)', 'Worst Regime Sharpe']
)

# 4. Refine the visual layout
fig.update_traces(marker=dict(size=6, opacity=0.8))
fig.update_layout(
    scene=dict(
        xaxis_title='Z-Period (Lookback)',
        yaxis_title='Entry Z-Score',
        zaxis_title='Stop Z-Score'
    ),
    margin=dict(l=0, r=0, b=0, t=40)
)

# 5. Launch in browser
fig.show()