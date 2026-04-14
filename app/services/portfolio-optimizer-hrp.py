"""
Hierarchical Risk Parity (HRP) Portfolio Optimizer and Alpha/Beta Metrics Pipeline.

This module automates the daily extraction of market data, calculation of key risk/reward
metrics (Alpha, Beta, Volume Z-Scores) across multiple time horizons (1-Month, YTD, 1-Year),
and the generation of optimized portfolio allocations using Hierarchical Risk Parity (HRP).

Unlike traditional Mean-Variance Optimization (Markowitz) which relies on fragile covariance
matrix inversions, HRP uses machine learning (graph theory and hierarchical clustering) to group
correlated assets and allocate weights. This results in highly diversified, mathematically
robust portfolios that are more resilient to out-of-sample market shocks.

The script performs the following core steps:
    1. Fetches historical adjusted closes and volumes from a PostgreSQL database (`ohlc_daily`).
    2. Calculates rolling Alpha and Beta against the SPY benchmark, alongside volume anomalies.
    3. Filters the universe for positive Alpha and high liquidity to create a candidate pool.
    4. Runs the HRP optimization algorithm on the candidate pool for 3 separate strategies.
    5. Upserts the metrics and final portfolio weights into PostgreSQL for downstream dashboarding.
"""

import numpy as np
import pandas as pd
from scipy import stats
from dotenv import load_dotenv
import os
from sqlalchemy import create_engine, text
from sqlalchemy.dialects.postgresql import insert
from pypfopt import hierarchical_portfolio
from datetime import datetime

# ==========================================
# 1. DATABASE & LOGGING SETUP
# ==========================================
load_dotenv()
DB_URL = f"postgresql://{os.getenv('PG_USER')}:{os.getenv('PG_PASS')}@{os.getenv('POSTGRES_HOST')}:{os.getenv('POSTGRES_PORT')}/{os.getenv('POSTGRES_DB')}"
engine = create_engine(DB_URL)
SCHEMA = "dashboard"


def init_tables():
    """Initializes the table with the full suite of Alpha, Beta, and Volume metrics."""
    queries = [
        f"CREATE SCHEMA IF NOT EXISTS {SCHEMA};",
        f"""CREATE TABLE IF NOT EXISTS {SCHEMA}.universe_metrics_history (
            run_date DATE, 
            ticker VARCHAR(10), 
            alpha_1m FLOAT, beta_1m FLOAT,
            alpha_ytd FLOAT, beta_ytd FLOAT,
            alpha_1y FLOAT, beta_1y FLOAT, 
            avg_vol_1m FLOAT,
            volume_z FLOAT,
            PRIMARY KEY (run_date, ticker));""",
        f"""CREATE TABLE IF NOT EXISTS {SCHEMA}.portfolio_history (
            run_date DATE, 
            ticker VARCHAR(10), 
            weight FLOAT, 
            strategy VARCHAR(15),
            PRIMARY KEY (run_date, ticker, strategy));"""
    ]
    with engine.connect() as conn:
        for q in queries:
            conn.execute(text(q))
        conn.commit()


# ==========================================
# 2. THE UPSERT ENGINE
# ==========================================
def upsert_df(df, table_name, engine, schema, conflict_cols):
    def method(table, conn, keys, data_iter):
        data = [dict(zip(keys, row)) for row in data_iter]
        stmt = insert(table.table).values(data)
        update_cols = {c.name: c for c in stmt.excluded if c.name not in conflict_cols}
        upsert_stmt = stmt.on_conflict_do_update(index_elements=conflict_cols, set_=update_cols)
        conn.execute(upsert_stmt)

    df.to_sql(table_name, engine, schema=schema, if_exists='append', index=False, method=method)


