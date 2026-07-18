"""
backtester.py
-------------
ทดสอบกลยุทธ์กับข้อมูลราคาย้อนหลัง (Backtest)
เพื่อตอบคำถามสำคัญที่สุด: "ถ้าใช้กลยุทธ์นี้ในอดีต จะกำไรหรือขาดทุน?"

รองรับการเปรียบเทียบ 2 กลยุทธ์ ใน 3 timeframes (1h / 4h / 1d):

กลยุทธ์ v1 "โหวตรวม" (แบบเดียวกับ signal_combiner ปัจจุบัน):
- เข้าเมื่อคะแนนโหวตรวมจาก 4 indicators ถึงเกณฑ์ (ปกติ ±2)
- จุดอ่อนที่เจอจากการ backtest: RSI/Bollinger (สวนเทรนด์) หักล้างกับ
  MA/MACD (ตามเทรนด์) ทำให้โหวต ±3 ไม่เคยเกิดขึ้นเลย

กลยุทธ์ v2 "ตามเทรนด์ + รอย่อ" (trend + pullback):
- ทิศทาง: MA เร็ว/ช้า และ MACD ต้องชี้ทางเดียวกัน (ไม่ตรงกัน = ไม่เทรด)
- จังหวะเข้า: รอราคา "ย่อ" สวนเทรนด์ก่อน — ขาขึ้นรอ RSI < 50, ขาลงรอ RSI > 50
  (ใช้เส้นกลาง 50 ซึ่งเป็นค่ามาตรฐาน ไม่ได้จูนเอง เพื่อเลี่ยง overfitting)

กติกาเหมือนกันทั้งคู่ (เทียบกันแฟร์ๆ):
- Stop-loss = 1.5 x ATR, Take-profit = 2 เท่าของ SL, เสี่ยง 1% ต่อไม้, หักสเปรด
- กัน lookahead bias: ตัดสินใจจากแท่งที่ปิดแล้ว เข้าที่ราคาเปิดแท่งถัดไป
- แท่งเดียวแตะทั้ง SL และ TP = นับเป็นโดน SL (มองโลกร้ายไว้ก่อน)

ข้อจำกัด: ทดสอบได้เฉพาะฝั่งเทคนิค (ข่าวย้อนหลังหลายเดือนไม่มีให้ใช้ฟรี)
และผลในอดีตไม่รับประกันผลในอนาคต — ต้องผ่าน demo ก่อนเงินจริงเสมอ

วิธีใช้:
    python backtester.py
"""

import numpy as np
import pandas as pd

import config
import price_fetcher
import technical_analyzer
from signal_combiner import pip_size_of


# ============================================
# ส่วนที่ 1: ตัวสร้างสัญญาณ (แต่ละกลยุทธ์)
# แต่ละตัวคืน DataFrame ที่มีคอลัมน์เพิ่ม:
#   signal = +1 (เข้า BUY) / -1 (เข้า SELL) / 0 (ไม่เข้า)
#   atr    = สำหรับคำนวณระยะ stop-loss
# indicator ทุกตัวใช้เฉพาะข้อมูลย้อนหลังของแท่งนั้น จึงไม่มีการแอบเห็นอนาคต
# ============================================

def _base_indicators(ohlc: pd.DataFrame) -> dict:
    """คำนวณ indicator พื้นฐานที่ทั้งสองกลยุทธ์ใช้ร่วมกัน"""
    close = ohlc["close"]
    return {
        "ma_fast": technical_analyzer.moving_average(close, config.MA_FAST_PERIOD),
        "ma_slow": technical_analyzer.moving_average(close, config.MA_SLOW_PERIOD),
        "rsi": technical_analyzer.rsi(close, config.RSI_PERIOD),
        "macd": technical_analyzer.macd(close),
        "bb": technical_analyzer.bollinger_bands(close, config.BB_PERIOD),
        "atr": technical_analyzer.atr(ohlc["high"], ohlc["low"], close, config.ATR_PERIOD),
    }


def _warmup_bars() -> int:
    """จำนวนแท่งช่วง 'อุ่นเครื่อง' ที่ indicator ยังคำนวณไม่ครบ ต้องตัดทิ้ง"""
    return max(config.MA_SLOW_PERIOD, config.BB_PERIOD, config.RSI_PERIOD, config.ATR_PERIOD)


