"""
signal_combiner.py
------------------
รวมสัญญาณจาก 2 แหล่งให้เป็นข้อสรุปเดียว:
1. เทคนิค (technical) -> กลยุทธ์ "ตามเทรนด์ + รอย่อ" เป็นตัวให้จังหวะเข้า
2. ข่าว (sentiment)   -> เป็นตัวกรอง: เห็นด้วย = มั่นใจขึ้น, ขัดแย้ง = ห้ามเข้า

กลยุทธ์เทคนิคนี้ผ่านการ backtest แล้ว (ก.ค. 2026, ข้อมูล 1h ย้อนหลัง 1 ปี):
ดีกว่าระบบโหวตรวมแบบเก่าทุกคู่เงิน (PF รวม 1.27 vs 0.97, drawdown ต่ำกว่ามาก)
แต่ผลอดีตไม่รับประกันอนาคต — ยังต้องพิสูจน์ต่อด้วย paper trading

กฎการรวม (ออกแบบให้ระมัดระวังไว้ก่อน — สงสัยเมื่อไหร่ = WAIT):

| เทคนิคให้จังหวะ | ข่าวว่าไง        | ผลลัพธ์                        |
|-----------------|------------------|--------------------------------|
| ซื้อ/ขาย        | ชี้ทางเดียวกัน   | BUY/SELL ความเชื่อมั่น "สูง"    |
| ซื้อ/ขาย        | กลางๆ/ไม่มีข่าว  | BUY/SELL ความเชื่อมั่น "ปานกลาง"|
| ซื้อ/ขาย        | ชี้สวนทาง        | WAIT — ข่าวขัดแย้ง ห้ามเข้า     |
| ไม่มีจังหวะ     | อะไรก็ตาม        | WAIT                           |

ผลลัพธ์เป็นเพียงข้อมูลประกอบการตัดสินใจ ไม่ใช่คำแนะนำการลงทุน
และไม่รับประกันผลกำไรใดๆ

ทดสอบไฟล์นี้เดี่ยวๆ ได้ด้วยคำสั่ง (ใช้ข้อมูลจำลอง):
    python signal_combiner.py
"""

# เกณฑ์ตัดสินฝั่งข่าว: |net_score| ต้องถึงค่านี้ ข่าวถึงนับว่า "มีทิศทาง"
NEWS_THRESHOLD = 0.15


def pip_size_of(pair: str) -> float:
    """
    ขนาด 1 pip ของคู่เงิน:
    - คู่ที่ลงท้ายด้วย JPY: 1 pip = 0.01 (เพราะราคา quote เป็นหลักร้อย)
    - คู่อื่นๆ: 1 pip = 0.0001
    """
    return 0.01 if pair.upper().endswith("JPY") else 0.0001


def _news_direction(news_analysis: dict | None) -> str:
    """สรุปทิศทางจากข่าว: 'up' / 'down' / 'neutral' / 'no_data'"""
    if news_analysis is None:
        return "no_data"
    score = news_analysis["net_score"]
    if score >= NEWS_THRESHOLD:
        return "up"
    if score <= -NEWS_THRESHOLD:
        return "down"
    return "neutral"


