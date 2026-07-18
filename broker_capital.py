"""
broker_capital.py
-----------------
เชื่อมต่อโบรกเกอร์ Capital.com ผ่าน REST API (ขั้น 5.4 — ทางเลือกแทน OANDA)

ทำไมเพิ่ม Capital.com: ผู้ใช้ติดปัญหาล็อกอิน OANDA — Capital.com สมัคร demo
ง่ายกว่ามาก และ REST API ใช้ได้ทุกระบบปฏิบัติการเหมือนกัน
(ระบบรองรับทั้ง 2 โบรก: ใส่คีย์ของอันไหน อันนั้นทำงาน)

*** ความปลอดภัย: ไฟล์นี้รองรับเฉพาะบัญชีทดลอง (demo = เงินปลอม) เท่านั้น ***
ตามแผนขั้นบันได: ต้องผ่าน paper trading + demo อย่างน้อย 1-3 เดือนก่อนคิดเรื่องเงินจริง

วิธีตั้งค่า (ทำครั้งเดียว ฟรี):
1. สมัครที่ https://capital.com (ยืนยันอีเมล แล้วเข้าโหมด Demo — สลับได้มุมบนของแอป)
2. ในแอปเว็บ: Settings -> API integrations -> Generate new key
   (ระบบอาจให้เปิด 2FA ก่อน ทำตามขั้นตอนบนจอ)
   ตอนสร้างคีย์จะให้ตั้ง "รหัสผ่านประจำคีย์" (custom password) — จดไว้ด้วย
3. ใส่ 3 ค่าใน secrets_local.py:
   CAPITAL_API_KEY      = คีย์ที่ได้ (โชว์ครั้งเดียวตอนสร้าง)
   CAPITAL_IDENTIFIER   = อีเมลที่ใช้สมัคร
   CAPITAL_API_PASSWORD = รหัสผ่านประจำคีย์ที่ตั้งไว้

ทดสอบการเชื่อมต่อ (อ่านข้อมูลอย่างเดียว ไม่ส่งออเดอร์):
    python broker_capital.py

คำเตือนสำคัญ: ระบบนี้เป็นเครื่องมือประกอบการตัดสินใจเท่านั้น ไม่รับประกันผลกำไร
"""

import requests

import config

# ที่อยู่เซิร์ฟเวอร์ Capital.com — เราใช้เฉพาะ demo (บัญชีทดลอง เงินปลอม)
DEMO_HOST = "https://demo-api-capital.backend-capital.com"

# ชื่อสินค้าในระบบ Capital.com (เรียกว่า "epic") — ส่วนใหญ่ตรงกับชื่อคู่เงินเรา
# ยกเว้นทองคำที่ใช้ชื่อ "GOLD"
EPIC_MAP = {"XAUUSD": "GOLD"}


def epic_of(pair: str) -> str:
    """แปลงชื่อคู่เงินของเรา (XAUUSD) เป็นชื่อในระบบ Capital.com (GOLD)"""
    return EPIC_MAP.get(pair, pair)


# ============================================
# ส่วนที่ 1: การเชื่อมต่อพื้นฐาน + login
# ============================================

def is_configured() -> bool:
    """เช็คว่าใส่คีย์ครบ 3 ค่าแล้วหรือยัง"""
    return bool(config.CAPITAL_API_KEY and config.CAPITAL_IDENTIFIER
                and config.CAPITAL_API_PASSWORD)


def _check_safety():
    """ด่านความปลอดภัย: ยอมทำงานเฉพาะบัญชีทดลองเท่านั้น"""
    if not is_configured():
        raise ValueError(
            "ยังไม่ได้ตั้งค่า CAPITAL_API_KEY / CAPITAL_IDENTIFIER / CAPITAL_API_PASSWORD "
            "ใน secrets_local.py (อ่านวิธีสมัครที่หัวไฟล์ broker_capital.py)"
        )
    if config.CAPITAL_ENV != "demo":
        raise ValueError(
            "ระบบนี้รองรับเฉพาะบัญชีทดลอง (CAPITAL_ENV = 'demo') เท่านั้น — "
            "ตามแผนต้องผ่าน paper trading 1-3 เดือนก่อนพิจารณาเรื่องบัญชีจริง"
        )