def signals_v1_vote(ohlc: pd.DataFrame, entry_vote: int = 2) -> pd.DataFrame:
    """กลยุทธ์ v1: คะแนนโหวตรวม 4 indicators ถึงเกณฑ์ = เข้า"""
    ind = _base_indicators(ohlc)
    close = ohlc["close"]
    macd_line, signal_line = ind["macd"]
    bb_upper, _, bb_lower = ind["bb"]

    ma_vote = np.where(ind["ma_fast"] > ind["ma_slow"], 1, -1)
    rsi_vote = np.where(ind["rsi"] > config.RSI_OVERBOUGHT, -1,
               np.where(ind["rsi"] < config.RSI_OVERSOLD, 1, 0))
    macd_vote = np.where(macd_line > signal_line, 1, -1)
    bb_vote = np.where(close > bb_upper, -1,
              np.where(close < bb_lower, 1, 0))

    vote = ma_vote + rsi_vote + macd_vote + bb_vote

    result = ohlc.copy()
    result["signal"] = np.where(vote >= entry_vote, 1, np.where(vote <= -entry_vote, -1, 0))
    result["atr"] = ind["atr"]
    return result.iloc[_warmup_bars():]


def signals_v2_trend_pullback(ohlc: pd.DataFrame) -> pd.DataFrame:
    """กลยุทธ์ v2: MA+MACD กำหนดทิศทาง, RSI บอกจังหวะย่อ"""
    ind = _base_indicators(ohlc)
    macd_line, signal_line = ind["macd"]
    rsi = ind["rsi"]

    # ทิศทางเทรนด์: ทั้ง MA และ MACD ต้องเห็นตรงกัน
    uptrend = (ind["ma_fast"] > ind["ma_slow"]) & (macd_line > signal_line)
    downtrend = (ind["ma_fast"] < ind["ma_slow"]) & (macd_line < signal_line)

    # จังหวะเข้า: ราคาย่อสวนเทรนด์ (RSI ข้ามมาอยู่ฝั่งตรงข้ามของเส้นกลาง 50)
    buy = uptrend & (rsi < 50)
    sell = downtrend & (rsi > 50)

    result = ohlc.copy()
    result["signal"] = np.where(buy, 1, np.where(sell, -1, 0))
    result["atr"] = ind["atr"]
    return result.iloc[_warmup_bars():]


# ============================================
# ส่วนที่ 2: ตัวจำลองการเทรด (ใช้ร่วมกันทุกกลยุทธ์)
# ============================================

def simulate(pair: str, df: pd.DataFrame) -> dict:
    """
    จำลองการเทรดทีละแท่งตามคอลัมน์ signal ใน df แล้วสรุปสถิติ

    df ต้องมีคอลัมน์: open, high, low, close, signal, atr
    """
    pip = pip_size_of(pair)
    spread = config.BACKTEST_SPREAD_PIPS * pip     # ต้นทุนต่อออเดอร์ (หน่วยราคา)
    rr = config.BACKTEST_TP_RR
    risk_pct = config.RISK_PER_TRADE_PERCENT / 100

    opens = df["open"].to_numpy()
    highs = df["high"].to_numpy()
    lows = df["low"].to_numpy()
    signals = df["signal"].to_numpy()
    atrs = df["atr"].to_numpy()
    times = df.index

    equity = 1.0                 # เริ่มที่ 1.0 = 100% ของทุน
    equity_curve = []            # เก็บ (เวลา, ทุน) ไว้วาดกราฟ
    trades = []                  # เก็บผลทุกไม้
    position = None              # ออเดอร์ที่ถืออยู่ (None = ว่าง)

    for i in range(len(df) - 1):
        if position is None:
            # --- ยังไม่มีออเดอร์: ดูว่าแท่งนี้ (ปิดแล้ว) ให้สัญญาณไหม ---
            if signals[i] != 0 and not np.isnan(atrs[i]):
                direction = int(signals[i])                      # 1 = BUY, -1 = SELL
                sl_dist = atrs[i] * config.ATR_SL_MULTIPLIER
                if sl_dist <= 0:
                    continue
                entry = opens[i + 1] + direction * (spread / 2)  # เข้าที่เปิดแท่งถัดไป + ครึ่งสเปรด
                position = {
                    "direction": direction,
                    "entry_time": times[i + 1],
                    "entry": entry,
                    "sl": entry - direction * sl_dist,
                    "tp": entry + direction * sl_dist * rr,
                    "sl_dist": sl_dist,
                }
        else:
            # --- มีออเดอร์อยู่: เช็คแท่งนี้ว่าโดน SL หรือ TP ไหม ---
            d = position["direction"]
            hit_sl = lows[i] <= position["sl"] if d == 1 else highs[i] >= position["sl"]
            hit_tp = highs[i] >= position["tp"] if d == 1 else lows[i] <= position["tp"]

            result_r = None
            if hit_sl:               # โดนทั้งคู่ในแท่งเดียว = นับ SL ก่อน (มองโลกร้าย)
                result_r = -1.0
            elif hit_tp:
                result_r = rr

            if result_r is not None:
                # หักต้นทุนสเปรดขาออกอีกครึ่ง (คิดเป็นสัดส่วนของระยะ SL)
                cost_r = (spread / 2) / position["sl_dist"]
                net_r = result_r - cost_r

                # อัปเดตทุน: เสี่ยง 1% ของทุนต่อ 1R
                equity *= (1 + risk_pct * net_r)
                equity_curve.append((times[i], equity))
                trades.append({
                    "pair": pair,
                    "direction": "BUY" if d == 1 else "SELL",
                    "entry_time": str(position["entry_time"]),
                    "exit_time": str(times[i]),
                    "result": "ชนะ (TP)" if result_r > 0 else "แพ้ (SL)",
                    "net_r": round(net_r, 3),
                })
                position = None

    return _summarize(pair, trades, equity, equity_curve, times)


