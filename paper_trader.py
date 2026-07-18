"""
paper_trader.py
---------------
สมุดบันทึก Paper Trading (เทรดจำลอง — ไม่มีเงินจริงเกี่ยวข้อง)

หน้าที่:
1. ทุกครั้งที่ระบบให้สัญญาณ BUY/SELL -> บันทึกเป็น "เทรดจำลอง" พร้อมราคาเข้า, SL, TP
2. รอบถัดไป -> เช็คราคาจริงที่เกิดขึ้นหลังจากนั้น ว่าเทรดจำลองโดน SL (แพ้) หรือ TP (ชนะ)
3. สะสมสถิติ: ชนะกี่ %, กำไร/ขาดทุนสะสม (คิดแบบเสี่ยง 1% ต่อไม้ เหมือน backtest)

จุดประสงค์: พิสูจน์ว่าระบบทำผลงานได้ใกล้เคียงผล backtest ไหม "แบบเดินหน้า"
ก่อนตัดสินใจเรื่องเงินจริง (แผนกำหนดขั้นต่ำ 1-3 เดือน)

กติกาเดียวกับ backtest ทุกข้อ:
- TP = 2 เท่าของระยะ SL, หักสเปรด, แท่งเดียวโดนทั้งคู่ = นับแพ้ (มองโลกร้าย)

ข้อมูลเก็บที่ output/paper_trades.json

ทดสอบไฟล์นี้เดี่ยวๆ (ใช้ข้อมูลจำลอง ไม่ต้องต่อเน็ต):
    python paper_trader.py
"""

import json
import os
from datetime import datetime, timezone

import pandas as pd

import config
import price_fetcher
from signal_combiner import pip_size_of, spread_pips_of


# ============================================
# ส่วนที่ 1: อ่าน/เขียนสมุดบันทึก
# ============================================

def load_trades() -> list:
    if not os.path.exists(config.PAPER_LOG_FILE):
        return []
    with open(config.PAPER_LOG_FILE, encoding="utf-8") as f:
        return json.load(f)


def save_trades(trades: list):
    os.makedirs(config.OUTPUT_DIR, exist_ok=True)
    with open(config.PAPER_LOG_FILE, "w", encoding="utf-8") as f:
        json.dump(trades, f, ensure_ascii=False, indent=2)


# ============================================
# ส่วนที่ 2: เปิดเทรดจำลองจากสัญญาณ
# ============================================

def open_trade_from_signal(pair: str, signal: dict) -> dict:
    """สร้างเทรดจำลอง 1 ไม้จากสัญญาณ BUY/SELL ของ signal_combiner"""
    direction = 1 if signal["action"] == "BUY" else -1
    pip = pip_size_of(pair)
    spread = spread_pips_of(pair) * pip
    sl_dist = signal["suggested_sl_pips"] * pip

    # ราคาเข้า = ราคาปัจจุบัน + ครึ่งสเปรด (เหมือนโดนสเปรดตอนเข้าจริง)
    entry = signal["price_now"] + direction * (spread / 2)

    return {
        "pair": pair,
        "direction": signal["action"],                 # "BUY" / "SELL"
        "confidence": signal["confidence"],
        "entry_time": datetime.now(timezone.utc).isoformat(),
        "entry_price": round(entry, 5),
        "sl_price": round(entry - direction * sl_dist, 5),
        "tp_price": round(entry + direction * sl_dist * config.BACKTEST_TP_RR, 5),
        "sl_dist": sl_dist,
        "status": "open",                              # open / won / lost
    }


# ============================================
# ส่วนที่ 3: เช็คเทรดที่เปิดอยู่กับราคาจริง
# ============================================

def check_trade(trade: dict, ohlc: pd.DataFrame) -> bool:
    """
    เช็คเทรด 1 ไม้กับข้อมูลราคา: โดน SL/TP หรือยัง
    ถ้าปิดแล้วจะแก้ไข trade ในที่ (in-place) และคืน True
    """
    entry_time = pd.Timestamp(trade["entry_time"])
    # เอาเฉพาะแท่งที่เกิด "หลัง" เวลาเข้า (เทียบเวลาแบบ UTC ทั้งคู่)
    bars = ohlc[ohlc.index.tz_convert("UTC") > entry_time]

    d = 1 if trade["direction"] == "BUY" else -1
    pip = pip_size_of(trade["pair"])
    spread = spread_pips_of(trade["pair"]) * pip

    for ts, bar in bars.iterrows():
        hit_sl = bar["low"] <= trade["sl_price"] if d == 1 else bar["high"] >= trade["sl_price"]
        hit_tp = bar["high"] >= trade["tp_price"] if d == 1 else bar["low"] <= trade["tp_price"]

        result_r = None
        if hit_sl:                       # โดนทั้งคู่ในแท่งเดียว = นับแพ้ (มองโลกร้าย)
            result_r = -1.0
        elif hit_tp:
            result_r = config.BACKTEST_TP_RR

        if result_r is not None:
            cost_r = (spread / 2) / trade["sl_dist"]   # หักสเปรดขาออก
            trade["status"] = "won" if result_r > 0 else "lost"
            trade["exit_time"] = str(ts)
            trade["net_r"] = round(result_r - cost_r, 3)
            return True

    return False


