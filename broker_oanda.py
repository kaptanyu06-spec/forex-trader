"""
broker_oanda.py
---------------
เชื่อมต่อโบรกเกอร์ OANDA ผ่าน REST API (ขั้น 5.4 ของแผน)

ทำไมใช้ OANDA แทน MT5:
- เราใช้ Mac แต่ package `MetaTrader5` ของ Python รองรับเฉพาะ Windows
- OANDA มี REST API ที่ใช้ได้ทุกระบบปฏิบัติการ + บัญชีทดลอง (practice) ฟรี

*** ความปลอดภัย: ไฟล์นี้รองรับเฉพาะบัญชีทดลอง (practice = เงินปลอม) เท่านั้น ***
ตามแผนขั้นบันได: ต้องผ่าน paper trading + demo อย่างน้อย 1-3 เดือนก่อนคิดเรื่องเงินจริง

วิธีตั้งค่า (ทำครั้งเดียว ฟรี):
1. สมัครบัญชีทดลอง (demo) ที่ https://www.oanda.com
2. เข้าหน้าจัดการบัญชี -> Manage API Access -> สร้าง Personal Access Token
3. ใส่ค่าใน config.py: OANDA_API_KEY และ OANDA_ACCOUNT_ID

ทดสอบการเชื่อมต่อ (อ่านข้อมูลอย่างเดียว ไม่ส่งออเดอร์):
    python broker_oanda.py

คำเตือนสำคัญ: ระบบนี้เป็นเครื่องมือประกอบการตัดสินใจเท่านั้น ไม่รับประกันผลกำไร
"""

import math

import requests

import config
from signal_combiner import pip_size_of

# ที่อยู่เซิร์ฟเวอร์ OANDA — เราใช้เฉพาะ practice (บัญชีทดลอง เงินปลอม)
PRACTICE_HOST = "https://api-fxpractice.oanda.com"


# ============================================
# ส่วนที่ 1: การเชื่อมต่อพื้นฐาน
# ============================================

def is_configured() -> bool:
    """เช็คว่าใส่ API key และหมายเลขบัญชีแล้วหรือยัง"""
    return bool(config.OANDA_API_KEY and config.OANDA_ACCOUNT_ID)


def _check_safety():
    """ด่านความปลอดภัย: ยอมทำงานเฉพาะบัญชีทดลองเท่านั้น"""
    if not is_configured():
        raise ValueError(
            "ยังไม่ได้ตั้งค่า OANDA_API_KEY / OANDA_ACCOUNT_ID ใน config.py "
            "(อ่านวิธีสมัครที่หัวไฟล์ broker_oanda.py)"
        )
    if config.OANDA_ENV != "practice":
        raise ValueError(
            "ระบบนี้รองรับเฉพาะบัญชีทดลอง (OANDA_ENV = 'practice') เท่านั้น — "
            "ตามแผนต้องผ่าน paper trading 1-3 เดือนก่อนพิจารณาเรื่องบัญชีจริง"
        )


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {config.OANDA_API_KEY}",
        "Content-Type": "application/json",
    }


def _get(path: str, params: dict = None) -> dict:
    """เรียกอ่านข้อมูลจาก OANDA — ถ้าผิดพลาดจะโยน error พร้อมข้อความอธิบาย"""
    _check_safety()
    resp = requests.get(PRACTICE_HOST + path, headers=_headers(), params=params, timeout=20)
    if not resp.ok:
        raise RuntimeError(f"OANDA ตอบกลับผิดพลาด {resp.status_code}: {resp.text[:200]}")
    return resp.json()


def oanda_instrument(pair: str) -> str:
    """แปลงชื่อคู่เงินของเรา (EURUSD) เป็นรูปแบบ OANDA (EUR_USD)"""
    return f"{pair[:3]}_{pair[3:]}"


def price_decimals(pair: str) -> int:
    """
    จำนวนทศนิยมของราคาที่ OANDA ยอมรับ ประมาณจากขนาด pip ของคู่เงินนั้น
    เช่น EURUSD (pip 0.0001) -> 5 ตำแหน่ง, USDJPY (pip 0.01) -> 3, XAUUSD (pip 0.1) -> 2
    สำคัญ: ถ้าส่งทศนิยมละเอียดเกินที่โบรกรับ ออเดอร์จะถูกปฏิเสธทันที
    """
    pip = pip_size_of(pair)
    return max(1, -int(math.floor(math.log10(pip))) + 1)


# ============================================
# ส่วนที่ 2: อ่านข้อมูลบัญชีและราคา
# ============================================

