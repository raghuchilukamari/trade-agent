import pandas as pd
from sqlalchemy import create_engine, text
from datetime import datetime
import os
from dotenv import load_dotenv
import numpy as np

# --- CONFIGURATION ---
load_dotenv()
DB_URL = f"postgresql://{os.getenv('PG_USER')}:{os.getenv('PG_PASS')}@{os.getenv('POSTGRES_HOST')}:{os.getenv('POSTGRES_PORT')}/{os.getenv('POSTGRES_DB')}"
engine = create_engine(DB_URL)
SCHEMA = "dashboard"


def generate_strategic_audit():
    today = datetime.now().date()

    # 1. Fetch Data
    query_p = f"SELECT * FROM {SCHEMA}.portfolio_history WHERE run_date = '{today}'"
    df_p = pd.read_sql(query_p, engine)

    query_m = f"SELECT * FROM {SCHEMA}.universe_metrics_history WHERE run_date = '{today}'"
    df_m = pd.read_sql(query_m, engine)

    # 2. Fetch price returns to calculate Portfolio Volatility (Last 1Y)
    query_rets = """
        SELECT date, ticker, adj_close FROM ohlc_daily 
        WHERE date >= (SELECT MAX(date) FROM ohlc_daily) - INTERVAL '1 year'
    """
    df_prices = pd.read_sql(query_rets, engine)
    df_prices['date'] = pd.to_datetime(df_prices['date'])
    price_matrix = df_prices.pivot(index='date', columns='ticker', values='adj_close').ffill().pct_change().dropna()

    if df_p.empty:
        print("No portfolios found for today.")
        return

    print(f"\n{'=' * 85}")
    print(f"  EXECUTIVE RISK & MOMENTUM AUDIT: {today}")
    print(f"{'=' * 85}\n")

    strategies = ['HRP_1M', 'HRP_YTD', 'HRP_1Y']
    summary_data = []

    for strat in strategies:
        weights = df_p[df_p['strategy'] == strat].set_index('ticker')['weight']
        if weights.empty: continue

        # Intersection with metrics
        tickers = weights.index.intersection(df_m.set_index('ticker').index)
        w_final = weights.loc[tickers]
        m_final = df_m.set_index('ticker').loc[tickers]

        # --- PORTFOLIO METRICS ---
        # 1. Weighted Beta (Risk Sensitivity)
        port_beta = np.sum(w_final * m_final['beta_1y']) / np.sum(w_final)

        # 2. Weighted Alpha (Expected Edge)
        # We use the Alpha corresponding to the strategy's timeframe
        alpha_col = strat.lower().replace('hrp_', 'alpha_')
        port_alpha = np.sum(w_final * m_final[alpha_col]) / np.sum(w_final)

        # 3. Realized Volatility & Sharpe
        # Filter price matrix to just these stocks
        available_tickers = [t for t in tickers if t in price_matrix.columns]
        if available_tickers:
            port_rets = price_matrix[available_tickers].dot(w_final.loc[available_tickers])
            ann_vol = port_rets.std() * np.sqrt(252)
            # Sharpe = (Alpha / Vol) - simple version
            sharpe = port_alpha / ann_vol if ann_vol > 0 else 0
        else:
            ann_vol, sharpe = 0, 0

        summary_data.append({
            'Strategy': strat,
            'Beta': round(port_beta, 2),
            'Exp. Alpha': f"{round(port_alpha * 100, 2)}%",
            'Volatility': f"{round(ann_vol * 100, 2)}%",
            'Sharpe': round(sharpe, 2),
            'Positions': len(weights)
        })

    # Print Comparison Table
    summary_df = pd.DataFrame(summary_data)
    print(summary_df.to_string(index=False))

    # --- MANAGER'S INTERPRETATION ---
    print(f"\n{'-' * 30} MANAGER'S VERDICT {'-' * 30}")

    # Logic for Beta Analysis
    hrp_1m_beta = summary_data[0]['Beta']
    hrp_1y_beta = summary_data[2]['Beta']

    if hrp_1m_beta > hrp_1y_beta + 0.2:
        print("🚩 BETA EXPANSION: Your short-term portfolio is significantly more aggressive than your long-term core.")
        print("   The market is in a 'Risk-On' phase. Momentum is being driven by high-sensitivity stocks.")
    elif hrp_1m_beta < hrp_1y_beta - 0.2:
        print("🛡️ BETA COMPRESSION: Short-term leaders are more defensive than your long-term core.")
        print("   The market is hiding in 'Safe Havens'. This is often a bearish divergence.")
    else:
        print("⚖️ STABLE REGIME: Short-term and long-term risk profiles are aligned.")

    # Logic for Alpha Efficiency
    best_sharpe_strat = summary_df.loc[summary_df['Sharpe'].idxmax(), 'Strategy']
    print(f"💎 EFFICIENCY LEADER: {best_sharpe_strat} is providing the best 'Bang for your Buck' right now.")

    print(f"{'=' * 85}\n")

