"""
technical_analyzer.py
---------------------
วิเคราะห์กราฟด้วย Technical Indicators

Indicators ที่คำนวณ:
1. MA Crossover  — เส้นค่าเฉลี่ยเร็วตัดเส้นช้า บอกแนวโน้ม (ขึ้น/ลง)
2. RSI           — วัดภาวะซื้อมากเกิน (>70) / ขายมากเกิน (<30)
3. MACD          — วัดโมเมนตัมของแนวโน้ม
4. ATR           — วัดความผันผวน ใช้คำนวณระยะ stop-loss แบบ dynamic
5. Bollinger Bands — กรอบราคาบน/ล่าง บอกว่าราคา "ตึง" ไปด้านไหน

เราคำนวณเองด้วย pandas ล้วนๆ (ไม่พึ่ง library อื่น)
เพื่อให้อ่านสูตรเข้าใจได้ และไม่มีปัญหาเวอร์ชัน library ชนกัน

ทดสอบไฟล์นี้เดี่ยวๆ ได้ด้วยคำสั่ง (ใช้ข้อมูลจำลอง ไม่ต้องต่อเน็ต):
    python technical_analyzer.py
"""

import pandas as pd

import config


# ============================================
# ส่วนที่ 1: สูตรคำนวณ indicator แต่ละตัว
# ============================================

def moving_average(close: pd.Series, period: int) -> pd.Series:
    """Simple Moving Average — ค่าเฉลี่ยราคาปิดย้อนหลัง `period` แท่ง"""
    return close.rolling(window=period).mean()


def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    """
    RSI (Relative Strength Index) ค่าระหว่าง 0-100
    - สูงกว่า 70 = ซื้อมากเกิน (overbought) ราคาอาจย่อลง
    - ต่ำกว่า 30 = ขายมากเกิน (oversold) ราคาอาจเด้งขึ้น
    """
    delta = close.diff()                          # ราคาเปลี่ยนจากแท่งก่อนหน้าเท่าไร
    gain = delta.clip(lower=0)                    # เก็บเฉพาะขาขึ้น
    loss = -delta.clip(upper=0)                   # เก็บเฉพาะขาลง (กลับเป็นบวก)

    # ใช้ค่าเฉลี่ยแบบ Wilder (มาตรฐานของ RSI)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period).mean()

    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9):
    """
    MACD — ผลต่างระหว่างค่าเฉลี่ยเร็ว (12) กับช้า (26)
    คืนค่า 2 เส้น: (macd_line, signal_line)
    - macd_line ตัดขึ้นเหนือ signal_line = โมเมนตัมขาขึ้น
    - macd_line ตัดลงใต้ signal_line = โมเมนตัมขาลง
    """
    ema_fast = close.ewm(span=fast, min_periods=fast).mean()
    ema_slow = close.ewm(span=slow, min_periods=slow).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, min_periods=signal).mean()
    return macd_line, signal_line


def atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    """
    ATR (Average True Range) — ระยะแกว่งเฉลี่ยของราคาต่อแท่ง
    ใช้ตั้ง stop-loss แบบ dynamic เช่น SL = ราคาเข้า - (1.5 x ATR)
    """
    prev_close = close.shift(1)
    # True Range = ค่ามากสุดของ 3 ระยะนี้
    tr = pd.concat([
        high - low,                     # ช่วงราคาในแท่งนี้
        (high - prev_close).abs(),      # กระโดดขึ้นจากแท่งก่อน
        (low - prev_close).abs(),       # กระโดดลงจากแท่งก่อน
    ], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / period, min_periods=period).mean()


def bollinger_bands(close: pd.Series, period: int = 20, num_std: float = 2.0):
    """
    Bollinger Bands — กรอบราคา = ค่าเฉลี่ย ± (ส่วนเบี่ยงเบนมาตรฐาน x 2)
    คืนค่า 3 เส้น: (เส้นบน, เส้นกลาง, เส้นล่าง)
    """
    middle = close.rolling(window=period).mean()
    std = close.rolling(window=period).std()
    upper = middle + num_std * std
    lower = middle - num_std * std
    return upper, middle, lower


# ============================================
# ส่วนที่ 2: แปลงค่า indicator เป็น "สัญญาณ" ที่อ่านง่าย
# ============================================