def login() -> dict:
    """
    ล็อกอินขอ "ตั๋วชั่วคราว" (session tokens) จาก Capital.com
    ตั๋วนี้ต้องแนบไปกับทุกคำขอหลังจากนี้ (หมดอายุเองใน ~10 นาที ไม่ต้อง logout)
    """
    _check_safety()
    resp = requests.post(
        DEMO_HOST + "/api/v1/session",
        headers={"X-CAP-API-KEY": config.CAPITAL_API_KEY},
        json={"identifier": config.CAPITAL_IDENTIFIER,
              "password": config.CAPITAL_API_PASSWORD},
        timeout=20,
    )
    if not resp.ok:
        raise RuntimeError(f"ล็อกอิน Capital.com ไม่สำเร็จ {resp.status_code}: {resp.text[:200]}")
    # ตั๋ว 2 ใบอยู่ใน header ของคำตอบ: CST (ตัวตน) + X-SECURITY-TOKEN (ความปลอดภัย)
    return {
        "X-CAP-API-KEY": config.CAPITAL_API_KEY,
        "CST": resp.headers["CST"],
        "X-SECURITY-TOKEN": resp.headers["X-SECURITY-TOKEN"],
    }


def _get(headers: dict, path: str) -> dict:
    """เรียกอ่านข้อมูล — ถ้าผิดพลาดจะโยน error พร้อมข้อความอธิบาย"""
    resp = requests.get(DEMO_HOST + path, headers=headers, timeout=20)
    if not resp.ok:
        raise RuntimeError(f"Capital.com ตอบกลับผิดพลาด {resp.status_code}: {resp.text[:200]}")
    return resp.json()


# ============================================
# ส่วนที่ 2: อ่านข้อมูลบัญชีและราคา
# ============================================

def get_account_summary(headers: dict) -> dict:
    """ดึงสรุปบัญชี: ยอดเงิน (ปลอม), กำไร/ขาดทุน — ใช้บัญชีแรกที่ตั้งเป็นหลัก"""
    accounts = _get(headers, "/api/v1/accounts")["accounts"]
    acct = next((a for a in accounts if a.get("preferred")), accounts[0])
    return {
        "balance": float(acct["balance"]["balance"]),
        "currency": acct["currency"],
        "account_id": acct["accountId"],
    }


def get_market(headers: dict, pair: str) -> dict:
    """ดึงข้อมูลสินค้า 1 ตัว: ราคาซื้อ/ขายปัจจุบัน + ขนาดไม้ขั้นต่ำที่โบรกยอมรับ"""
    data = _get(headers, f"/api/v1/markets/{epic_of(pair)}")
    return {
        "pair": pair,
        "bid": float(data["snapshot"]["bid"]),          # ราคาที่เราขายได้
        "ask": float(data["snapshot"]["offer"]),        # ราคาที่เราซื้อได้
        "min_size": float(data["dealingRules"]["minDealSize"]["value"]),
        "status": data["snapshot"]["marketStatus"],     # TRADEABLE = ตลาดเปิด
    }


def get_open_positions(headers: dict) -> list:
    """ดึงรายการไม้ที่เปิดค้างอยู่ในบัญชีทดลอง"""
    data = _get(headers, "/api/v1/positions")
    positions = []
    for p in data["positions"]:
        epic = p["market"]["epic"]
        # แปลงชื่อกลับเป็นแบบของเรา (GOLD -> XAUUSD)
        pair = next((k for k, v in EPIC_MAP.items() if v == epic), epic)
        positions.append({
            "pair": pair,
            "direction": p["position"]["direction"],    # "BUY" / "SELL"
            "size": float(p["position"]["size"]),
            "entry_price": float(p["position"]["level"]),
        })
    return positions