def run_momentum_audit():
    # 1. Get the most recent date available in the DB
    with engine.connect() as conn:
        latest_date = conn.execute(text(f"SELECT MAX(run_date) FROM {SCHEMA}.portfolio_history")).scalar()

    if not latest_date:
        print("Database is empty. Run the optimizer first.")
        return

    print(f"--- MOMENTUM AUDIT FOR: {latest_date} ---\n")

    # 2. Fetch Portfolios
    query_p = f"SELECT ticker, strategy FROM {SCHEMA}.portfolio_history WHERE run_date = '{latest_date}'"
    df_p = pd.read_sql(query_p, engine)

    # Organize into Sets for math
    s_1m = set(df_p[df_p['strategy'] == 'HRP_1M']['ticker'])
    s_ytd = set(df_p[df_p['strategy'] == 'HRP_YTD']['ticker'])
    s_1y = set(df_p[df_p['strategy'] == 'HRP_1Y']['ticker'])

    # 3. Fetch Metrics for Alpha Acceleration
    query_m = f"SELECT ticker, alpha_1m, alpha_ytd, alpha_1y FROM {SCHEMA}.universe_metrics_history WHERE run_date = '{latest_date}'"
    df_m = pd.read_sql(query_m, engine)

    # --- CATEGORY 1: NEW BREAKOUTS (The 3-Way Comparison) ---
    # Fresh Heat: In 1M, but NOT in YTD and NOT in 1Y
    fresh_heat = s_1m - (s_ytd | s_1y)

    # Established Momentum: In 1M AND YTD, but NOT in 1Y yet
    developing_trend = (s_1m & s_ytd) - s_1y

    # --- CATEGORY 2: FADING GIANTS ---
    # Structural losers: In 1Y, but dropped from 1M
    fading_giants = s_1y - s_1m

    # Serious Exit Warning: In 1Y, but dropped from BOTH 1M and YTD
    structural_collapse = s_1y - (s_1m | s_ytd)

    # --- CATEGORY 3: ALPHA ACCELERATORS ---
    df_m['momentum_score'] = df_m['alpha_1m'] - df_m['alpha_1y']
    top_accelerators = df_m.nlargest(10, 'momentum_score')

    # --- OUTPUT REPORT ---
    print("🚀 [NEW BREAKOUTS: FRESH HEAT]")
    print("Brand new leaders. Sizing should be small but these are the 'Early Birds'.")
    print(f"-> {', '.join(list(fresh_heat)[:15]) if fresh_heat else 'None'}\n")

    print("📈 [NEW BREAKOUTS: DEVELOPING TRENDS]")
    print("Stocks winning the 1M and YTD race. High conviction for momentum traders.")
    print(f"-> {', '.join(list(developing_trend)[:15]) if developing_trend else 'None'}\n")

    print("📉 [FADING GIANTS]")
    print("Long-term winners losing short-term steam. Consider trimming positions.")
    print(f"-> {', '.join(list(fading_giants)[:15]) if fading_giants else 'None'}\n")

    print("⚠️ [STRUCTURAL COLLAPSE]")
    print("In the 1Y portfolio but missing from 1M and YTD. High risk of trend reversal.")
    print(f"-> {', '.join(list(structural_collapse)[:15]) if structural_collapse else 'None'}\n")

    print("🔥 [TOP ALPHA ACCELERATORS]")
    print("Largest positive gaps between Monthly and Yearly Alpha:")
    for _, row in top_accelerators.iterrows():
        gap = row['alpha_1m'] - row['alpha_1y']
        print(f"   {row['ticker']}: +{gap:.2f} Alpha Boost (1M: {row['alpha_1m']:.2f} vs 1Y: {row['alpha_1y']:.2f})")