# ==========================================
# 3. THE MASTER PIPELINE
# ==========================================
def run_daily_pipeline():
    init_tables()
    today = datetime.now().date()
    start_of_year = datetime(today.year, 1, 1).date()

    print("1. Fetching universe data...")
    raw_df = pd.read_sql("SELECT date, ticker, adj_close, volume FROM ohlc_daily ORDER BY date ASC", engine)
    raw_df['date'] = pd.to_datetime(raw_df['date'])

    price_matrix = raw_df.pivot(index='date', columns='ticker', values='adj_close')
    price_matrix = price_matrix.dropna(thresh=int(len(price_matrix) * 0.70), axis=1).ffill().dropna()
    all_rets = price_matrix.pct_change().dropna()

    spy_rets = all_rets['SPY']
    stock_rets = all_rets.drop(columns=['SPY'])

    # 2. Calculate All Metrics
    print("2. Calculating Alpha/Beta/Volume Conviction...")
    metrics = []
    ytd_mask = spy_rets.index.date >= start_of_year

    # Pre-calculate Volume Stats for Z-Score
    vol_stats = raw_df.groupby('ticker')['volume'].apply(lambda x: {
        'current': x.iloc[-1],
        'mean': x.iloc[-21:].mean(),
        'std': x.iloc[-21:].std()
    }).unstack()

    for t in stock_rets.columns:
        # Long-term (1Y)
        slope_y, inter_y, _, _, _ = stats.linregress(spy_rets.iloc[-252:].values, stock_rets[t].iloc[-252:].values)
        # Short-term (1M)
        slope_m, inter_m, _, _, _ = stats.linregress(spy_rets.iloc[-21:].values, stock_rets[t].iloc[-21:].values)
        # YTD
        if np.sum(ytd_mask) > 5:
            slope_ytd, inter_ytd, _, _, _ = stats.linregress(spy_rets[ytd_mask].values, stock_rets[t][ytd_mask].values)
            alpha_ytd, beta_ytd = inter_ytd * 252, slope_ytd
        else:
            alpha_ytd, beta_ytd = 0.0, 0.0

        # Volume Z-Score
        v_curr, v_mean, v_std = vol_stats.loc[t, 'current'], vol_stats.loc[t, 'mean'], vol_stats.loc[t, 'std']
        z_score = (v_curr - v_mean) / v_std if v_std > 0 else 0

        metrics.append({
            'run_date': today, 'ticker': t,
            'alpha_1m': round(inter_m * 252, 4), 'beta_1m': round(slope_m, 3),
            'alpha_ytd': round(alpha_ytd, 4), 'beta_ytd': round(beta_ytd, 3),
            'alpha_1y': round(inter_y * 252, 4), 'beta_1y': round(slope_y, 3),
            'avg_vol_1m': round(v_mean, 2),
            'volume_z': round(z_score, 2)
        })

    metrics_df = pd.DataFrame(metrics)
    upsert_df(metrics_df, 'universe_metrics_history', engine, SCHEMA, ['run_date', 'ticker'])

    # 3. Build Portfolios
    horizons = {'HRP_1M': 'alpha_1m', 'HRP_YTD': 'alpha_ytd', 'HRP_1Y': 'alpha_1y'}
    for strategy_name, alpha_col in horizons.items():
        elite_tickers = metrics_df[metrics_df[alpha_col] > 0].nlargest(500, 'avg_vol_1m')['ticker'].tolist()
        if not elite_tickers: continue

        hrp = hierarchical_portfolio.HRPOpt(stock_rets[elite_tickers].iloc[-252:])
        hrp.optimize()
        clean_w = pd.Series(hrp.clean_weights()).reset_index()
        clean_w.columns = ['ticker', 'weight']
        clean_w = clean_w[clean_w['weight'] > 0.005].copy()
        clean_w['run_date'], clean_w['strategy'] = today, strategy_name
        upsert_df(clean_w, 'portfolio_history', engine, SCHEMA, ['run_date', 'ticker', 'strategy'])

    print(f"\n✅ SUCCESS: Full Alpha/Beta/Volume metrics and 3 Portfolios stored for {today}.")


if __name__ == "__main__":
    run_daily_pipeline()