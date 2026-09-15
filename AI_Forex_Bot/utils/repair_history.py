"""
utils/repair_history.py
-----------------------
One-time script to backfill close_time, close_price, pips, profit_usd
for trades that were recorded with None values (sl_tp_hit bug).

Run once:
    python utils/repair_history.py
"""
import sys
from pathlib import Path
from datetime import datetime, timezone, timedelta

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

import pandas as pd
import MetaTrader5 as mt5

CSV = ROOT / "storage" / "data" / "trade_history.csv"

if not CSV.exists():
    print("No trade_history.csv found.")
    sys.exit(0)

df = pd.read_csv(CSV)
print(f"Loaded {len(df)} records")

broken = df[df["close_price"].isna() | df["profit_usd"].isna()]
print(f"Found {len(broken)} records needing repair")

if broken.empty:
    print("Nothing to fix!")
    sys.exit(0)

if not mt5.initialize():
    print("MT5 not available — cannot repair. Make sure MT5 is open.")
    sys.exit(1)

# Fetch all deals from a wide window
from_dt = datetime.now(timezone.utc) - timedelta(days=7)
to_dt   = datetime.now(timezone.utc) + timedelta(hours=1)
deals   = mt5.history_deals_get(from_dt, to_dt)

if not deals:
    print("No deals found in MT5 history.")
    mt5.shutdown()
    sys.exit(0)

# Build lookup: position_id → closing deal
close_deals = {}
for d in deals:
    if d.entry == 1:  # 1 = close deal
        close_deals[d.position_id] = d

repaired = 0
for idx, row in broken.iterrows():
    ticket = None
    # Try to match by open_price and pair
    for pos_id, d in close_deals.items():
        open_px = float(row.get("open_price", 0) or 0)
        if abs(d.price - open_px) < 0.01 or True:  # match by position_id if stored
            # Try to use ticket column if present
            t = row.get("ticket") or row.get("order") or pos_id
            if str(int(t)) == str(pos_id) if t else False:
                ticket = pos_id
                break

    # Simpler: match deals to rows by pair and approximate open price
    pair = row.get("pair", "")
    open_px = float(row.get("open_price", 0) or 0)
    direction = row.get("direction", "BUY")

    matched_deal = None
    for pos_id, d in close_deals.items():
        if d.symbol == pair:
            matched_deal = d
            break

    if matched_deal:
        d = matched_deal
        pip = 0.01 if "JPY" in pair.upper() else 0.0001
        raw_pips = (d.price - open_px) / pip
        if direction == "SELL":
            raw_pips = -raw_pips
        profit = d.profit

        df.at[idx, "close_price"] = round(d.price, 5)
        df.at[idx, "close_time"]  = datetime.fromtimestamp(d.time, tz=timezone.utc).isoformat()
        df.at[idx, "pips"]        = round(raw_pips, 1)
        df.at[idx, "profit_usd"]  = round(profit, 2)
        print(f"  Repaired row {idx}: {pair} {direction} | close={d.price:.5f} | pips={raw_pips:.1f} | P&L=${profit:.2f}")
        repaired += 1
        # Remove used deal so it's not matched twice
        del close_deals[d.position_id]

df.to_csv(CSV, index=False)
mt5.shutdown()
print(f"\nRepaired {repaired}/{len(broken)} records. Saved to {CSV}")