def combine_signals(pair: str, news_analysis: dict | None, technical: dict | None) -> dict:
    """
    รวมสัญญาณข่าว + เทคนิคของคู่เงิน 1 คู่ เป็นข้อสรุปเดียว

    Returns
    -------
    dict:
    - action: "BUY" / "SELL" / "WAIT"
    - confidence: "สูง" / "ปานกลาง" / "-" (กรณี WAIT)
    - reason: คำอธิบายที่มาของข้อสรุป
    - suggested_sl_pips: ระยะ stop-loss แนะนำเป็น pip (จาก ATR) — มีเฉพาะกรณี BUY/SELL
    """
    # ถ้าไม่มีข้อมูลเทคนิคเลย = ตัดสินใจไม่ได้ (เทคนิคคือตัวให้จังหวะเข้า)
    if technical is None:
        return {
            "pair": pair,
            "action": "WAIT",
            "confidence": "-",
            "reason": "ไม่มีข้อมูลราคา/เทคนิค จึงไม่สามารถประเมินจังหวะเข้าได้",
        }

    news_dir = _news_direction(news_analysis)
    entry = technical["entry_signal"]           # +1 / -1 / 0 จากกลยุทธ์เทรนด์+รอย่อ

    action = "WAIT"
    confidence = "-"
    reason = ""

    if entry == 0:
        # เทคนิคไม่ให้จังหวะ = ไม่เข้า ไม่ว่าข่าวจะว่าอะไร
        if technical["trend_direction"] == "none":
            reason = f"{technical['trend_label']} — ไม่เทรดตอนไม่มีเทรนด์"
        else:
            reason = (f"เทรนด์{technical['trend_label']} แต่ราคายังไม่ย่อ "
                      f"(RSI={technical['rsi_value']}) — รอจังหวะเข้าที่ดีกว่า")

    else:
        entry_dir = "up" if entry == 1 else "down"

        if news_dir == entry_dir:
            # ข่าวยืนยันทางเดียวกับเทคนิค = สัญญาณที่ดีที่สุดของระบบนี้
            action = "BUY" if entry == 1 else "SELL"
            confidence = "สูง"
            reason = (f"เทคนิคให้จังหวะ ({technical['trend_label']}, RSI={technical['rsi_value']}) "
                      f"และข่าวชี้ทางเดียวกัน (net score {news_analysis['net_score']})")

        elif news_dir in ("up", "down"):
            # ข่าวชี้สวนทางเทคนิค = อันตราย ห้ามเข้า
            reason = (f"เทคนิคให้จังหวะ{'ซื้อ' if entry == 1 else 'ขาย'} "
                      f"แต่ข่าวชี้ทาง{'ขึ้น' if news_dir == 'up' else 'ลง'}สวนทางกัน — ไม่ควรเข้า")

        else:
            # ไม่มีข่าวยืนยัน (เป็นกลาง/ไม่มีข้อมูล) = เข้าได้แต่ความเชื่อมั่นลดลง
            action = "BUY" if entry == 1 else "SELL"
            confidence = "ปานกลาง"
            news_note = "ไม่มีข้อมูลข่าว" if news_dir == "no_data" else "ข่าวเป็นกลาง"
            reason = (f"เทคนิคให้จังหวะ ({technical['trend_label']}, RSI={technical['rsi_value']}) "
                      f"แต่{news_note} — ความเชื่อมั่นแค่ปานกลาง")

    result = {
        "pair": pair,
        "action": action,
        "confidence": confidence,
        "reason": reason,
    }

    # ถ้ามีสัญญาณเข้า -> แนบระยะ stop-loss แนะนำ (จาก ATR) เป็น pip
    # เตือนซ้ำ: ทุกออเดอร์ต้องมี stop-loss เสมอ ห้ามเปิดแบบไม่มี SL
    if action in ("BUY", "SELL"):
        sl_pips = technical["suggested_sl_distance"] / pip_size_of(pair)
        result["suggested_sl_pips"] = round(sl_pips, 1)
        result["price_now"] = technical["price_now"]

    return result


# ============================================
# ทดสอบรันไฟล์นี้เดี่ยวๆ ด้วยข้อมูลจำลอง
# ============================================
if __name__ == "__main__":
    print("ทดสอบ signal_combiner ด้วยสถานการณ์จำลอง 5 แบบ...\n")

    def mock_tech(trend, entry, rsi):
        labels = {"up": "ขาขึ้น (MA และ MACD เห็นตรงกัน)",
                  "down": "ขาลง (MA และ MACD เห็นตรงกัน)",
                  "none": "ไม่มีเทรนด์ชัด (MA กับ MACD ขัดกัน)"}
        return {"trend_direction": trend, "trend_label": labels[trend],
                "entry_signal": entry, "rsi_value": rsi,
                "suggested_sl_distance": 0.0020, "price_now": 1.1000}

    mock_news_up = {"net_score": 0.30}
    mock_news_down = {"net_score": -0.30}

    scenarios = [
        ("1. เทคนิคให้จังหวะซื้อ + ข่าวหนุน", mock_news_up, mock_tech("up", 1, 44.0)),
        ("2. เทคนิคให้จังหวะซื้อ + ข่าวสวนทาง", mock_news_down, mock_tech("up", 1, 44.0)),
        ("3. เทคนิคให้จังหวะซื้อ + ไม่มีข่าว", None, mock_tech("up", 1, 44.0)),
        ("4. เทรนด์ขึ้นแต่ราคายังไม่ย่อ", mock_news_up, mock_tech("up", 0, 62.0)),
        ("5. ไม่มีเทรนด์ชัด", mock_news_up, mock_tech("none", 0, 55.0)),
    ]

    for name, news, tech in scenarios:
        r = combine_signals("EURUSD", news, tech)
        print(f"{name}")
        print(f"   -> {r['action']} (ความเชื่อมั่น: {r['confidence']})")
        print(f"   -> เหตุผล: {r['reason']}\n")
