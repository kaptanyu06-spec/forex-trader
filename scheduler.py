"""
scheduler.py
------------
รันระบบวิเคราะห์อัตโนมัติเป็นรอบๆ (ตาม config.SCHEDULER_INTERVAL_HOURS)
พร้อมบันทึก paper trading และแจ้งเตือน Telegram เมื่อมีเหตุการณ์สำคัญ

วิธีใช้:
    python scheduler.py           # รันวนไปเรื่อยๆ (หยุดด้วย Ctrl+C)
    python scheduler.py --once    # รันแค่รอบเดียวแล้วจบ (ไว้ทดสอบ)

สิ่งที่ทำทุกรอบ:
1. วิเคราะห์ข่าว + เทคนิค + รวมสัญญาณ (เหมือน main.py)
2. อัปเดต paper trading: ปิดเทรดจำลองที่โดน SL/TP, เปิดไม้ใหม่ตามสัญญาณ
3. แจ้งเตือน Telegram เมื่อ: มีสัญญาณใหม่ / เทรดจำลองปิด (ถ้าตั้งค่าไว้)

ข้อควรรู้:
- ต้องเปิดหน้าต่าง Terminal นี้ทิ้งไว้ (ปิดเครื่อง/พับจอ = หยุดทำงาน)
- ตลาด Forex ปิดเสาร์-อาทิตย์ ระบบยังรันได้แต่จะไม่มีสัญญาณใหม่
"""

import sys
import time
from datetime import datetime, timedelta, timezone

THAI_TZ = timezone(timedelta(hours=7))   # เวลาไทย (UTC+7) ใช้ตัดวันในรายงาน

import config
import main as engine
import paper_trader
import notifier
import risk_manager
import broker_oanda
import broker_capital
from signal_combiner import pip_size_of


def _thai_date(iso_time: str) -> str:
    """แปลงเวลา ISO (UTC) เป็นวันที่แบบไทย เช่น '18/07' — ไว้เทียบว่าเป็นของวันนี้ไหม"""
    return datetime.fromisoformat(iso_time).astimezone(THAI_TZ).strftime("%d/%m")


def build_daily_report() -> str:
    """
    สรุปประจำวันฉบับอ่านง่าย ส่งเข้า Telegram วันละครั้ง (แม้วันที่ไม่มีเทรด)
    เนื้อหา: เทรดของวันนี้ / ไม้ที่ค้างอยู่ / สถิติสะสมเทียบเป้า 20 ไม้ / ยอดบัญชี demo
    """
    trades = paper_trader.load_trades()
    stats = paper_trader.summarize(trades)
    today = datetime.now(THAI_TZ).strftime("%d/%m")

    opened_today = [t for t in trades if _thai_date(t["entry_time"]) == today]
    closed_today = [t for t in trades if t["status"] != "open"
                    and t.get("exit_time") and _thai_date(t["exit_time"]) == today]
    open_now = [t for t in trades if t["status"] == "open"]

    lines = [f"📒 รายงานประจำวัน {today}", ""]

    # เทรดของวันนี้
    if not opened_today and not closed_today:
        lines.append("วันนี้ไม่มีเทรดใหม่/ปิด (ไม่มีสัญญาณเข้าเงื่อนไข หรือตลาดปิด)")
    else:
        for t in opened_today:
            lines.append(f"🆕 เปิด {t['direction']} {t['pair']} @ {t['entry_price']}")
            lines.append(f"    📰 {t.get('news_note', 'ไม่มีข้อมูลข่าว')}")
        for t in closed_today:
            emoji = "✅" if t["status"] == "won" else "❌"
            lines.append(f"{emoji} ปิด {t['direction']} {t['pair']} ({t['net_r']:+}R)")

    # ไม้ที่ยังค้างอยู่
    if open_now:
        lines.append("")
        lines.append(f"ไม้ค้าง {len(open_now)} ไม้: "
                     + ", ".join(f"{t['direction']} {t['pair']}" for t in open_now))

    # สถิติสะสม + ความคืบหน้าเทียบเป้าที่ตกลงกัน (1 เดือน + ปิด 20 ไม้)
    lines += [
        "",
        f"สะสม: ปิดแล้ว {stats['closed_count']}/20 ไม้ตามเป้า | "
        f"ชนะ {stats['win_rate_pct']}% | {stats['total_r']:+}R "
        f"({stats['sim_return_pct']:+}% ของทุนจำลอง)",
    ]

    # ยอดบัญชี demo จริงจากโบรก (ถ้าตั้งค่าไว้)
    try:
        if broker_capital.is_configured():
            acct = broker_capital.get_account_summary(broker_capital.login())
            lines.append(f"💰 Capital.com demo: {acct['balance']:,.2f} {acct['currency']}")
    except Exception:
        pass   # ดึงยอดไม่ได้ (เช่น เน็ตสะดุด) ไม่ต้องพังทั้งรายงาน

    lines += ["", "(เทรดจำลองเท่านั้น ไม่ใช่คำแนะนำการลงทุน)"]
    return "\n".join(lines)