# ============================================
# ส่วนที่ 3: ส่งออเดอร์ (บัญชีทดลองเท่านั้น)
# ============================================

def place_market_order(headers: dict, pair: str, action: str, size: float,
                       sl_price: float, tp_price: float = None) -> dict:
    """
    ส่งออเดอร์ market เข้าบัญชีทดลอง

    pair     : เช่น "EURUSD"
    action   : "BUY" หรือ "SELL"
    size     : ขนาดไม้ (คู่เงิน = หน่วยสกุลเงินหลัก, ทอง = ออนซ์)
    sl_price : ราคา stop-loss — **บังคับต้องใส่เสมอ** (กฎเหล็กของโปรเจกต์)
    tp_price : ราคา take-profit (แนะนำให้ใส่ ตาม RR ที่ backtest ไว้)
    """
    _check_safety()

    # กฎเหล็ก: ทุกออเดอร์ต้องมี stop-loss ห้ามยกเว้น
    if not sl_price or sl_price <= 0:
        raise ValueError("ห้ามเปิดออเดอร์โดยไม่มี stop-loss — กฎ risk management ของโปรเจกต์")
    if action not in ("BUY", "SELL"):
        raise ValueError(f"action ต้องเป็น BUY หรือ SELL เท่านั้น (ได้รับ: {action})")

    order = {
        "epic": epic_of(pair),
        "direction": action,
        "size": size,
        "stopLevel": round(sl_price, 5),
    }
    if tp_price:
        order["profitLevel"] = round(tp_price, 5)

    resp = requests.post(DEMO_HOST + "/api/v1/positions",
                         headers=headers, json=order, timeout=20)
    if not resp.ok:
        raise RuntimeError(f"ส่งออเดอร์ไม่สำเร็จ {resp.status_code}: {resp.text[:200]}")

    # Capital.com ตอบกลับเป็น "ใบรับเรื่อง" (dealReference) — ต้องถามผลอีกที
    # ว่าออเดอร์สำเร็จจริงไหม (เช่น อาจถูกปฏิเสธเพราะตลาดปิดวันเสาร์-อาทิตย์)
    ref = resp.json()["dealReference"]
    confirm = _get(headers, f"/api/v1/confirms/{ref}")
    if confirm.get("dealStatus") != "ACCEPTED":
        reason = confirm.get("rejectReason") or confirm.get("status") or "ไม่ทราบสาเหตุ"
        raise RuntimeError(f"ออเดอร์ถูกปฏิเสธโดยโบรกเกอร์: {reason} (ตลาดปิดอยู่หรือเปล่า?)")
    return confirm


# ============================================
# ส่วนที่ 4: ต่อกับ scheduler — เทรดตามสัญญาณเข้าบัญชีทดลองอัตโนมัติ
# ============================================

def calc_size(pair: str, sl_dist: float, balance: float, price: float) -> float:
    """
    คำนวณขนาดไม้จากกฎเสี่ยง 1% ต่อไม้ — กติกาเดียวกับ paper trading

    หลักคิด: ถ้าโดน stop-loss เต็มๆ ต้องเสียไม่เกิน (balance x RISK_PER_TRADE_PERCENT)
    - คู่ที่ลงท้าย USD (EURUSD, XAUUSD): ขาดทุนเป็น USD ตรงๆ = size x ระยะ SL
    - คู่ที่ขึ้นต้น USD (USDJPY): ขาดทุนเป็นเงิน quote (เยน) ต้องแปลงกลับด้วยราคาปัจจุบัน
    """
    risk_usd = balance * config.RISK_PER_TRADE_PERCENT / 100

    if pair.endswith("USD"):
        size = risk_usd / sl_dist
    elif pair.startswith("USD"):
        size = risk_usd * price / sl_dist
    else:
        raise ValueError(f"ยังไม่รองรับการคำนวณขนาดไม้ของคู่ cross: {pair}")

    return round(size, 2)


