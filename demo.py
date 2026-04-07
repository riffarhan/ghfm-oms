"""
GHFM OMS — End-to-End Demo
===========================
Demonstrates the full order lifecycle, risk management, and reporting.

Usage:
    1. Start the server:  uvicorn oms.main:app --reload
    2. Run this script:   python demo.py
"""

import asyncio
import json
import sys

import httpx

BASE = "http://localhost:8000"
DIVIDER = "=" * 70
SECTION = "-" * 50


def pprint(data):
    print(json.dumps(data, indent=2, default=str))


def print_order(o):
    status = o["status"]
    color = {"FILLED": "\033[92m", "REJECTED": "\033[91m", "CANCELLED": "\033[90m"}.get(status, "\033[94m")
    reset = "\033[0m"
    print(f"  {o['client_order_id']}  {o['symbol']:>8}  {o['side']:>4}  {o['order_type']:>6}  "
          f"qty={float(o['quantity']):>10,.0f}  "
          f"filled={float(o['filled_quantity']):>10,.0f}  "
          f"avg_px={float(o['average_price']):>10,.2f}  "
          f"{color}{status}{reset}")


def print_position(p):
    upnl = float(p["unrealized_pnl"])
    rpnl = float(p["realized_pnl"])
    mv = float(p["quantity"]) * float(p["current_price"])
    color = "\033[92m" if upnl >= 0 else "\033[91m"
    reset = "\033[0m"
    print(f"  {p['symbol']:>8}  {p['asset_class']:>14}  "
          f"qty={float(p['quantity']):>12,.0f}  "
          f"avg={float(p['average_cost']):>10,.2f}  "
          f"mkt={float(p['current_price']):>10,.2f}  "
          f"mv={mv:>14,.2f}  "
          f"{color}upnl={upnl:>+12,.2f}{reset}  "
          f"rpnl={rpnl:>+12,.2f}")