def update_open_trades(trades: list) -> list:
    """เช็คเทรดที่ยังเปิดอยู่ทั้งหมดกับราคาล่าสุด คืนรายการเทรดที่เพิ่งปิดในรอบนี้"""
    open_trades = [t for t in trades if t["status"] == "open"]
    closed_now = []

    # ดึงราคาครั้งเดียวต่อคู่เงิน (ประหยัดเวลา)
    pairs = {t["pair"] for t in open_trades}
    prices = {}
    for pair in pairs:
        try:
            prices[pair] = price_fetcher.fetch_ohlc(pair)
        except Exception as e:
            print(f"   [paper] ดึงราคา {pair} ไม่ได้ ข้ามการเช็ครอบนี้: {e}")

    for trade in open_trades:
        if trade["pair"] in prices and check_trade(trade, prices[trade["pair"]]):
            closed_now.append(trade)

    return closed_now


# ============================================
# ส่วนที่ 4: จุดเรียกใช้หลัก + สถิติ
# ============================================

def process_results(results: list) -> dict:
    """
    เรียกหลังวิเคราะห์เสร็จทุกรอบ:
    1. เช็คเทรดเก่าที่ยังเปิด -> ปิดถ้าโดน SL/TP
    2. เปิดเทรดใหม่จากสัญญาณ BUY/SELL (คู่ละไม่เกิน 1 ไม้ที่เปิดพร้อมกัน)
    คืน dict: {"opened": [...], "closed": [...], "stats": {...}}
    """
    trades = load_trades()

    closed_now = update_open_trades(trades)

    opened_now = []
    open_pairs = {t["pair"] for t in trades if t["status"] == "open"}
    for r in results:
        sig = r["combined_signal"]
        if sig["action"] in ("BUY", "SELL") and r["pair"] not in open_pairs:
            trade = open_trade_from_signal(r["pair"], sig)
            trades.append(trade)
            opened_now.append(trade)

    save_trades(trades)
    return {"opened": opened_now, "closed": closed_now, "stats": summarize(trades)}


def summarize(trades: list = None) -> dict:
    """สรุปสถิติ paper trading ทั้งหมดจนถึงตอนนี้"""
    if trades is None:
        trades = load_trades()

    closed = [t for t in trades if t["status"] != "open"]
    wins = [t for t in closed if t["status"] == "won"]

    # จำลองทุน: เริ่ม 100% เสี่ยง 1% ต่อไม้ (เรียงตามเวลาปิด)
    equity = 1.0
    for t in sorted(closed, key=lambda t: t.get("exit_time", "")):
        equity *= (1 + (config.RISK_PER_TRADE_PERCENT / 100) * t["net_r"])

    return {
        "open_count": sum(1 for t in trades if t["status"] == "open"),
        "closed_count": len(closed),
        "wins": len(wins),
        "losses": len(closed) - len(wins),
        "win_rate_pct": round(len(wins) / len(closed) * 100, 1) if closed else 0.0,
        "total_r": round(sum(t["net_r"] for t in closed), 2),
        "sim_return_pct": round((equity - 1) * 100, 2),
    }


# ============================================
# ทดสอบรันไฟล์นี้เดี่ยวๆ ด้วยข้อมูลจำลอง (ไม่แตะไฟล์จริง)
# ============================================
if __name__ == "__main__":
    print("ทดสอบ paper_trader ด้วยข้อมูลจำลอง 3 สถานการณ์...\n")

    def mock_ohlc(prices_hl):
        """สร้างแท่งเทียนจำลองรายชั่วโมง: [(high, low), ...]"""
        idx = pd.date_range("2026-01-01 10:00", periods=len(prices_hl), freq="1h", tz="UTC")
        return pd.DataFrame({
            "open": [h for h, _ in prices_hl],
            "high": [h for h, _ in prices_hl],
            "low": [l for _, l in prices_hl],
            "close": [l for _, l in prices_hl],
        }, index=idx)

    def mock_trade():
        return {
            "pair": "EURUSD", "direction": "BUY", "confidence": "สูง",
            "entry_time": "2026-01-01T09:00:00+00:00",
            "entry_price": 1.1000, "sl_price": 1.0980, "tp_price": 1.1040,
            "sl_dist": 0.0020, "status": "open",
        }

    # 1. ราคาวิ่งขึ้นถึง TP -> ต้องชนะ
    t1 = mock_trade()
    check_trade(t1, mock_ohlc([(1.1010, 1.0995), (1.1045, 1.1005)]))
    print(f"1. ราคาแตะ TP: status={t1['status']} net_r={t1.get('net_r')} (ต้องเป็น won, ~+2)")

    # 2. ราคาร่วงถึง SL -> ต้องแพ้
    t2 = mock_trade()
    check_trade(t2, mock_ohlc([(1.1005, 1.0975)]))
    print(f"2. ราคาแตะ SL: status={t2['status']} net_r={t2.get('net_r')} (ต้องเป็น lost, ~-1)")

    # 3. ราคาแกว่งแคบ ไม่แตะอะไร -> ต้องยังเปิดอยู่
    t3 = mock_trade()
    check_trade(t3, mock_ohlc([(1.1010, 1.0995), (1.1015, 1.0990)]))
    print(f"3. ยังไม่แตะทั้งคู่: status={t3['status']} (ต้องยังเป็น open)")
