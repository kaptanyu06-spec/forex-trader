"""
config.py
---------
ไฟล์เก็บการตั้งค่าทั้งหมดของระบบ
ไม่ต้องแก้ไขไฟล์อื่นเลย ถ้าต้องการเปลี่ยนค่าต่างๆ ให้มาแก้ที่นี่ที่เดียว
"""

import os

# ============================================
# 1. API KEYS (ต้องไปสมัครฟรีเองที่เว็บผู้ให้บริการ)
# ============================================
# NewsAPI: สมัครฟรีที่ https://newsapi.org/register
#   -> ได้ 100 requests/วัน ฟรี (พอสำหรับใช้ทดสอบ/ส่วนตัว)
# ค่าจริงอยู่ใน secrets_local.py (ในเครื่อง) หรือ GitHub Secrets (บนคลาวด์)
NEWSAPI_KEY = os.environ.get("NEWSAPI_KEY", "")

# รหัส PIN หน้าแดชบอร์ด (ปล่อยว่าง = ไม่ล็อก เปิดดูได้เลย)
# ตั้งค่าจริง: ในเครื่อง -> secrets_local.py | บนคลาวด์ -> Secrets ของ Streamlit
DASHBOARD_PIN = os.environ.get("DASHBOARD_PIN", "")

# ============================================
# 2. คู่เงินที่ต้องการติดตาม (แก้ไขเพิ่ม/ลดได้)
# ============================================
# แนะนำสำหรับผู้เริ่มต้น: คู่เงินหลัก (majors) เพราะ
# - สภาพคล่องสูง สเปรดต่ำ (ต้นทุนต่อออเดอร์ถูกกว่า)
# - ข่าวภาษาอังกฤษเยอะ -> ส่วนวิเคราะห์ข่าวทำงานได้ดี
# - พฤติกรรมราคา "เรียบ" กว่าคู่ cross อย่าง AUDNZD ที่แกว่งแคบและข่าวน้อย
WATCHED_PAIRS = ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "XAUUSD"]
# XAUUSD = ทองคำ (เพิ่ม 2026-07-18 หลัง backtest ผ่าน: PF 1.24, +5.4%/ปี บน 1h)
# หมายเหตุ: ทองต้องใช้ทุนใหญ่กว่า forex มากถ้าจะเทรดจริงตามกฎ 1% (ดูรายละเอียดใน README)

# คำค้นหาข่าวที่เกี่ยวข้องกับแต่ละสกุลเงิน (ใช้จับคู่กับคู่เงินด้านบน)
CURRENCY_KEYWORDS = {
    "USD": ["Federal Reserve", "Fed rate", "US inflation", "US CPI", "Non-Farm Payroll", "FOMC"],
    "EUR": ["European Central Bank", "ECB rate", "Eurozone inflation", "EU GDP"],
    "JPY": ["Bank of Japan", "BOJ rate", "Japan inflation", "yen intervention"],
    "GBP": ["Bank of England", "BOE rate", "UK inflation", "UK GDP"],
    "AUD": ["Reserve Bank of Australia", "RBA rate", "Australia inflation", "Australia GDP"],
    "CAD": ["Bank of Canada", "BOC rate", "Canada inflation", "Canada GDP"],
    "NZD": ["Reserve Bank of New Zealand", "RBNZ rate", "New Zealand inflation"],
    # XAU = ทองคำ (สินทรัพย์ปลอดภัย — ข่าวที่ขยับราคาทอง)
    "XAU": ["gold price", "gold demand", "central bank gold", "safe haven gold"],
}

# ============================================
# 3. การตั้งค่าความเสี่ยง (Risk Management)
# ============================================
# เปอร์เซ็นต์ของทุนที่ยอมเสี่ยงต่อ 1 ออเดอร์ (มาตรฐานทั่วไป: 1-2%)
RISK_PER_TRADE_PERCENT = 1.0

# ขาดทุนสูงสุดต่อวันที่ยอมรับได้ (%) — ถ้าถึงลิมิตนี้ ระบบจะแนะนำให้หยุดเทรดวันนั้น
MAX_DAILY_LOSS_PERCENT = 3.0

# ขาดทุนสูงสุดต่อสัปดาห์ที่ยอมรับได้ (%)
MAX_WEEKLY_LOSS_PERCENT = 6.0