async def main():
    async with httpx.AsyncClient(base_url=BASE, timeout=30.0) as c:

        print(f"\n{DIVIDER}")
        print("  GOLDEN HORSE FUND MANAGEMENT — OMS PROTOTYPE DEMO")
        print(f"{DIVIDER}\n")

        # 1. Health check
        print(f"{SECTION}")
        print("1. System Health Check")
        print(f"{SECTION}")
        r = await c.get("/health")
        pprint(r.json())

        # 2. Equity order — AAPL limit buy
        print(f"\n{SECTION}")
        print("2. Submit Equity Order: BUY 5,000 AAPL @ LIMIT 186.00")
        print(f"{SECTION}")
        r = await c.post("/orders", json={
            "symbol": "AAPL", "asset_class": "EQUITY", "side": "BUY",
            "order_type": "LIMIT", "quantity": "5000", "limit_price": "186.00",
            "trader": "pm_macro", "strategy": "US_TECH_MOMENTUM",
        })
        o1 = r.json()
        print_order(o1)

        # 3. FX order — SELL USDJPY (JPY weakening thesis)
        print(f"\n{SECTION}")
        print("3. Submit FX Order: SELL 50,000 USDJPY @ MARKET")
        print(f"{SECTION}")
        r = await c.post("/orders", json={
            "symbol": "USDJPY", "asset_class": "FX", "side": "SELL",
            "order_type": "MARKET", "quantity": "50000",
            "trader": "pm_macro", "strategy": "JPY_WEAKENING",
        })
        o2 = r.json()
        print_order(o2)

        # 4. Commodity order — Gold futures
        print(f"\n{SECTION}")
        print("4. Submit Commodity Order: BUY 50 GCQ26 (Gold) @ LIMIT 2355.00")
        print(f"{SECTION}")
        r = await c.post("/orders", json={
            "symbol": "GCQ26", "asset_class": "COMMODITY", "side": "BUY",
            "order_type": "LIMIT", "quantity": "50", "limit_price": "2355.00",
            "trader": "pm_macro", "strategy": "GOLD_INFLATION_HEDGE",
        })
        o3 = r.json()
        print_order(o3)

        # 5. Fixed income — Treasury futures
        print(f"\n{SECTION}")
        print("5. Submit Fixed Income Order: BUY 100 TY1 (10Y Treasury) @ MARKET")
        print(f"{SECTION}")
        r = await c.post("/orders", json={
            "symbol": "TY1", "asset_class": "FIXED_INCOME", "side": "BUY",
            "order_type": "MARKET", "quantity": "100",
            "trader": "pm_macro", "strategy": "DURATION_BET",
        })
        o4 = r.json()
        print_order(o4)

        # 6. Risk rejection — restricted symbol (China A-share)
        print(f"\n{SECTION}")
        print("6. Risk Rejection: BUY China A-share (600519.SS — Kweichow Moutai)")
        print(f"{SECTION}")
        r = await c.post("/orders", json={
            "symbol": "600519.SS", "asset_class": "EQUITY", "side": "BUY",
            "order_type": "MARKET", "quantity": "1000", "trader": "pm_macro",
        })
        rej1 = r.json()
        print_order(rej1)
        print(f"  Reason: {rej1['reject_reason']}")

        # 7. Risk rejection — unauthorized trader
        print(f"\n{SECTION}")
        print("7. Risk Rejection: Equity trader attempting FX trade")
        print(f"{SECTION}")
        r = await c.post("/orders", json={
            "symbol": "USDJPY", "asset_class": "FX", "side": "BUY",
            "order_type": "MARKET", "quantity": "1000000", "trader": "trader_eq",
        })
        rej2 = r.json()
        print_order(rej2)
        print(f"  Reason: {rej2['reject_reason']}")

        # 8. Risk rejection — excessive notional
        print(f"\n{SECTION}")
        print("8. Risk Rejection: Excessive notional (500K NVDA = ~$425M)")
        print(f"{SECTION}")
        r = await c.post("/orders", json={
            "symbol": "NVDA", "asset_class": "EQUITY", "side": "BUY",
            "order_type": "MARKET", "quantity": "500000", "trader": "pm_macro",
        })
        rej3 = r.json()
        print_order(rej3)
        print(f"  Reason: {rej3['reject_reason']}")

        # 9. Wait for venue responses
        print(f"\n{SECTION}")
        print("9. Waiting for venue execution responses (3 seconds)...")
        print(f"{SECTION}")
        await asyncio.sleep(3)

        # 10. Submit and cancel
        print(f"\n{SECTION}")
        print("10. Submit and Cancel: BUY 10,000 MSFT @ LIMIT 415.00")
        print(f"{SECTION}")
        r = await c.post("/orders", json={
            "symbol": "MSFT", "asset_class": "EQUITY", "side": "BUY",
            "order_type": "LIMIT", "quantity": "10000", "limit_price": "415.00",
            "trader": "pm_macro",
        })
        o5 = r.json()
        print("  Submitted:")
        print_order(o5)
        await asyncio.sleep(1)
        r = await c.post(f"/orders/{o5['id']}/cancel")
        o5c = r.json()
        if r.status_code == 200:
            print("  After cancel request:")
            print_order(o5c)
        else:
            # Race condition: order was already filled before cancel processed
            print(f"  Cancel response: {o5c.get('detail', 'Order already filled (race condition)')}")
            print("  (This demonstrates a real-world scenario where fills arrive before cancels)")
        await asyncio.sleep(2)

        # 11. All orders summary
        print(f"\n{SECTION}")
        print("11. All Orders")
        print(f"{SECTION}")
        r = await c.get("/orders?limit=100")
        for o in r.json():
            print_order(o)

        # 12. Order detail with fills and audit trail
        print(f"\n{SECTION}")
        print("12. Order Detail — AAPL (fills + audit trail)")
        print(f"{SECTION}")
        r = await c.get(f"/orders/{o1['id']}")
        detail = r.json()
        print(f"  Status: {detail['status']}")
        print(f"  Filled: {float(detail['filled_quantity']):,.0f} / {float(detail['quantity']):,.0f}")
        print(f"  Avg Price: {float(detail['average_price']):,.2f}")
        print(f"\n  Fills ({len(detail['fills'])}):")
        for f in detail["fills"]:
            print(f"    {f['exec_id']}  qty={float(f['fill_quantity']):>10,.0f}  px={float(f['fill_price']):>10,.2f}")
        print(f"\n  Audit Trail ({len(detail['events'])} events):")
        for e in detail["events"]:
            ts = e["timestamp"][:19]
            print(f"    {ts}  {e['event_type']:>20}  {(e['from_status'] or ''):>18} -> {(e['to_status'] or ''):>18}")

        # 13. Positions
        print(f"\n{SECTION}")
        print("13. Current Positions")
        print(f"{SECTION}")
        r = await c.get("/positions")
        positions = r.json()
        total_mv = 0
        total_upnl = 0
        for p in positions:
            print_position(p)
            total_mv += abs(float(p["quantity"]) * float(p["current_price"]))
            total_upnl += float(p["unrealized_pnl"])
        print(f"\n  Total Market Value: ${total_mv:>14,.2f}")
        print(f"  Total Unrealized P&L: ${total_upnl:>+13,.2f}")

        # 14. Trade file
        print(f"\n{SECTION}")
        print("14. Prime Broker Trade File (CSV)")
        print(f"{SECTION}")
        r = await c.get("/reports/trades")
        lines = r.text.strip().split("\n")
        for line in lines[:6]:
            print(f"  {line}")
        if len(lines) > 6:
            print(f"  ... ({len(lines) - 1} trades total)")

        # 15. Position report
        print(f"\n{SECTION}")
        print("15. Fund Admin Position Report (CSV)")
        print(f"{SECTION}")
        r = await c.get("/reports/positions")
        lines = r.text.strip().split("\n")
        for line in lines:
            print(f"  {line}")

        # 16. Reconciliation
        print(f"\n{SECTION}")
        print("16. Three-Way Reconciliation (OMS vs Prime Broker vs Fund Admin)")
        print(f"{SECTION}")
        r = await c.get("/reports/reconciliation")
        recon = r.json()
        s = recon["summary"]
        status_color = "\033[92m" if recon["status"] == "RECONCILED" else "\033[91m"
        reset = "\033[0m"
        print(f"  Status: {status_color}{recon['status']}{reset}")
        print(f"  Positions: {s['total_positions']}  Matched: {s['matched']}  Breaks: {s['breaks']}")
        for d in recon["details"]:
            icon = "  " if d["status"] == "MATCHED" else "!!"
            print(f"  {icon} {d['symbol']:>8}  OMS={d['oms_quantity']:>12,.0f}  "
                  f"PB={d['pb_quantity']:>12,.0f}  Admin={d['admin_quantity']:>12,.0f}  "
                  f"{d['status']}")
            if d.get("break_details"):
                print(f"     -> {d['break_details']}")

        print(f"\n{DIVIDER}")
        print("  DEMO COMPLETE")
        print(f"  Dashboard: http://localhost:8000/static/index.html")
        print(f"  API Docs:  http://localhost:8000/docs")
        print(f"{DIVIDER}\n")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except httpx.ConnectError:
        print("\nError: Cannot connect to OMS server.")
        print("Start the server first:  uvicorn oms.main:app --reload\n")
        sys.exit(1)