def find_next_leaders(engine, schema="dashboard"):
    today = datetime.now().date()

    # 1. Fetch metrics for the entire universe
    query = f"SELECT * FROM {schema}.universe_metrics_history WHERE run_date = '{today}'"
    df = pd.read_sql(query, engine)

    # 2. Fetch current portfolio to exclude stocks we already own
    query_p = f"SELECT ticker FROM {schema}.portfolio_history WHERE run_date = '{today}'"
    owned_tickers = pd.read_sql(query_p, engine)['ticker'].tolist()

    # --- PREDICTIVE FILTERS ---

    # A. The Accelerators: 1M Alpha is 2x better than 1Y Alpha
    # This captures the "sudden wake up"
    df['accel_factor'] = df['alpha_1m'] / (df['alpha_1y'].replace(0, 0.001))
    df['accel_factor'] = pd.to_numeric(df['accel_factor'], errors='coerce').fillna(0)
    accelerators = df[
        (~df['ticker'].isin(owned_tickers)) &
        (df['alpha_1m'] > 0.10) &  # Must have decent current alpha
        (df['alpha_1y'] < 0.05)  # But was 'boring' over the last year
        ].nlargest(10, 'accel_factor')

    # B. The Stealth Leaders: Low Beta but Rising Alpha
    # Finding low-risk stocks that are starting to outperform
    stealth = df[
        (~df['ticker'].isin(owned_tickers)) &
        (df['beta_1y'] < 0.7) &
        (df['alpha_1m'] > 0.05)
        ].nlargest(10, 'alpha_1m')

    print(f"\n{'=' * 60}")
    print(f"🕵️ THE INCUBATOR REPORT: SCOUTING NEXT LEADERS")
    print(f"{'=' * 60}")

    print("\n🚀 [ALPHAS WAKING UP]")
    print("Boring for a year, but sprinting in the last 30 days:")
    for _, row in accelerators.iterrows():
        print(f"   {row['ticker']}: 1M Alpha {row['alpha_1m']:.2f} (vs 1Y: {row['alpha_1y']:.2f})")

    print("\n🤫 [STEALTH ACCUMULATION]")
    print("Low-risk/Low-beta stocks showing unusual independent strength:")
    for _, row in stealth.iterrows():
        print(f"   {row['ticker']}: Beta {row['beta_1y']:.2f} | 1M Alpha {row['alpha_1m']:.2f}")

    print(f"\n{'=' * 60}\n")


def scout_breakouts(engine):
    today = datetime.now().date()
    # Pull metrics for stocks NOT already in our HRP portfolios
    query = f"""
        SELECT m.* FROM {SCHEMA}.universe_metrics_history m
        LEFT JOIN {SCHEMA}.portfolio_history p 
            ON m.ticker = p.ticker AND m.run_date = p.run_date
        WHERE m.run_date = '{today}' AND p.ticker IS NULL
    """
    potential_df = pd.read_sql(query, engine)

    # --- THE FORWARD-LOOKING FILTERS ---

    # 1. The Volume Breakout: Huge volume, Beta is still low
    # This is "Quiet Accumulation" turning into "Active Buying"
    volume_leads = potential_df[
        (potential_df['volume_z'] > 3.0) &
        (potential_df['alpha_1m'] > 0) &
        (potential_df['beta_1y'] < 1.2)
        ].sort_values('volume_z', ascending=False)

    # 2. The Accelerators: 1M Alpha is much higher than 1Y Alpha
    accel_leads = potential_df[
        (potential_df['alpha_1m'] > potential_df['alpha_1y'] + 0.2)
    ].sort_values('alpha_1m', ascending=False)

    print(f"\n{'=' * 70}")
    print(f"🕵️ NEXT LEADER SCOUT: {today}")
    print(f"{'=' * 70}")

    print("\n📦 [HIGH CONVICTION VOLUME BREAKOUTS]")
    print("Volume is >3 standard deviations above normal. Institutions are entering.")
    for _, row in volume_leads.head(10).iterrows():
        print(f"   {row['ticker']}: Vol Z-Score {row['volume_z']:.2f} | 1M Alpha {row['alpha_1m']:.2f}")

    print("\n⚡ [ALPHA ACCELERATION]")
    print("Stocks gaining speed. Short-term performance is eclipsing long-term trend.")
    for _, row in accel_leads.head(10).iterrows():
        print(f"   {row['ticker']}: 1M Alpha {row['alpha_1m']:.2f} (vs 1Y: {row['alpha_1y']:.2f})")


if __name__ == "__main__":
    find_next_leaders(engine)
    run_momentum_audit()
    generate_strategic_audit()
    scout_breakouts(engine)
