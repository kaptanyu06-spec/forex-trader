"""
main.py
-------
จุดเริ่มต้นการรันระบบทั้งหมด

วิธีใช้งาน:
    python main.py

ระบบจะ:
1. ดึงข่าวที่เกี่ยวข้องกับคู่เงินที่ตั้งไว้ใน config.py แล้ววิเคราะห์ sentiment
2. ดึงราคาย้อนหลัง แล้ววิเคราะห์กราฟด้วย technical indicators
3. รวมสัญญาณข่าว + เทคนิค เป็นข้อสรุปเดียว (BUY / SELL / WAIT)
4. ถ้ามีสัญญาณเข้า: คำนวณระยะ SL (จาก ATR) และขนาด position ตาม risk management
5. พิมพ์สรุปผลออกทางหน้าจอ และบันทึกเป็นไฟล์ JSON

หมายเหตุ: ถ้ายังไม่ได้ใส่ NEWSAPI_KEY ระบบจะข้ามส่วนข่าว
แล้ววิเคราะห์เฉพาะส่วน technical ให้แทน
"""

import json
import os
from datetime import datetime

import config
import news_collector
import sentiment_analyzer
import risk_manager
import price_fetcher
import technical_analyzer
import signal_combiner


def collect_results() -> list:
    """
    รันการวิเคราะห์ทั้งหมด (ข่าว + เทคนิค + รวมสัญญาณ) แล้วคืนผลลัพธ์เป็น list
    — ฟังก์ชันนี้ถูกเรียกใช้ทั้งจากการรันทาง Terminal (main.py) และจากหน้าเว็บ (dashboard.py)
    """
    # 1. ดึงข่าว + วิเคราะห์ sentiment (ข้ามได้ถ้ายังไม่มี API key)
    sentiment_results = {}
    try:
        all_pair_news = news_collector.fetch_all_watched_news()
        for pair_news in all_pair_news:
            analysis = sentiment_analyzer.analyze_pair_news(pair_news)

            # ประเมินความน่าเชื่อถือของสัญญาณข่าว
            total_articles = (
                analysis["base_sentiment"]["article_count"]
                + analysis["quote_sentiment"]["article_count"]
            )
            risk_eval = risk_manager.evaluate_signal_risk(analysis["net_score"], total_articles)
            analysis["signal_risk_evaluation"] = risk_eval

            sentiment_results[analysis["pair"]] = analysis
    except ValueError as e:
        print(f"\n[ข้ามส่วนข่าว] {e}")
        print("จะวิเคราะห์เฉพาะส่วน technical ให้แทน\n")

    # 2. ดึงราคา + วิเคราะห์ technical
    print("\nกำลังดึงราคาย้อนหลัง...")
    all_prices = price_fetcher.fetch_all_watched_ohlc()

    technical_results = {}
    for pair, ohlc in all_prices.items():
        technical_results[pair] = technical_analyzer.analyze_pair_prices(pair, ohlc)

    # 3. รวมสัญญาณข่าว + เทคนิค เป็นข้อสรุปเดียวต่อคู่เงิน
    all_results = []
    for pair in config.WATCHED_PAIRS:
        news = sentiment_results.get(pair)          # None ถ้าไม่มีข่าว
        tech = technical_results.get(pair)          # None ถ้าดึงราคาไม่ได้
        combined = signal_combiner.combine_signals(pair, news, tech)

        all_results.append({
            "pair": pair,
            "news_sentiment": news,
            "technical": tech,
            "combined_signal": combined,
        })

    return all_results