# ============================================
# 4. การตั้งค่า Technical Analysis
# ============================================
# ขนาดแท่งเทียนที่ใช้วิเคราะห์: "1h" = 1 ชั่วโมง, "4h" = 4 ชั่วโมง, "1d" = รายวัน
PRICE_TIMEFRAME = "1h"

# ดึงราคาย้อนหลังเท่าไร (ต้องพอให้ indicator คำนวณได้ อย่างน้อย ~200 แท่ง)
PRICE_LOOKBACK = "60d"

# Moving Average: เส้นเร็ว/เส้นช้า (จำนวนแท่ง)
MA_FAST_PERIOD = 20
MA_SLOW_PERIOD = 50

# RSI
RSI_PERIOD = 14
RSI_OVERBOUGHT = 70   # เกินนี้ = ซื้อมากเกิน
RSI_OVERSOLD = 30     # ต่ำกว่านี้ = ขายมากเกิน

# ATR (ใช้คำนวณระยะ stop-loss)
ATR_PERIOD = 14
ATR_SL_MULTIPLIER = 1.5   # SL แนะนำ = 1.5 เท่าของ ATR

# Bollinger Bands
BB_PERIOD = 20

# เงินทุนตัวอย่างสำหรับคำนวณ position size (แก้เป็นทุนจริงของคุณเมื่อพร้อม)
# แนะนำ: เริ่มจาก Demo account ก่อนเสมอ — ตัวเลขนี้ใช้แค่แสดงตัวอย่างการคำนวณ
ACCOUNT_BALANCE_EXAMPLE = 1000

# ============================================
# 4.1 การตั้งค่า Backtest
# ============================================
# ดึงข้อมูลย้อนหลังเท่าไรสำหรับ backtest (1h ดึงได้สูงสุด ~730 วัน)
BACKTEST_LOOKBACK = "1y"

# Take-profit เป็นกี่เท่าของระยะ stop-loss (Risk:Reward ratio)
# 2.0 = เสี่ยง 1 เพื่อหวัง 2 -> ชนะแค่ ~40% ก็กำไรแล้ว
BACKTEST_TP_RR = 2.0

# ต้นทุนสเปรดโดยประมาณต่อออเดอร์ (pip) — คู่เงินหลักปกติ ~1 pip
BACKTEST_SPREAD_PIPS = 1.0

# สเปรดเฉพาะตัว (pip) สำหรับตัวที่แพงกว่าค่ามาตรฐานข้างบน
# ทองคำ: สเปรด ~$0.35/ออนซ์ = 3.5 pip (1 pip ทอง = $0.10)
PAIR_SPREAD_PIPS = {
    "XAUUSD": 3.5,
}

# ============================================
# 5. การตั้งค่าอื่นๆ
# ============================================
# ดึงข่าวย้อนหลังกี่วัน
NEWS_LOOKBACK_DAYS = 2

# โฟลเดอร์เก็บผลลัพธ์
OUTPUT_DIR = "output"

# ============================================
# 6. Scheduler + แจ้งเตือน Telegram (ขั้น paper trading)
# ============================================
# รันวิเคราะห์อัตโนมัติทุกกี่ชั่วโมง (ใช้กับ scheduler.py ในเครื่อง —
# ส่วนบนคลาวด์ตั้งใน .github/workflows/trader.yml: ทุก 1 ชม. ตรงจังหวะแท่งเทียน 1h)
SCHEDULER_INTERVAL_HOURS = 1

# จำผลวิเคราะห์ข่าวไว้ใช้ซ้ำกี่ชั่วโมง ก่อนดึงข่าวใหม่
# เหตุผล: รันทุก 1 ชม. x 8 requests = 192/วัน เกินโควตา NewsAPI ฟรี (100/วัน)
# แต่ข่าวมหภาคไม่เปลี่ยนรายชั่วโมง -> ดึงใหม่ทุก 3 ชม. = ~64 requests/วัน (ปลอดภัย)
NEWS_CACHE_HOURS = 3
NEWS_CACHE_FILE = os.path.join(OUTPUT_DIR, "news_cache.json")

