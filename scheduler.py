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
from datetime import datetime

import config
import main as engine
import paper_trader
import notifier
import risk_manager
import broker_oanda
from signal_combiner import pip_size_of


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

    # 3.5 ส่งออเดอร์เดียวกันเข้าบัญชีทดลอง OANDA (ขั้น 5.4)
    #     ถ้ายังไม่ได้ใส่คีย์ OANDA จะได้ลิสต์ว่างกลับมา = ข้ามส่วนนี้เฉยๆ
    oanda_notes = broker_oanda.mirror_paper_trades(paper["opened"])
    for note in oanda_notes:
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
                     f"   lot แนะนำ: {sizing['recommended_lot_size']} "
                     f"(ทุน {config.ACCOUNT_BALANCE_EXAMPLE} USD เสี่ยง {sizing['risk_percent']}%)")
    for t in paper["closed"]:
        emoji = "✅" if t["status"] == "won" else "❌"
        lines.append(f"{emoji} ปิด paper trade: {t['direction']} {t['pair']} "
                     f"{'ชนะ' if t['status'] == 'won' else 'แพ้'} ({t['net_r']:+}R)")
    lines.extend(oanda_notes)   # ผลส่งออเดอร์ demo แจ้งใน Telegram ด้วย

    if lines:
        header = f"📊 Forex Analyzer {datetime.now().strftime('%d/%m %H:%M')}\n\n"
        footer = (f"\n\nสถิติสะสม: ชนะ {stats['win_rate_pct']}% "
                  f"จาก {stats['closed_count']} ไม้ | {stats['sim_return_pct']}%\n"
                  f"(เทรดจำลองเท่านั้น ไม่ใช่คำแนะนำการลงทุน)")
        sent = notifier.send(header + "\n".join(lines) + footer)
        print(f"แจ้งเตือน Telegram: {'ส่งแล้ว' if sent else 'ข้าม (ยังไม่ตั้งค่า/ส่งไม่สำเร็จ)'}")


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