def analyze_pair_prices(pair: str, ohlc: pd.DataFrame) -> dict:
    """
    วิเคราะห์ราคาของคู่เงิน 1 คู่ ด้วย indicator ทุกตัว

    Parameters
    ----------
    pair : ชื่อคู่เงิน เช่น "EURUSD"
    ohlc : DataFrame จาก price_fetcher.fetch_ohlc()
           (ต้องมีคอลัมน์ open, high, low, close)

    Returns
    -------
    dict สรุปสัญญาณของแต่ละ indicator + สัญญาณรวม
    """
    close = ohlc["close"]

    # ---------- 1. MA Crossover ----------
    ma_fast = moving_average(close, config.MA_FAST_PERIOD)
    ma_slow = moving_average(close, config.MA_SLOW_PERIOD)

    if ma_fast.iloc[-1] > ma_slow.iloc[-1]:
        ma_signal = "ขาขึ้น (เส้นเร็วอยู่เหนือเส้นช้า)"
        ma_vote = 1
    else:
        ma_signal = "ขาลง (เส้นเร็วอยู่ใต้เส้นช้า)"
        ma_vote = -1

    # เพิ่งตัดกันในแท่งล่าสุดหรือไม่ (สัญญาณสดใหม่กว่า)
    crossed_now = (
        (ma_fast.iloc[-2] <= ma_slow.iloc[-2]) != (ma_fast.iloc[-1] <= ma_slow.iloc[-1])
    )

    # ---------- 2. RSI ----------
    rsi_series = rsi(close, config.RSI_PERIOD)
    rsi_now = float(rsi_series.iloc[-1])

    if rsi_now > config.RSI_OVERBOUGHT:
        rsi_signal = f"ซื้อมากเกิน (RSI={rsi_now:.1f}) ระวังราคาย่อ"
        rsi_vote = -1
    elif rsi_now < config.RSI_OVERSOLD:
        rsi_signal = f"ขายมากเกิน (RSI={rsi_now:.1f}) ราคาอาจเด้ง"
        rsi_vote = 1
    else:
        rsi_signal = f"โซนกลาง (RSI={rsi_now:.1f})"
        rsi_vote = 0

    # ---------- 3. MACD ----------
    macd_line, signal_line = macd(close)
    if macd_line.iloc[-1] > signal_line.iloc[-1]:
        macd_signal = "โมเมนตัมขาขึ้น (MACD เหนือ signal)"
        macd_vote = 1
    else:
        macd_signal = "โมเมนตัมขาลง (MACD ใต้ signal)"
        macd_vote = -1

    # ---------- 4. ATR (สำหรับ stop-loss ไม่ใช่ทิศทาง) ----------
    atr_series = atr(ohlc["high"], ohlc["low"], close, config.ATR_PERIOD)
    atr_now = float(atr_series.iloc[-1])
    suggested_sl_distance = atr_now * config.ATR_SL_MULTIPLIER

    # ---------- 5. Bollinger Bands ----------
    bb_upper, bb_middle, bb_lower = bollinger_bands(close, config.BB_PERIOD)
    price_now = float(close.iloc[-1])

    if price_now > bb_upper.iloc[-1]:
        bb_signal = "ราคาทะลุกรอบบน (ตึงด้านบน อาจย่อ)"
        bb_vote = -1
    elif price_now < bb_lower.iloc[-1]:
        bb_signal = "ราคาหลุดกรอบล่าง (ตึงด้านล่าง อาจเด้ง)"
        bb_vote = 1
    else:
        bb_signal = "ราคาอยู่ในกรอบปกติ"
        bb_vote = 0

    # ---------- รวมคะแนนโหวตเป็นสัญญาณเทคนิคภาพรวม ----------
    # แนวคิด: MA + MACD บอก "แนวโน้ม", RSI + BB บอก "จังหวะสุดโต่ง"
    total_vote = ma_vote + macd_vote + rsi_vote + bb_vote

    if total_vote >= 2:
        overall = "แนวโน้มขาขึ้น (BULLISH)"
    elif total_vote <= -2:
        overall = "แนวโน้มขาลง (BEARISH)"
    else:
        overall = "ไม่ชัดเจน (NEUTRAL)"

    # ---------- กลยุทธ์ "ตามเทรนด์ + รอย่อ" (ผ่านการ backtest แล้ว) ----------
    # ทิศทาง: MA และ MACD ต้องเห็นตรงกัน / จังหวะเข้า: RSI ย่อข้ามเส้นกลาง 50
    if ma_vote == 1 and macd_vote == 1:
        trend_direction = "up"
        trend_label = "ขาขึ้น (MA และ MACD เห็นตรงกัน)"
    elif ma_vote == -1 and macd_vote == -1:
        trend_direction = "down"
        trend_label = "ขาลง (MA และ MACD เห็นตรงกัน)"
    else:
        trend_direction = "none"
        trend_label = "ไม่มีเทรนด์ชัด (MA กับ MACD ขัดกัน)"

    if trend_direction == "up" and rsi_now < 50:
        entry_signal = 1        # ขาขึ้น + ราคาย่อ = จังหวะซื้อ
    elif trend_direction == "down" and rsi_now > 50:
        entry_signal = -1       # ขาลง + ราคาเด้ง = จังหวะขาย
    else:
        entry_signal = 0        # ยังไม่มีจังหวะ

    return {
        "pair": pair,
        "price_now": round(price_now, 5),
        "ma_signal": ma_signal,
        "ma_crossed_this_bar": bool(crossed_now),
        "rsi_value": round(rsi_now, 1),
        "rsi_signal": rsi_signal,
        "macd_signal": macd_signal,
        "atr_value": round(atr_now, 5),
        "suggested_sl_distance": round(suggested_sl_distance, 5),
        "bb_signal": bb_signal,
        "technical_vote": total_vote,          # -4 ถึง +4 (เก็บไว้ดูประกอบ)
        "technical_bias": overall,
        "trend_direction": trend_direction,    # "up" / "down" / "none"
        "trend_label": trend_label,
        "entry_signal": entry_signal,          # +1 จังหวะซื้อ / -1 จังหวะขาย / 0 รอ
    }


# ============================================
# ทดสอบรันไฟล์นี้เดี่ยวๆ ด้วยข้อมูลจำลอง (ไม่ต้องต่อเน็ต)
# ============================================
if __name__ == "__main__":
    import numpy as np

    print("ทดสอบ technical_analyzer ด้วยข้อมูลจำลอง (แนวโน้มขาขึ้น)...")

    # สร้างราคาจำลอง 200 แท่ง: ขาขึ้นเรียบๆ + สุ่มแกว่งเล็กน้อย
    rng = np.random.default_rng(seed=42)
    trend = np.linspace(1.0500, 1.1200, 200)
    noise = rng.normal(0, 0.0008, 200)
    close_prices = trend + noise

    mock = pd.DataFrame({
        "open": close_prices - 0.0003,
        "high": close_prices + 0.0010,
        "low": close_prices - 0.0010,
        "close": close_prices,
    })

    result = analyze_pair_prices("EURUSD(จำลอง)", mock)
    for key, value in result.items():
        print(f"   {key}: {value}")
