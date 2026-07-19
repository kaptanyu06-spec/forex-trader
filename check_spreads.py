"""
check_spreads.py — วัดสเปรดจริงจาก Capital.com แล้วตัดสินว่าควรเพิ่มคู่เงินไหม

ที่มา (2026-07-18): backtest คู่ใหม่ USDCAD/EURJPY/GBPJPY ได้ PF ก้ำกึ่ง (1.09-1.12)
เมื่อใช้สเปรดประมาณการ 1.8/1.8/2.5 pip — ตกลงกันว่าวันจันทร์ตลาดเปิด
ให้วัดสเปรดจริงจากโบรก ถ้าถูกกว่าที่ประมาณจน backtest กลับมา PF > ~1.15 ค่อยพิจารณาเพิ่ม

วิธีใช้ (รันตอนตลาดเปิด เช่น จันทร์ช่วงบ่าย-ค่ำเวลาไทย ซึ่งตลาดลอนดอนเปิด สเปรดแคบสุด):
    python3 check_spreads.py              # วัด 12 รอบ ห่างรอบละ 25 วิ (~5 นาที) แล้วรัน backtest
    python3 check_spreads.py 20 30       # วัด 20 รอบ ห่างรอบละ 30 วิ

ผลลัพธ์:
1. ตารางสเปรดจริง (มัธยฐาน) เทียบกับค่าที่ใช้ใน backtest
2. backtest v2/1h/1ปี ของคู่ตัวเลือก ด้วยสเปรดจริงที่วัดได้ + คำตัดสินตามเกณฑ์ PF >= 1.15

คำเตือน: เครื่องมือประกอบการตัดสินใจเท่านั้น ไม่รับประกันผลกำไร
"""

import sys
import time
import statistics

import config
import broker_capital
from signal_combiner import pip_size_of, spread_pips_of

# คู่ที่วัด: คู่ที่เทรดอยู่ (เช็คว่าสมมติฐานสเปรดไม่หลอกตัวเอง) + คู่ตัวเลือกที่รอตัดสิน
CANDIDATE_PAIRS = ["USDCAD", "EURJPY", "GBPJPY"]
PAIRS_TO_CHECK = list(config.WATCHED_PAIRS) + CANDIDATE_PAIRS

# เกณฑ์ตัดสินใจที่ตกลงกันไว้ 2026-07-18
PF_THRESHOLD = 1.15


def measure_spreads(samples: int, interval_sec: int) -> dict:
    """วัดสเปรด (หน่วย pip) หลายรอบ แล้วคืน {pair: มัธยฐาน} — นับเฉพาะตอนตลาดเปิด (TRADEABLE)"""
    headers = broker_capital.login()
    collected = {p: [] for p in PAIRS_TO_CHECK}

    for round_no in range(1, samples + 1):
        line = [f"รอบ {round_no}/{samples}:"]
        for pair in PAIRS_TO_CHECK:
            try:
                m = broker_capital.get_market(headers, pair)
            except Exception as e:
                line.append(f"{pair}=ผิดพลาด({e})")
                continue
            spread_pips = (m["ask"] - m["bid"]) / pip_size_of(pair)
            if m["status"] == "TRADEABLE":
                collected[pair].append(spread_pips)
                line.append(f"{pair}={spread_pips:.1f}")
            else:
                line.append(f"{pair}=ปิด")
        print("  ".join(line), flush=True)
        if round_no < samples:
            time.sleep(interval_sec)

    return {p: statistics.median(v) for p, v in collected.items() if v}


def report_vs_assumption(medians: dict):
    """ตารางเทียบ: สเปรดจริง vs ค่าที่ backtest ใช้"""
    print(f"\n{'คู่':<10}{'สเปรดจริง(มัธยฐาน)':>20}{'ที่ backtest ใช้':>18}  หมายเหตุ")
    print("-" * 62)
    # ค่าประมาณการของคู่ตัวเลือก (จากการทดสอบ 2026-07-18)
    assumed = {"USDCAD": 1.8, "EURJPY": 1.8, "GBPJPY": 2.5}
    for pair in PAIRS_TO_CHECK:
        if pair not in medians:
            print(f"{pair:<10}{'วัดไม่ได้ (ตลาดปิด?)':>20}")
            continue
        used = assumed.get(pair, spread_pips_of(pair))
        real = medians[pair]
        note = "จริงถูกกว่าที่คิด" if real < used else ("ใกล้เคียง" if real <= used * 1.2 else "จริงแพงกว่าที่คิด!")
        print(f"{pair:<10}{real:>20.2f}{used:>18.2f}  {note}")


def backtest_candidates(medians: dict):
    """รัน backtest v2/1h ของคู่ตัวเลือกด้วยสเปรดจริง แล้วตัดสินตามเกณฑ์ PF"""
    import backtester

    print(f"\nรัน backtest v2/1h/1ปี ด้วยสเปรดจริง (เกณฑ์เพิ่มคู่: PF >= {PF_THRESHOLD})")
    for pair in CANDIDATE_PAIRS:
        if pair not in medians:
            print(f"  [ข้าม] {pair}: ไม่มีค่าสเปรดจริง")
            continue
        # ใส่สเปรดจริงลงตาราง config ชั่วคราว เพื่อให้ simulate ใช้ค่านี้
        config.PAIR_SPREAD_PIPS[pair] = round(medians[pair], 2)
        try:
            ohlc = backtester.fetch_for_timeframe(pair, "1h")
            result = backtester.simulate(pair, backtester.signals_v2_trend_pullback(ohlc))
        except Exception as e:
            print(f"  [ข้าม] {pair}: {e}")
            continue
        pf = result.get("profit_factor") or 0.0
        verdict = "ผ่านเกณฑ์ — พิจารณาเพิ่มได้" if pf >= PF_THRESHOLD else "ไม่ผ่าน — ยังไม่เพิ่ม"
        print(f"  {pair}: สเปรด {medians[pair]:.2f} pip | เทรด {result.get('total_trades')} "
              f"| Win {result.get('win_rate_pct', 0):.0f}% | PF {pf:.2f} "
              f"| กำไรสุทธิ {result.get('net_return_pct', 0):+.1f}% | {verdict}")

    print("\nข้อควรระวัง: EURJPY/GBPJPY เป็นคู่ cross — calc_size/calc_units ของ broker")
    print("ทั้งสองยังคิดเป็นหน่วยสกุลเงินหลักแบบคู่ USD ต้องแก้ให้แปลงค่าเงิน quote ก่อนเทรดจริง")


def main():
    samples = int(sys.argv[1]) if len(sys.argv) > 1 else 12
    interval = int(sys.argv[2]) if len(sys.argv) > 2 else 25

    if not broker_capital.is_configured():
        print("ยังไม่ได้ตั้งค่าคีย์ Capital.com — ใส่ใน secrets_local.py ก่อน")
        return

    print(f"วัดสเปรดจาก Capital.com: {samples} รอบ ห่างรอบละ {interval} วิ (~{samples*interval//60} นาที)\n")
    medians = measure_spreads(samples, interval)

    if not medians:
        print("\nวัดไม่ได้เลยสักคู่ — ตลาดน่าจะปิดอยู่ ลองใหม่ตอนตลาดเปิด (จันทร์-ศุกร์)")
        return

    report_vs_assumption(medians)
    backtest_candidates(medians)
    print("\nคำเตือน: เครื่องมือประกอบการตัดสินใจเท่านั้น ไม่รับประกันผลกำไร")


if __name__ == "__main__":
    main()