def run_analysis():
    print("=" * 60)
    print("ระบบวิเคราะห์ Forex: ข่าว + เทคนิค + ความเสี่ยง")
    print(f"เวลา: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    all_results = collect_results()

    # พิมพ์สรุปผลทางหน้าจอ
    print_summary(all_results)

    # บันทึกผลลัพธ์เป็นไฟล์ JSON
    save_results(all_results)


def print_summary(results: list):
    print("\n" + "-" * 60)
    print("สรุปผลการวิเคราะห์รายคู่เงิน (ข่าว + เทคนิค)")
    print("-" * 60)

    for r in results:
        print(f"\n>> {r['pair']}")

        # ---- ส่วนข่าว (sentiment) ----
        news = r["news_sentiment"]
        if news:
            print(f"   [ข่าว] Bias: {news['bias']} (net score: {news['net_score']})")
            print(f"   [ข่าว] ความน่าเชื่อถือ: {news['signal_risk_evaluation']['confidence_level']} "
                  f"— {news['signal_risk_evaluation']['reason']}")
        else:
            print("   [ข่าว] ไม่มีข้อมูล (ยังไม่ได้ใส่ API key หรือดึงข่าวไม่สำเร็จ)")

        # ---- ส่วนเทคนิค ----
        tech = r["technical"]
        if tech:
            print(f"   [เทคนิค] เทรนด์: {tech['trend_label']}")
            print(f"   [เทคนิค] ราคาปัจจุบัน: {tech['price_now']}")
            print(f"   [เทคนิค] MA: {tech['ma_signal']}")
            print(f"   [เทคนิค] RSI: {tech['rsi_signal']}")
            print(f"   [เทคนิค] MACD: {tech['macd_signal']}")
            print(f"   [เทคนิค] Bollinger: {tech['bb_signal']}")
            print(f"   [เทคนิค] ระยะ SL แนะนำจาก ATR: {tech['suggested_sl_distance']} "
                  f"(= {config.ATR_SL_MULTIPLIER} x ATR)")
        else:
            print("   [เทคนิค] ไม่มีข้อมูล (ดึงราคาไม่สำเร็จ)")

        # ---- ข้อสรุปรวม (สัญญาณสุดท้าย) ----
        combined = r["combined_signal"]
        print(f"   >>> สรุป: {combined['action']}"
              + (f" (ความเชื่อมั่น: {combined['confidence']})" if combined["action"] != "WAIT" else ""))
        print(f"       เหตุผล: {combined['reason']}")

        # ถ้ามีสัญญาณเข้า -> แสดงขนาด position ที่เหมาะกับ SL ของสัญญาณนี้
        if combined["action"] in ("BUY", "SELL"):
            sizing = risk_manager.calculate_position_size(
                account_balance=config.ACCOUNT_BALANCE_EXAMPLE,
                stop_loss_pips=combined["suggested_sl_pips"],
            )
            print(f"       SL แนะนำ: {combined['suggested_sl_pips']} pip (จาก ATR) | "
                  f"ขนาด lot ตาม risk {sizing['risk_percent']}% ของทุน "
                  f"{config.ACCOUNT_BALANCE_EXAMPLE} USD: {sizing['recommended_lot_size']} lot")

    print("\n" + "=" * 60)
    print("คำเตือนสำคัญ: ผลวิเคราะห์นี้เป็นข้อมูลประกอบการตัดสินใจเท่านั้น")
    print("ไม่ใช่คำแนะนำการลงทุน และไม่รับประกันผลกำไร")
    print("=" * 60)


def save_results(results: list):
    os.makedirs(config.OUTPUT_DIR, exist_ok=True)
    filename = os.path.join(
        config.OUTPUT_DIR,
        f"analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    )
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"\nบันทึกผลลัพธ์ละเอียดไว้ที่: {filename}")
    cleanup_old_results()
    return filename


def cleanup_old_results():
    """
    ลบไฟล์ผลวิเคราะห์เก่า เก็บไว้แค่ล่าสุดตาม config.KEEP_ANALYSIS_FILES
    (ระบบรันอัตโนมัติทุก 2 ชม. ถ้าไม่ลบ ไฟล์จะเพิ่มขึ้นเรื่อยๆ ไม่มีที่สิ้นสุด)
    หมายเหตุ: ไม่แตะ paper_trades.json — สมุดเทรดจำลองเก็บถาวร
    """
    import glob
    files = sorted(glob.glob(os.path.join(config.OUTPUT_DIR, "analysis_*.json")))
    for old_file in files[:-config.KEEP_ANALYSIS_FILES]:
        try:
            os.remove(old_file)
        except OSError:
            pass  # ลบไม่ได้ก็ข้าม ไม่ใช่เรื่องใหญ่


if __name__ == "__main__":
    run_analysis()