# รายงานสรุปประจำวันทาง Telegram: ส่งในรอบรันของชั่วโมงนี้ (เวลา UTC)
# 13 UTC = ประมาณ 20:07 เวลาไทย (รอบรันอยู่ที่นาทีที่ 7 ของชั่วโมง)
DAILY_REPORT_UTC_HOUR = 13

# Telegram Bot สำหรับแจ้งเตือนสัญญาณ (ไม่ใส่ก็ได้ ระบบจะข้ามการแจ้งเตือน)
# วิธีสมัคร: คุยกับ @BotFather ใน Telegram -> /newbot -> ได้ token
# แล้วคุยกับ @userinfobot -> ได้ chat id ของตัวเอง
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

# ไฟล์เก็บบันทึก paper trading (เทรดจำลอง ไม่ใช้เงินจริง)
PAPER_LOG_FILE = os.path.join(OUTPUT_DIR, "paper_trades.json")

# เก็บไฟล์ผลวิเคราะห์ (analysis_*.json) ล่าสุดกี่ไฟล์ — เก่ากว่านั้นลบทิ้งอัตโนมัติ
# 60 ไฟล์ = ประมาณ 5 วัน (รันทุก 2 ชม. = 12 ไฟล์/วัน)
KEEP_ANALYSIS_FILES = 60

# ============================================
# 7. โบรกเกอร์ OANDA (ขั้น 5.4 — เชื่อม Demo account)
# ============================================
# ทำไมเลือก OANDA: ผู้ใช้ใช้ Mac ซึ่งต่อ MT5 ด้วย Python โดยตรงไม่ได้ (Windows เท่านั้น)
# OANDA มี REST API ใช้ได้ทุกระบบ + มีบัญชีทดลอง (practice) ฟรี
#
# วิธีสมัคร (ฟรี ไม่ต้องฝากเงิน):
# 1. สมัครบัญชีทดลองที่ https://www.oanda.com (เลือก demo/practice account)
# 2. เข้าหน้าจัดการบัญชี -> Manage API Access -> สร้าง Personal Access Token
# 3. เอา token กับหมายเลขบัญชี (เช่น 101-011-1234567-001) มาใส่ด้านล่าง
#
# OANDA_ENV: "practice" = บัญชีทดลอง (เงินปลอม) เท่านั้น
# ระบบตั้งใจไม่รองรับ "live" ในตอนนี้ — ต้องผ่าน paper trading 1-3 เดือนก่อน
OANDA_API_KEY = os.environ.get("OANDA_API_KEY", "")
OANDA_ACCOUNT_ID = os.environ.get("OANDA_ACCOUNT_ID", "")
OANDA_ENV = "practice"

# ============================================
# 7.5 โบรกเกอร์ Capital.com (ทางเลือกแทน OANDA — ใส่คีย์อันไหน อันนั้นทำงาน)
# ============================================
# เพิ่มเข้ามาเพราะติดปัญหาล็อกอิน OANDA — Capital.com สมัคร demo ง่ายกว่า
# วิธีสมัครอยู่ที่หัวไฟล์ broker_capital.py
#
# CAPITAL_ENV: "demo" = บัญชีทดลอง (เงินปลอม) เท่านั้น
# ระบบตั้งใจไม่รองรับ "live" ในตอนนี้ — ต้องผ่าน paper trading 1-3 เดือนก่อน
CAPITAL_API_KEY = os.environ.get("CAPITAL_API_KEY", "")
CAPITAL_IDENTIFIER = os.environ.get("CAPITAL_IDENTIFIER", "")     # อีเมลที่ใช้สมัคร
CAPITAL_API_PASSWORD = os.environ.get("CAPITAL_API_PASSWORD", "") # รหัสผ่านประจำคีย์ API
CAPITAL_ENV = "demo"

# ============================================
# 8. โหลดรหัสลับจากไฟล์ในเครื่อง — ต้องอยู่ท้ายไฟล์เสมอ เพื่อทับค่าว่างด้านบน
# secrets_local.py มีเฉพาะในเครื่องเรา (ไม่ถูกอัปโหลดขึ้น GitHub — อยู่ใน .gitignore)
# ส่วนบนคลาวด์ (GitHub Actions) ไฟล์นี้ไม่มี ระบบใช้ค่าจาก GitHub Secrets ผ่าน
# environment variables แทน
# ============================================
try:
    from secrets_local import *  # noqa: F401,F403
except ImportError:
    pass