def mirror_paper_trades(opened_trades: list) -> list:
    """
    ส่งออเดอร์เข้าบัญชีทดลอง Capital.com ให้ตรงกับ paper trade ที่เพิ่งเปิดในรอบนี้
    (SL/TP ฝากไว้กับโบรกเกอร์เลย — โบรกปิดไม้ให้เองเมื่อราคาแตะ ไม่ต้องรอรอบถัดไป)

    คืนรายการข้อความสรุปผล (สำเร็จ/ข้าม/ผิดพลาด) ไว้พิมพ์และส่ง Telegram
    ถ้ายังไม่ได้ตั้งค่าคีย์จะคืนลิสต์ว่าง = ระบบทำ paper trading ต่อตามปกติ
    """
    if not is_configured() or not opened_trades:
        return []

    try:
        headers = login()
        acct = get_account_summary(headers)
        open_pairs = {p["pair"] for p in get_open_positions(headers)}
    except Exception as e:
        return [f"⚠️ Capital.com: เชื่อมต่อไม่ได้ ข้ามการส่งออเดอร์รอบนี้ ({e})"]

    notes = []
    for t in opened_trades:
        pair = t["pair"]
        if pair in open_pairs:
            notes.append(f"⏭️ Capital.com: {pair} มีไม้เปิดค้างอยู่แล้ว ไม่เปิดซ้ำ")
            continue
        try:
            size = calc_size(pair, t["sl_dist"], acct["balance"], t["entry_price"])
            market = get_market(headers, pair)
            if size < market["min_size"]:
                # ไม้เล็กกว่าขั้นต่ำของโบรก — ใช้ขั้นต่ำแทน แต่บอกไว้ให้รู้ว่าเสี่ยงเกินสูตร
                notes.append(f"ℹ️ Capital.com: {pair} ขนาดตามสูตร {size} เล็กกว่าขั้นต่ำ "
                             f"{market['min_size']} ใช้ขั้นต่ำแทน")
                size = market["min_size"]
            place_market_order(headers, pair, t["direction"], size,
                               sl_price=t["sl_price"], tp_price=t["tp_price"])
            notes.append(f"🏦 Capital.com demo: เปิด {t['direction']} {pair} "
                         f"ขนาด {size:,} (ทุนปลอม {acct['balance']:,.0f} {acct['currency']})")
        except Exception as e:
            notes.append(f"⚠️ Capital.com: เปิด {pair} ไม่สำเร็จ — {e}")
    return notes


# ============================================
# ทดสอบไฟล์นี้เดี่ยวๆ — อ่านข้อมูลอย่างเดียว ไม่ส่งออเดอร์
# ============================================
if __name__ == "__main__":
    print("ทดสอบเชื่อมต่อ Capital.com (บัญชีทดลอง — อ่านอย่างเดียว ไม่ส่งออเดอร์)\n")

    if not is_configured():
        print("ยังไม่ได้ตั้งค่า CAPITAL_API_KEY / CAPITAL_IDENTIFIER / CAPITAL_API_PASSWORD")
        print("อ่านวิธีสมัครบัญชีทดลอง (ฟรี) ที่หัวไฟล์นี้")
    else:
        h = login()
        acct = get_account_summary(h)
        print(f"บัญชีทดลอง {acct['account_id']}: "
              f"ยอดเงิน(ปลอม) {acct['balance']:,.2f} {acct['currency']}")

        for pair in config.WATCHED_PAIRS:
            try:
                m = get_market(h, pair)
                print(f"  {pair}: bid {m['bid']} / ask {m['ask']} "
                      f"(ขั้นต่ำ {m['min_size']}, {m['status']})")
            except Exception as e:
                print(f"  {pair}: ดึงราคาไม่ได้ — {e}")

        print("\nเชื่อมต่อสำเร็จ! ระบบพร้อมส่งออเดอร์ demo อัตโนมัติในรอบถัดไป")
        print("คำเตือน: เครื่องมือประกอบการตัดสินใจเท่านั้น ไม่รับประกันผลกำไร")
