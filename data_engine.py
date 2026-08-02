import os
import pandas as pd
import databento as db
import yfinance as yf

CACHE_DIR = "data_cache"
if not os.path.exists(CACHE_DIR):
    os.makedirs(CACHE_DIR)

def fetch_deep_history(symbol, resolution, start_date_str, end_date_str, provider="DATABENTO"):
    formatted_bars = []
    
    if provider == "DATABENTO":
        cache_file = os.path.join(CACHE_DIR, f"{symbol}_{start_date_str}_{end_date_str}_1m.parquet")
        
        if os.path.exists(cache_file):
            df = pd.read_parquet(cache_file)
        else:
            db_key = os.environ.get("DATABENTO_API_KEY")
            if not db_key:
                return []
                
            try:
                client = db.Historical(db_key)
                
                raw_data = client.timeseries.get_range(
                    dataset="XNAS.ITCH",
                    schema="ohlcv-1m",
                    symbols=symbol,
                    start=start_date_str,
                    end=end_date_str,
                )
                
                df = raw_data.to_df()
                
                if df.empty:
                    return []
                    
                df.to_parquet(cache_file)
                
            except Exception as e:
                return []

        if df.index.tz is None:
            df.index = df.index.tz_localize('UTC')

        resample_map = {
            "M1": "1min",
            "M5": "5min",
            "M15": "15min",
            "M30": "30min",
            "H1": "1h",
            "D1": "1D"
        }
        pd_resolution = resample_map.get(resolution.upper(), "1min")
        
        resampled_df = df.resample(pd_resolution).agg({
            'open': 'first',
            'high': 'max',
            'low': 'min',
            'close': 'last',
            'volume': 'sum'
        }).dropna()
        
        for dt, row in resampled_df.iterrows():
            formatted_bars.append({
                "datetime": dt.to_pydatetime(),
                "open": float(row['open']),
                "high": float(row['high']),
                "low": float(row['low']),
                "close": float(row['close']),
                "volume": float(row['volume'])
            })
            
    return formatted_bars

def fetch_vix_series(start_date_str, end_date_str):
    """Fetches daily VIX data to align with market backtest windows safely."""
    cache_file = os.path.join(CACHE_DIR, f"vix_series_{start_date_str}_{end_date_str}.parquet")
    if os.path.exists(cache_file):
        df = pd.read_parquet(cache_file)
        return df['Close'].to_dict()
    
    df = yf.download("^VIX", start=start_date_str, end=end_date_str, progress=False)
    if not df.empty:
        # Flatten columns if multi-index is returned by yfinance
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
            
        if 'Close' in df.columns:
            series = df['Close'].copy()
            
            # Explicitly force index to DatetimeIndex first, normalize, then convert to date objects
            dt_index = pd.to_datetime(series.index).normalize()
            series.index = [d.date() for d in dt_index]
            
            clean_df = pd.DataFrame({'Close': series})
            clean_df.to_parquet(cache_file)
            return series.to_dict()
            
    return {}