def _summarize(pair, trades, final_equity, equity_curve, times) -> dict:
    """สรุปสถิติจากรายการเทรดทั้งหมด"""
    n = len(trades)
    wins = [t for t in trades if t["net_r"] > 0]
    losses = [t for t in trades if t["net_r"] <= 0]

    gross_win = sum(t["net_r"] for t in wins)
    gross_loss = abs(sum(t["net_r"] for t in losses))

    # Max drawdown: ทุนเคยร่วงจากจุดสูงสุดลงมามากสุดกี่ %
    max_dd = 0.0
    peak = 1.0
    for _, eq in equity_curve:
        peak = max(peak, eq)
        max_dd = max(max_dd, (peak - eq) / peak)

    period = f"{times[0].strftime('%d/%m/%Y')} ถึง {times[-1].strftime('%d/%m/%Y')}"

    return {
        "pair": pair,
        "period": period,
        "total_trades": n,
        "wins": len(wins),
        "losses": len(losses),
        "win_rate_pct": round(len(wins) / n * 100, 1) if n else 0.0,
        "profit_factor": round(gross_win / gross_loss, 2) if gross_loss > 0 else None,
        "net_return_pct": round((final_equity - 1) * 100, 2),
        "max_drawdown_pct": round(max_dd * 100, 2),
        "trades": trades,
        "equity_curve": equity_curve,
    }


# ============================================
# ส่วนที่ 3: รันเปรียบเทียบหลายกลยุทธ์ / หลาย timeframe
# ============================================

# กลยุทธ์ที่ทดสอบ: {ชื่อ: ฟังก์ชันสร้างสัญญาณ}
STRATEGIES = {
    "v1 โหวตรวม (±2)": lambda ohlc: signals_v1_vote(ohlc, entry_vote=2),
    "v2 เทรนด์+รอย่อ": signals_v2_trend_pullback,
}


def fetch_for_timeframe(pair: str, timeframe: str) -> pd.DataFrame:
    """
    ดึงข้อมูลตาม timeframe ที่ต้องการ:
    - "1h": ดึงตรงจาก Yahoo ย้อนหลัง 1 ปี
    - "4h": Yahoo ไม่มี -> ดึง 1h ย้อนหลัง ~2 ปี แล้วรวมแท่งเอง
    - "1d": ดึงตรง ย้อนหลัง 5 ปี
    """
    if timeframe == "1h":
        return price_fetcher.fetch_ohlc(pair, timeframe="1h", lookback="1y")
    if timeframe == "4h":
        hourly = price_fetcher.fetch_ohlc(pair, timeframe="1h", lookback="729d")
        return price_fetcher.resample_ohlc(hourly, "4h")
    if timeframe == "1d":
        return price_fetcher.fetch_ohlc(pair, timeframe="1d", lookback="5y")
    raise ValueError(f"ไม่รองรับ timeframe: {timeframe}")


