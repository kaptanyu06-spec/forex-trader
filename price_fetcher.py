"""
price_fetcher.py
----------------
ดึงข้อมูลราคาย้อนหลัง (OHLC = Open/High/Low/Close) ของคู่เงิน Forex

ใช้ library `yfinance` (ข้อมูลจาก Yahoo Finance) เพราะ:
- ฟรี ไม่ต้องสมัคร API key
- มีข้อมูลคู่เงิน Forex ครบ (ใช้สัญลักษณ์แบบ "EURUSD=X")

หมายเหตุ: ข้อมูลจาก Yahoo เหมาะสำหรับขั้นเรียนรู้/backtest เบื้องต้น
เมื่อเชื่อมต่อ MT5 แล้ว ควรเปลี่ยนมาดึงราคาจาก broker โดยตรง
(ผ่าน MetaTrader5.copy_rates_from) เพราะจะตรงกับราคาที่เทรดจริงมากกว่า

ทดสอบไฟล์นี้เดี่ยวๆ ได้ด้วยคำสั่ง:
    python price_fetcher.py
"""

import pandas as pd
import yfinance as yf

import config


def pair_to_yahoo_symbol(pair: str) -> str:
    """
    แปลงชื่อคู่เงินของเรา เช่น 'EURUSD' -> สัญลักษณ์ของ Yahoo คือ 'EURUSD=X'
    ยกเว้นทองคำ XAUUSD: Yahoo ไม่มีราคา spot ให้ ใช้ 'GC=F' (ทองฟิวเจอร์ส COMEX)
    ซึ่งราคาขยับใกล้เคียงกันมาก เหมาะสำหรับวิเคราะห์/paper trading
    """
    if pair.upper() == "XAUUSD":
        return "GC=F"
    return f"{pair}=X"


def fetch_ohlc(pair: str, timeframe: str = None, lookback: str = None) -> pd.DataFrame:
    """
    ดึงราคาย้อนหลังของคู่เงิน 1 คู่

    Parameters
    ----------
    pair : ชื่อคู่เงิน เช่น "EURUSD"
    timeframe : ขนาดแท่งเทียน เช่น "1h" (1 ชั่วโมง), "1d" (รายวัน)
                ถ้าไม่ระบุ จะใช้ค่าจาก config.PRICE_TIMEFRAME
    lookback : ช่วงเวลาย้อนหลัง เช่น "60d" (60 วัน), "1y" (1 ปี)
               ถ้าไม่ระบุ จะใช้ค่าจาก config.PRICE_LOOKBACK

    Returns
    -------
    DataFrame ที่มีคอลัมน์: open, high, low, close
    (แต่ละแถวคือแท่งเทียน 1 แท่ง เรียงจากเก่าไปใหม่)
    """
    timeframe = timeframe or config.PRICE_TIMEFRAME
    lookback = lookback or config.PRICE_LOOKBACK

    symbol = pair_to_yahoo_symbol(pair)
    data = yf.download(
        symbol,
        period=lookback,
        interval=timeframe,
        progress=False,       # ไม่ต้องแสดงแถบโหลด
        auto_adjust=True,
    )

    if data is None or data.empty:
        raise ValueError(
            f"ดึงราคา {pair} ไม่สำเร็จ (ไม่มีข้อมูลกลับมา) "
            f"— ลองเช็คอินเทอร์เน็ต หรือชื่อคู่เงินว่าถูกต้องหรือไม่"
        )

    # yfinance บางเวอร์ชันคืนคอลัมน์ซ้อน 2 ชั้น (MultiIndex) — ทำให้เหลือชั้นเดียว
    if isinstance(data.columns, pd.MultiIndex):
        data.columns = data.columns.get_level_values(0)

    # เก็บเฉพาะคอลัมน์ที่ใช้ และเปลี่ยนชื่อเป็นตัวพิมพ์เล็กให้ใช้ง่าย
    data = data[["Open", "High", "Low", "Close"]].copy()
    data.columns = ["open", "high", "low", "close"]

    # ลบแถวที่ข้อมูลขาด (ถ้ามี)
    data = data.dropna()

    return data


def resample_ohlc(ohlc: pd.DataFrame, rule: str) -> pd.DataFrame:
    """
    รวมแท่งเทียนเล็กเป็นแท่งใหญ่ เช่น รวมแท่ง 1h เป็นแท่ง 4h
    (Yahoo ไม่มีข้อมูล 4h ให้ตรงๆ เลยต้องรวมเอง)

    rule: ขนาดแท่งปลายทาง เช่น "4h"
    """
    resampled = ohlc.resample(rule).agg({
        "open": "first",    # ราคาเปิด = เปิดของแท่งย่อยแรก
        "high": "max",      # สูงสุด = สูงสุดของทุกแท่งย่อย
        "low": "min",       # ต่ำสุด = ต่ำสุดของทุกแท่งย่อย
        "close": "last",    # ราคาปิด = ปิดของแท่งย่อยสุดท้าย
    })
    return resampled.dropna()


def fetch_all_watched_ohlc() -> dict:
    """
    ดึงราคาของทุกคู่เงินใน config.WATCHED_PAIRS

    Returns
    -------
    dict รูปแบบ {ชื่อคู่เงิน: DataFrame ราคา}
    คู่ที่ดึงไม่สำเร็จจะถูกข้าม (พร้อมพิมพ์แจ้งเตือน)
    """
    all_prices = {}
    for pair in config.WATCHED_PAIRS:
        try:
            all_prices[pair] = fetch_ohlc(pair)
            print(f"   ดึงราคา {pair} สำเร็จ ({len(all_prices[pair])} แท่ง)")
        except Exception as e:
            print(f"   [ข้าม] {pair}: {e}")
    return all_prices


# ============================================
# ทดสอบรันไฟล์นี้เดี่ยวๆ
# ============================================
if __name__ == "__main__":
    print("ทดสอบดึงราคา EURUSD ...")
    df = fetch_ohlc("EURUSD")
    print(f"ได้ข้อมูล {len(df)} แท่งเทียน")
    print("\n5 แท่งล่าสุด:")
    print(df.tail())
