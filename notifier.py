"""
notifier.py
-----------
ส่งข้อความแจ้งเตือนเข้า Telegram

วิธีตั้งค่า (ทำครั้งเดียว ฟรี):
1. เปิด Telegram คุยกับ @BotFather -> พิมพ์ /newbot -> ตั้งชื่อบอท
   จะได้ "token" หน้าตาแบบ 123456:ABC-DEF...
2. คุยกับ @userinfobot -> จะบอก chat id ของเรา (ตัวเลข)
3. เอาทั้งสองค่าไปใส่ใน config.py (TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID)
4. สำคัญ: ต้องกด Start คุยกับบอทของเราเองก่อน 1 ครั้ง บอทถึงจะส่งหาเราได้

ถ้ายังไม่ตั้งค่า ระบบจะข้ามการแจ้งเตือนเฉยๆ (ไม่พังส่วนอื่น)

ทดสอบ: python notifier.py  (จะส่งข้อความทดสอบถ้าตั้งค่าแล้ว)
"""

import requests

import config


def is_configured() -> bool:
    """เช็คว่าใส่ token/chat id แล้วหรือยัง"""
    return bool(config.TELEGRAM_BOT_TOKEN and config.TELEGRAM_CHAT_ID)


def send(text: str) -> bool:
    """
    ส่งข้อความเข้า Telegram — คืน True ถ้าส่งสำเร็จ
    ถ้ายังไม่ตั้งค่า หรือส่งไม่สำเร็จ จะคืน False เฉยๆ (ไม่ทำให้ระบบหลักพัง)
    """
    if not is_configured():
        return False

    url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        resp = requests.post(
            url,
            json={"chat_id": config.TELEGRAM_CHAT_ID, "text": text},
            timeout=15,
        )
        if not resp.ok:
            print(f"   [แจ้งเตือน] Telegram ตอบกลับผิดพลาด: {resp.status_code} {resp.text[:100]}")
        return resp.ok
    except requests.RequestException as e:
        print(f"   [แจ้งเตือน] ส่ง Telegram ไม่สำเร็จ: {e}")
        return False


if __name__ == "__main__":
    if not is_configured():
        print("ยังไม่ได้ตั้งค่า TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID ใน config.py")
        print("อ่านวิธีตั้งค่าที่หัวไฟล์ notifier.py นี้")
    else:
        ok = send("ทดสอบการแจ้งเตือนจากระบบวิเคราะห์ Forex ✅")
        print("ส่งสำเร็จ!" if ok else "ส่งไม่สำเร็จ — เช็ค token/chat id อีกครั้ง")