def run_cycle():
    """รัน 1 รอบเต็ม: วิเคราะห์ -> paper trading -> แจ้งเตือน"""
    print("\n" + "=" * 60)
    print(f"รอบวิเคราะห์อัตโนมัติ: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    # 1. วิเคราะห์และบันทึกผล
    results = engine.collect_results()
    engine.save_results(results)

    # 2. อัปเดต paper trading
    paper = paper_trader.process_results(results)
    stats = paper["stats"]

    # 3. สรุปสั้นๆ ทางหน้าจอ
    signals = [r for r in results if r["combined_signal"]["action"] != "WAIT"]
    print(f"\nสัญญาณรอบนี้: {len(signals)} คู่ | "
          f"paper trade เปิดใหม่ {len(paper['opened'])} / ปิด {len(paper['closed'])} ไม้")
    print(f"สถิติ paper สะสม: เปิดค้าง {stats['open_count']} | ปิดแล้ว {stats['closed_count']} "
          f"(ชนะ {stats['win_rate_pct']}%) | ผลรวม {stats['total_r']}R "
          f"= {stats['sim_return_pct']}% ของทุนจำลอง")

    # 3.5 ส่งออเดอร์เดียวกันเข้าบัญชีทดลองของโบรกเกอร์ (ขั้น 5.4)
    #     รองรับ 2 โบรก: ใส่คีย์ของอันไหน อันนั้นทำงาน (ไม่ใส่ = ลิสต์ว่าง ข้ามเฉยๆ)
    broker_notes = []
    for broker in (broker_oanda, broker_capital):
        broker_notes += broker.mirror_paper_trades(paper["opened"])
    for note in broker_notes:
        print(note)

    # 4. แจ้งเตือน Telegram เมื่อมีเหตุการณ์ (สัญญาณใหม่ / เทรดปิด)
    lines = []
    for t in paper["opened"]:
        # คำนวณ lot แนะนำ เผื่อผู้ใช้อยากกดเทรดตามใน MT5 demo ด้วยมือ
        sl_pips = t["sl_dist"] / pip_size_of(t["pair"])
        sizing = risk_manager.calculate_position_size(
            account_balance=config.ACCOUNT_BALANCE_EXAMPLE,
            stop_loss_pips=sl_pips,
        )
        lines.append(f"🆕 เปิด paper trade: {t['direction']} {t['pair']} @ {t['entry_price']}\n"
                     f"   SL {t['sl_price']} / TP {t['tp_price']} (เชื่อมั่น: {t['confidence']})\n"
                     f"   📰 {t.get('news_note', 'ไม่มีข้อมูลข่าว')}\n"
                     f"   lot แนะนำ: {sizing['recommended_lot_size']} "
                     f"(ทุน {config.ACCOUNT_BALANCE_EXAMPLE} USD เสี่ยง {sizing['risk_percent']}%)")
    for t in paper["closed"]:
        emoji = "✅" if t["status"] == "won" else "❌"
        lines.append(f"{emoji} ปิด paper trade: {t['direction']} {t['pair']} "
                     f"{'ชนะ' if t['status'] == 'won' else 'แพ้'} ({t['net_r']:+}R)")
    lines.extend(broker_notes)   # ผลส่งออเดอร์ demo แจ้งใน Telegram ด้วย

    if lines:
        header = f"📊 Forex Analyzer {datetime.now().strftime('%d/%m %H:%M')}\n\n"
        footer = (f"\n\nสถิติสะสม: ชนะ {stats['win_rate_pct']}% "
                  f"จาก {stats['closed_count']} ไม้ | {stats['sim_return_pct']}%\n"
                  f"(เทรดจำลองเท่านั้น ไม่ใช่คำแนะนำการลงทุน)")
        sent = notifier.send(header + "\n".join(lines) + footer)
        print(f"แจ้งเตือน Telegram: {'ส่งแล้ว' if sent else 'ข้าม (ยังไม่ตั้งค่า/ส่งไม่สำเร็จ)'}")

    # 5. รายงานสรุปประจำวัน — ส่งเฉพาะรอบที่ตรงชั่วโมงที่ตั้งไว้ (วันละครั้ง)
    if datetime.now(timezone.utc).hour == config.DAILY_REPORT_UTC_HOUR:
        sent = notifier.send(build_daily_report())
        print(f"รายงานประจำวัน: {'ส่งแล้ว' if sent else 'ข้าม (ยังไม่ตั้งค่า/ส่งไม่สำเร็จ)'}")


if __name__ == "__main__":
    run_once = "--once" in sys.argv
    interval_sec = config.SCHEDULER_INTERVAL_HOURS * 3600

    print(f"เริ่ม scheduler: รันทุก {config.SCHEDULER_INTERVAL_HOURS} ชั่วโมง "
          f"(หยุดด้วย Ctrl+C){' — โหมดทดสอบรอบเดียว' if run_once else ''}")
    if not notifier.is_configured():
        print("หมายเหตุ: ยังไม่ได้ตั้งค่า Telegram — ระบบจะทำงานปกติแต่ไม่แจ้งเตือน "
              "(ดูวิธีตั้งค่าที่หัวไฟล์ notifier.py)")

    while True:
        try:
            run_cycle()
        except Exception as e:
            # รอบไหนพัง (เช่น เน็ตหลุด) ให้ข้ามไปรอรอบถัดไป ไม่ต้องล้มทั้งโปรแกรม
            print(f"\n[ผิดพลาดรอบนี้ จะลองใหม่รอบหน้า] {e}")

        if run_once:
            break

        next_run = datetime.now().strftime("%H:%M")
        print(f"\nรอรอบถัดไปอีก {config.SCHEDULER_INTERVAL_HOURS} ชม. "
              f"(รอบนี้จบเวลา {next_run}) ... กด Ctrl+C เพื่อหยุด")
        try:
            time.sleep(interval_sec)
        except KeyboardInterrupt:
            print("\nหยุด scheduler แล้ว")
            break
