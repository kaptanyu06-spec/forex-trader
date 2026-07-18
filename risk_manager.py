"""
risk_manager.py
----------------
คำนวณขนาดสถานะ (position size) และประเมินความเสี่ยงตามหลัก Risk Management พื้นฐาน

หลักการสำคัญ: ไม่ว่าสัญญาณข่าวหรือ technical จะบอกว่าอะไร
"ขนาดออเดอร์" ต้องคำนวณจากเงินทุนและระยะ stop-loss เสมอ
ไม่ใช่เดาหรือใช้ lot คงที่
"""

import config


def calculate_position_size(
    account_balance: float,
    stop_loss_pips: float,
    pip_value_per_lot: float = 10.0,
    risk_percent: float = None,
) -> dict:
    """
    คำนวณขนาด lot ที่ควรเปิด โดยจำกัดความเสี่ยงไม่ให้เกิน risk_percent ของทุน

    Parameters:
    - account_balance: เงินทุนในบัญชี (หน่วยเดียวกับสกุลเงินบัญชี เช่น USD)
    - stop_loss_pips: ระยะ stop-loss เป็น pip (คำนวณจากกราฟ/ATR ไม่ใช่เดา)
    - pip_value_per_lot: มูลค่า 1 pip ต่อ 1 lot มาตรฐาน (ปกติ ~10 USD สำหรับคู่ที่ quote เป็น USD,
      ควรเช็คค่าจริงจากโบรกเกอร์ของคุณเพราะแต่ละคู่เงินไม่เท่ากัน)
    - risk_percent: เปอร์เซ็นต์ทุนที่ยอมเสี่ยง ถ้าไม่ระบุจะใช้ค่าจาก config.py

    คืนค่า dict พร้อมคำอธิบาย
    """
    risk_percent = risk_percent if risk_percent is not None else config.RISK_PER_TRADE_PERCENT

    if stop_loss_pips <= 0:
        raise ValueError("stop_loss_pips ต้องมากกว่า 0 (ต้องกำหนด stop-loss เสมอ)")

    risk_amount = account_balance * (risk_percent / 100)
    lot_size = risk_amount / (stop_loss_pips * pip_value_per_lot)

    return {
        "account_balance": account_balance,
        "risk_percent": risk_percent,
        "risk_amount": round(risk_amount, 2),
        "stop_loss_pips": stop_loss_pips,
        "recommended_lot_size": round(lot_size, 2),
        "note": (
            "ปัดขนาด lot ลงให้เข้ากับ step size ที่โบรกเกอร์อนุญาต (เช่น 0.01) "
            "และตรวจสอบ pip_value จริงของคู่เงินนั้นๆ กับโบรกเกอร์ก่อนใช้จริง"
        ),
    }


def check_daily_loss_limit(current_loss_percent: float) -> dict:
    """
    ตรวจสอบว่าขาดทุนวันนี้เกินลิมิตที่ตั้งไว้หรือยัง
    """
    limit = config.MAX_DAILY_LOSS_PERCENT
    exceeded = current_loss_percent >= limit

    return {
        "current_loss_percent": current_loss_percent,
        "daily_limit_percent": limit,
        "limit_exceeded": exceeded,
        "recommendation": (
            "หยุดเทรดวันนี้ทันที ห้ามฝืนเปิดออเดอร์เพิ่มเพื่อเอาคืน (revenge trading)"
            if exceeded
            else "ยังอยู่ในลิมิตที่ยอมรับได้ แต่ควรติดตามต่อเนื่อง"
        ),
    }


def check_weekly_loss_limit(current_loss_percent: float) -> dict:
    """
    ตรวจสอบว่าขาดทุนสัปดาห์นี้เกินลิมิตที่ตั้งไว้หรือยัง
    """
    limit = config.MAX_WEEKLY_LOSS_PERCENT
    exceeded = current_loss_percent >= limit

    return {
        "current_loss_percent": current_loss_percent,
        "weekly_limit_percent": limit,
        "limit_exceeded": exceeded,
        "recommendation": (
            "หยุดเทรดจนถึงสัปดาห์หน้า และทบทวนกลยุทธ์ก่อนกลับมาเทรดใหม่"
            if exceeded
            else "ยังอยู่ในลิมิตที่ยอมรับได้"
        ),
    }


def evaluate_signal_risk(net_sentiment_score: float, article_count: int) -> dict:
    """
    ประเมิน "ความน่าเชื่อถือ" ของสัญญาณข่าว ไม่ใช่คำแนะนำให้เข้าเทรด
    ยิ่งข่าวน้อย/คะแนนอ่อน ยิ่งควรระวังไม่พึ่งสัญญาณนี้อย่างเดียว

    คืนค่าระดับความเชื่อมั่น: ต่ำ / ปานกลาง / สูง
    """
    strength = abs(net_sentiment_score)

    if article_count < 3:
        confidence = "ต่ำ"
        reason = "จำนวนข่าวน้อยเกินไป สัญญาณอาจไม่น่าเชื่อถือ"
    elif strength < 0.15:
        confidence = "ต่ำ"
        reason = "คะแนน sentiment อ่อน ไม่ชัดเจนพอ"
    elif strength < 0.35:
        confidence = "ปานกลาง"
        reason = "มีความเอียงพอสมควร แต่ควรยืนยันด้วย technical analysis ร่วมด้วย"
    else:
        confidence = "สูง (เทียบกับสัญญาณข่าวอย่างเดียว)"
        reason = "คะแนน sentiment ชัดเจนและมีจำนวนข่าวสนับสนุนเพียงพอ"

    return {
        "confidence_level": confidence,
        "reason": reason,
        "warning": (
            "คำเตือน: สัญญาณจากข่าวเพียงอย่างเดียวไม่ควรใช้ตัดสินใจเข้าเทรด "
            "ควรใช้ร่วมกับ technical analysis, risk management ที่เข้มงวด "
            "และไม่ควรถือเป็นคำแนะนำการลงทุน"
        ),
    }