def get_account_summary() -> dict:
    """ดึงสรุปบัญชี: ยอดเงิน (ปลอม), กำไร/ขาดทุนลอยตัว, จำนวนไม้ที่เปิดอยู่"""
    data = _get(f"/v3/accounts/{config.OANDA_ACCOUNT_ID}/summary")["account"]
    return {
        "balance": float(data["balance"]),
        "currency": data["currency"],
        "unrealized_pl": float(data["unrealizedPL"]),
        "open_trade_count": int(data["openTradeCount"]),
    }


def get_price(pair: str) -> dict:
    """ดึงราคาซื้อ/ขายปัจจุบันของคู่เงิน 1 คู่"""
    data = _get(
        f"/v3/accounts/{config.OANDA_ACCOUNT_ID}/pricing",
        params={"instruments": oanda_instrument(pair)},
    )
    p = data["prices"][0]
    return {
        "pair": pair,
        "bid": float(p["bids"][0]["price"]),   # ราคาที่เราขายได้
        "ask": float(p["asks"][0]["price"]),   # ราคาที่เราซื้อได้
        "time": p["time"],
    }


def get_open_trades() -> list:
    """ดึงรายการไม้ที่เปิดค้างอยู่ในบัญชีทดลอง"""
    data = _get(f"/v3/accounts/{config.OANDA_ACCOUNT_ID}/openTrades")
    trades = []
    for t in data["trades"]:
        trades.append({
            "id": t["id"],
            "pair": t["instrument"].replace("_", ""),
            "units": int(float(t["currentUnits"])),   # บวก = BUY, ลบ = SELL
            "entry_price": float(t["price"]),
            "unrealized_pl": float(t["unrealizedPL"]),
        })
    return trades


# ============================================
# ส่วนที่ 3: ส่งออเดอร์ (บัญชีทดลองเท่านั้น)
# ============================================

def place_market_order(pair: str, action: str, units: int,
                       sl_price: float, tp_price: float = None) -> dict:
    """
    ส่งออเดอร์ market เข้าบัญชีทดลอง

    pair     : เช่น "EURUSD"
    action   : "BUY" หรือ "SELL"
    units    : จำนวนหน่วยสกุลเงินหลัก (1,000 units = 0.01 lot มาตรฐาน)
    sl_price : ราคา stop-loss — **บังคับต้องใส่เสมอ** (กฎเหล็กของโปรเจกต์)
    tp_price : ราคา take-profit (แนะนำให้ใส่ ตาม RR ที่ backtest ไว้)
    """
    _check_safety()

    # กฎเหล็ก: ทุกออเดอร์ต้องมี stop-loss ห้ามยกเว้น
    if not sl_price or sl_price <= 0:
        raise ValueError("ห้ามเปิดออเดอร์โดยไม่มี stop-loss — กฎ risk management ของโปรเจกต์")
    if action not in ("BUY", "SELL"):
        raise ValueError(f"action ต้องเป็น BUY หรือ SELL เท่านั้น (ได้รับ: {action})")

    signed_units = abs(units) if action == "BUY" else -abs(units)
    nd = price_decimals(pair)   # ทศนิยมต้องตรงกับที่โบรกรับ ไม่งั้นโดนปฏิเสธ (เช่น USDJPY = 3)
    order = {
        "order": {
            "type": "MARKET",
            "instrument": oanda_instrument(pair),
            "units": str(signed_units),
            "stopLossOnFill": {"price": f"{sl_price:.{nd}f}"},
        }
    }
    if tp_price:
        order["order"]["takeProfitOnFill"] = {"price": f"{tp_price:.{nd}f}"}

    resp = requests.post(
        f"{PRACTICE_HOST}/v3/accounts/{config.OANDA_ACCOUNT_ID}/orders",
        headers=_headers(), json=order, timeout=20,
    )
    if not resp.ok:
        raise RuntimeError(f"ส่งออเดอร์ไม่สำเร็จ {resp.status_code}: {resp.text[:200]}")

    data = resp.json()
    # ถ้าออเดอร์ถูกปฏิเสธ (เช่น ตลาดปิดวันเสาร์-อาทิตย์) OANDA จะตอบ 201 แต่มี cancelTransaction
    if "orderCancelTransaction" in data:
        reason = data["orderCancelTransaction"].get("reason", "ไม่ทราบสาเหตุ")
        raise RuntimeError(f"ออเดอร์ถูกยกเลิกโดยโบรกเกอร์: {reason} (ตลาดปิดอยู่หรือเปล่า?)")
    return data


# ============================================
# ส่วนที่ 4: ต่อกับ scheduler — เทรดตามสัญญาณเข้าบัญชีทดลองอัตโนมัติ
# ============================================

