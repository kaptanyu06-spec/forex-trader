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

import requests

import config

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
    order = {
        "order": {
            "type": "MARKET",
            "instrument": oanda_instrument(pair),
            "units": str(signed_units),
            "stopLossOnFill": {"price": f"{sl_price:.5f}"},
        }
    }
    if tp_price:
        order["order"]["takeProfitOnFill"] = {"price": f"{tp_price:.5f}"}

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