def run_comparison(timeframes: list = None) -> dict:
    """
    รัน backtest ทุกกลยุทธ์ x ทุก timeframe x ทุกคู่เงิน
    คืน dict: {timeframe: {ชื่อกลยุทธ์: [ผลรายคู่เงิน]}}
    """
    timeframes = timeframes or ["1h", "4h", "1d"]
    all_results = {}

    for tf in timeframes:
        print(f"\n--- Timeframe {tf} ---")
        # ดึงข้อมูลครั้งเดียวต่อคู่ ใช้ร่วมกันทุกกลยุทธ์
        data = {}
        for pair in config.WATCHED_PAIRS:
            try:
                data[pair] = fetch_for_timeframe(pair, tf)
                print(f"   ดึงข้อมูล {pair} ได้ {len(data[pair])} แท่ง")
            except Exception as e:
                print(f"   [ข้าม] {pair}: {e}")

        all_results[tf] = {}
        for name, make_signals in STRATEGIES.items():
            results = [simulate(pair, make_signals(ohlc)) for pair, ohlc in data.items()]
            all_results[tf][name] = results

    return all_results


def print_report(results: list):
    print(f"{'คู่เงิน':<10}{'เทรด':>6}{'ชนะ':>6}{'Win%':>8}{'PF':>7}{'กำไรสุทธิ':>12}{'DD สูงสุด':>12}")
    print("-" * 64)
    for r in results:
        pf = r["profit_factor"] if r["profit_factor"] is not None else "-"
        print(f"{r['pair']:<10}{r['total_trades']:>6}{r['wins']:>6}"
              f"{r['win_rate_pct']:>7}%{pf:>7}"
              f"{r['net_return_pct']:>11}%{r['max_drawdown_pct']:>11}%")

    # แถวรวม: นับทุกเทรดของทุกคู่รวมกัน
    all_trades = [t for r in results for t in r["trades"]]
    wins = [t for t in all_trades if t["net_r"] > 0]
    losses = [t for t in all_trades if t["net_r"] <= 0]
    gross_win = sum(t["net_r"] for t in wins)
    gross_loss = abs(sum(t["net_r"] for t in losses))
    pf_total = round(gross_win / gross_loss, 2) if gross_loss > 0 else "-"
    winrate = round(len(wins) / len(all_trades) * 100, 1) if all_trades else 0.0
    avg_return = round(sum(r["net_return_pct"] for r in results) / len(results), 2) if results else 0.0
    print(f"{'รวม':<10}{len(all_trades):>6}{len(wins):>6}{winrate:>7}%{pf_total:>7}{avg_return:>10}%*{'':>11}")
    print("   (* = ค่าเฉลี่ยกำไรสุทธิของทุกคู่)")


if __name__ == "__main__":
    print("=" * 64)
    print("Backtest เปรียบเทียบกลยุทธ์ (SL=1.5xATR, TP=2xSL, เสี่ยง 1% ต่อไม้)")
    print("=" * 64)

    comparison = run_comparison()

    for tf, per_strategy in comparison.items():
        print(f"\n{'=' * 64}")
        print(f"Timeframe: {tf}")
        print("=" * 64)
        for name, results in per_strategy.items():
            print(f"\n[{name}]")
            print_report(results)

    print("\nวิธีอ่าน:")
    print("- Win% = ชนะกี่ % ของเทรดทั้งหมด (กลยุทธ์ RR 1:2 ชนะเกิน ~35% ก็เริ่มมีกำไร)")
    print("- PF (Profit Factor) = กำไรรวม/ขาดทุนรวม — เกิน 1.0 คือกำไร, ต่ำกว่าคือขาดทุน")
    print("- กำไรสุทธิ = ทุนเปลี่ยนไปกี่ % ตลอดช่วงทดสอบ (เสี่ยง 1% ต่อไม้)")
    print("- DD สูงสุด = ทุนเคยร่วงจากจุดสูงสุดมากสุดกี่ % (ยิ่งต่ำยิ่งดี)")

    print("\n" + "=" * 64)
    print("คำเตือน: ผล backtest คืออดีต ไม่รับประกันอนาคต และนี่คือการทดสอบ")
    print("เฉพาะฝั่งเทคนิค (ไม่มีข่าวยืนยัน) — ก่อนใช้เงินจริงต้องผ่าน demo ก่อนเสมอ")
    print("=" * 64)