def calc_units(pair: str, sl_dist: float, balance: float, price: float) -> int:
    """
    คำนวณขนาดไม้ (units) จากกฎเสี่ยง 1% ต่อไม้ — กติกาเดียวกับ paper trading

    หลักคิด: ถ้าโดน stop-loss เต็มๆ ต้องเสียไม่เกิน (balance x RISK_PER_TRADE_PERCENT)
    - คู่ที่ลงท้าย USD (EURUSD, XAUUSD ฯลฯ): ขาดทุนเป็น USD ตรงๆ = units x ระยะ SL
    - คู่ที่ขึ้นต้น USD (USDJPY): ขาดทุนเป็นเงิน quote (เยน) ต้องแปลงกลับด้วยราคาปัจจุบัน
    """
    risk_usd = balance * config.RISK_PER_TRADE_PERCENT / 100

    if pair.endswith("USD"):
        units = risk_usd / sl_dist
    elif pair.startswith("USD"):
        units = risk_usd * price / sl_dist
    else:
        raise ValueError(f"ยังไม่รองรับการคำนวณขนาดไม้ของคู่ cross: {pair}")

    return max(1, int(units))   # ปัดลงกันเสี่ยงเกิน, ขั้นต่ำของ OANDA คือ 1 unit


def mirror_paper_trades(opened_trades: list) -> list:
    """
    ส่งออเดอร์เข้าบัญชีทดลอง OANDA ให้ตรงกับ paper trade ที่เพิ่งเปิดในรอบนี้
    (SL/TP ฝากไว้กับโบรกเกอร์เลย — โบรกปิดไม้ให้เองเมื่อราคาแตะ ไม่ต้องรอรอบถัดไป)

    คืนรายการข้อความสรุปผล (สำเร็จ/ข้าม/ผิดพลาด) ไว้พิมพ์และส่ง Telegram
    ถ้ายังไม่ได้ตั้งค่าคีย์ OANDA จะคืนลิสต์ว่าง = ระบบทำ paper trading ต่อตามปกติ
    """
    if not is_configured() or not opened_trades:
        return []

    try:
        acct = get_account_summary()
        open_pairs = {t["pair"] for t in get_open_trades()}
    except Exception as e:
        return [f"⚠️ OANDA: เชื่อมต่อไม่ได้ ข้ามการส่งออเดอร์รอบนี้ ({e})"]

    notes = []
    for t in opened_trades:
        pair = t["pair"]
        if pair in open_pairs:
            notes.append(f"⏭️ OANDA: {pair} มีไม้เปิดค้างอยู่แล้ว ไม่เปิดซ้ำ")
            continue
        try:
            units = calc_units(pair, t["sl_dist"], acct["balance"], t["entry_price"])
            place_market_order(pair, t["direction"], units,
                               sl_price=t["sl_price"], tp_price=t["tp_price"])
            notes.append(f"🏦 OANDA demo: เปิด {t['direction']} {pair} "
                         f"{units:,} units (ทุนปลอม {acct['balance']:,.0f} {acct['currency']})")
        except Exception as e:
            notes.append(f"⚠️ OANDA: เปิด {pair} ไม่สำเร็จ — {e}")
    return notes


# ============================================
# ทดสอบไฟล์นี้เดี่ยวๆ — อ่านข้อมูลอย่างเดียว ไม่ส่งออเดอร์
# ============================================
if __name__ == "__main__":
    print("ทดสอบเชื่อมต่อ OANDA (บัญชีทดลอง — อ่านอย่างเดียว ไม่ส่งออเดอร์)\n")

    if not is_configured():
        print("ยังไม่ได้ตั้งค่า OANDA_API_KEY / OANDA_ACCOUNT_ID ใน config.py")
        print("อ่านวิธีสมัครบัญชีทดลอง (ฟรี) ที่หัวไฟล์นี้")
    else:
        acct = get_account_summary()
        print(f"บัญชีทดลอง: ยอดเงิน(ปลอม) {acct['balance']:,.2f} {acct['currency']} | "
              f"ไม้เปิดค้าง {acct['open_trade_count']}")

        for pair in config.WATCHED_PAIRS:
            try:
                p = get_price(pair)
                print(f"  {pair}: bid {p['bid']} / ask {p['ask']}")
            except Exception as e:
                print(f"  {pair}: ดึงราคาไม่ได้ — {e}")

        print("\nเชื่อมต่อสำเร็จ! (ขั้นถัดไป: ต่อเข้ากับ scheduler ให้ส่งออเดอร์ demo อัตโนมัติ)")
        print("คำเตือน: เครื่องมือประกอบการตัดสินใจเท่านั้น ไม่รับประกันผลกำไร")
