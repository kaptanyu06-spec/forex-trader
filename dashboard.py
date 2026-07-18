"""
dashboard.py
------------
หน้าเว็บ Dashboard สำหรับดูผลวิเคราะห์ (รันในเครื่องตัวเอง เปิดผ่าน browser)

วิธีใช้งาน:
    streamlit run dashboard.py

แล้ว browser จะเปิดหน้า Dashboard ให้อัตโนมัติ (ที่ http://localhost:8501)
กดปุ่ม "รันวิเคราะห์ใหม่" เพื่อดึงข่าว+ราคาล่าสุด หรือดูผลเก่าจากเมนูซ้ายมือ
"""

import json
import os
from datetime import datetime

import altair as alt
import pandas as pd
import streamlit as st

import config
import main as analysis_engine
import paper_trader
import price_fetcher
import technical_analyzer

# ============================================
# สีของกราฟ (ตรวจผ่านเกณฑ์คนตาบอดสีแล้ว — อย่าเปลี่ยนมั่ว)
# ============================================
COLOR_PRICE = "#1170aa"    # น้ำเงิน = ราคาปิด
COLOR_MA_FAST = "#fc7d0b"  # ส้ม = เส้นค่าเฉลี่ยเร็ว
COLOR_MA_SLOW = "#6f63bb"  # ม่วง = เส้นค่าเฉลี่ยช้า

st.set_page_config(page_title="Forex Analyzer", page_icon="📈", layout="wide")


# ============================================
# ฟังก์ชันช่วยโหลด/รันผลวิเคราะห์
# ============================================

def list_saved_results() -> list:
    """คืนรายชื่อไฟล์ผลวิเคราะห์เก่าใน output/ (ใหม่สุดก่อน)"""
    if not os.path.isdir(config.OUTPUT_DIR):
        return []
    files = [f for f in os.listdir(config.OUTPUT_DIR) if f.endswith(".json")]
    return sorted(files, reverse=True)


def load_result_file(filename: str) -> list:
    with open(os.path.join(config.OUTPUT_DIR, filename), encoding="utf-8") as f:
        return json.load(f)


@st.cache_data(ttl=3600, show_spinner=False)
def get_chart_data(pair: str) -> pd.DataFrame:
    """ดึงราคาสำหรับวาดกราฟ (จำผลไว้ 1 ชั่วโมง จะได้ไม่ดึงซ้ำทุกครั้งที่กดหน้าจอ)"""
    ohlc = price_fetcher.fetch_ohlc(pair)
    df = ohlc[["close"]].copy()
    df["MA เร็ว"] = technical_analyzer.moving_average(ohlc["close"], config.MA_FAST_PERIOD)
    df["MA ช้า"] = technical_analyzer.moving_average(ohlc["close"], config.MA_SLOW_PERIOD)
    df = df.rename(columns={"close": "ราคาปิด"})
    return df.dropna()


def price_chart(pair: str) -> alt.Chart:
    """กราฟราคาปิด + เส้น MA สองเส้น (แกนเดียว เส้นบาง มี tooltip)"""
    df = get_chart_data(pair).reset_index()
    df = df.rename(columns={df.columns[0]: "เวลา"})

    # แปลงเป็นรูปแบบยาว (long format) เพื่อให้ altair แยกสีตามชื่อเส้นได้
    long_df = df.melt(id_vars="เวลา", var_name="เส้น", value_name="ราคา")

    series_order = ["ราคาปิด", "MA เร็ว", "MA ช้า"]
    colors = [COLOR_PRICE, COLOR_MA_FAST, COLOR_MA_SLOW]

    hover = alt.selection_point(fields=["เวลา"], nearest=True, on="mouseover", empty=False)

    lines = alt.Chart(long_df).mark_line(strokeWidth=2).encode(
        x=alt.X("เวลา:T", title=None),
        y=alt.Y("ราคา:Q", title=None, scale=alt.Scale(zero=False)),
        color=alt.Color("เส้น:N", sort=series_order,
                        scale=alt.Scale(domain=series_order, range=colors),
                        legend=alt.Legend(orient="top", title=None)),
    )

    # จุด + เส้นตั้งตอนเอาเมาส์ชี้ (crosshair + tooltip)
    points = lines.mark_point(size=64).encode(
        opacity=alt.condition(hover, alt.value(1), alt.value(0)),
        tooltip=[alt.Tooltip("เวลา:T", format="%d %b %H:%M"),
                 alt.Tooltip("เส้น:N"),
                 alt.Tooltip("ราคา:Q", format=".5f")],
    ).add_params(hover)

    rule = alt.Chart(long_df).mark_rule(color="#9a9a97").encode(
        x="เวลา:T",
        opacity=alt.condition(hover, alt.value(0.4), alt.value(0)),
    )

    return (lines + points + rule).properties(height=320)


# ============================================
# แถบข้าง (Sidebar): ปุ่มรันใหม่ + เลือกดูผลเก่า
# ============================================

st.sidebar.title("📈 Forex Analyzer")

if st.sidebar.button("🔄 รันวิเคราะห์ใหม่", type="primary", width="stretch"):
    with st.spinner("กำลังดึงข่าวและราคาล่าสุด... (ใช้เวลา ~1 นาที)"):
        results = analysis_engine.collect_results()
        analysis_engine.save_results(results)
        paper_trader.process_results(results)   # อัปเดตสมุด paper trading ด้วย
    st.rerun()  # โหลดหน้าใหม่เพื่อให้ไฟล์ล่าสุดขึ้นในรายการ

saved_files = list_saved_results()
if not saved_files:
    st.info("ยังไม่มีผลวิเคราะห์ — กดปุ่ม 'รันวิเคราะห์ใหม่' ที่แถบซ้ายมือเพื่อเริ่ม")
    st.stop()

selected_file = st.sidebar.selectbox(
    "ดูผลวิเคราะห์ครั้งไหน",
    saved_files,
    format_func=lambda f: (
        # แปลงชื่อไฟล์ analysis_20260716_202402.json -> "16/07/2026 20:24"
        datetime.strptime(f.replace("analysis_", "").replace(".json", ""), "%Y%m%d_%H%M%S")
        .strftime("%d/%m/%Y %H:%M")
        if f.startswith("analysis_") else f
    ),
)
st.sidebar.caption(f"มีผลวิเคราะห์เก็บไว้ {len(saved_files)} ครั้ง")
st.sidebar.warning(
    "ผลวิเคราะห์นี้เป็นข้อมูลประกอบการตัดสินใจเท่านั้น "
    "ไม่ใช่คำแนะนำการลงทุน และไม่รับประกันผลกำไร"
)

results = load_result_file(selected_file)

# ============================================
# ส่วนบน: สรุปภาพรวม
# ============================================

st.title("ผลวิเคราะห์ Forex: ข่าว + เทคนิค")

actions = [r["combined_signal"]["action"] for r in results]
col1, col2, col3 = st.columns(3)
col1.metric("สัญญาณ BUY", actions.count("BUY"))
col2.metric("สัญญาณ SELL", actions.count("SELL"))
col3.metric("รอจังหวะ (WAIT)", actions.count("WAIT"))

# ตารางสรุปสัญญาณทุกคู่เงิน
ACTION_LABEL = {"BUY": "🟢 BUY", "SELL": "🔴 SELL", "WAIT": "⏸️ WAIT"}
summary_rows = []
for r in results:
    sig = r["combined_signal"]
    tech = r["technical"]
    summary_rows.append({
        "คู่เงิน": r["pair"],
        "สัญญาณ": ACTION_LABEL.get(sig["action"], sig["action"]),
        "ความเชื่อมั่น": sig["confidence"],
        "ราคาล่าสุด": tech["price_now"] if tech else "-",
        "เหตุผล": sig["reason"],
    })
st.dataframe(pd.DataFrame(summary_rows), width="stretch", hide_index=True)

# ============================================
# ส่วนกลาง: สถิติ Paper Trading (เทรดจำลอง)
# ============================================

st.subheader("Paper Trading (เทรดจำลอง — ไม่มีเงินจริง)")

paper_trades = paper_trader.load_trades()
paper_stats = paper_trader.summarize(paper_trades)

p1, p2, p3, p4 = st.columns(4)
p1.metric("เปิดค้างอยู่", paper_stats["open_count"])
p2.metric("ปิดแล้ว", f"{paper_stats['closed_count']} ไม้")
p3.metric("อัตราชนะ", f"{paper_stats['win_rate_pct']}%")
p4.metric("ผลตอบแทนจำลอง", f"{paper_stats['sim_return_pct']}%",
          help="จำลองทุนโดยเสี่ยง 1% ต่อไม้ ตามกฎ risk management")

if paper_trades:
    paper_df = pd.DataFrame([{
        "คู่เงิน": t["pair"],
        "ทิศทาง": t["direction"],
        "สถานะ": {"open": "⏳ เปิดอยู่", "won": "✅ ชนะ", "lost": "❌ แพ้"}[t["status"]],
        "ราคาเข้า": t["entry_price"],
        "SL": t["sl_price"],
        "TP": t["tp_price"],
        "ผล (R)": t.get("net_r", "-"),
        "เวลาเข้า": t["entry_time"][:16].replace("T", " ") + " UTC",
    } for t in reversed(paper_trades)])       # ใหม่สุดขึ้นก่อน
    st.dataframe(paper_df, width="stretch", hide_index=True)
else:
    st.caption("ยังไม่มีเทรดจำลอง — ระบบจะบันทึกให้อัตโนมัติเมื่อเกิดสัญญาณ BUY/SELL "
               "(รันผ่านปุ่มด้านซ้าย หรือเปิด scheduler ทิ้งไว้)")

# ============================================
# ส่วนล่าง: รายละเอียดรายคู่เงิน (กดเปิดดูทีละคู่)
# ============================================

st.subheader("รายละเอียดรายคู่เงิน")

for r in results:
    sig = r["combined_signal"]
    with st.expander(f"{r['pair']} — {ACTION_LABEL.get(sig['action'], sig['action'])}"):
        left, right = st.columns([3, 2])

        # ---- ฝั่งซ้าย: กราฟราคา + MA ----
        with left:
            try:
                st.altair_chart(price_chart(r["pair"]), width="stretch")
                with st.popover("ดูข้อมูลกราฟเป็นตาราง"):
                    st.dataframe(get_chart_data(r["pair"]).tail(50))
            except Exception as e:
                st.warning(f"วาดกราฟไม่สำเร็จ: {e}")

        # ---- ฝั่งขวา: รายละเอียดข่าว + เทคนิค ----
        with right:
            st.markdown(f"**ข้อสรุป: {sig['action']}**"
                        + (f" (ความเชื่อมั่น: {sig['confidence']})" if sig["action"] != "WAIT" else ""))
            st.caption(sig["reason"])
            if sig["action"] in ("BUY", "SELL"):
                st.markdown(f"- SL แนะนำ (จาก ATR): **{sig['suggested_sl_pips']} pip**")

            news = r["news_sentiment"]
            st.markdown("**ข่าว (sentiment)**")
            if news:
                st.markdown(f"- {news['bias']}")
                st.markdown(f"- Net score: `{news['net_score']}` | "
                            f"ความน่าเชื่อถือ: {news['signal_risk_evaluation']['confidence_level']}")
                st.markdown(f"- ข่าว {news['base_currency']}: "
                            f"{news['base_sentiment']['article_count']} ชิ้น | "
                            f"ข่าว {news['quote_currency']}: "
                            f"{news['quote_sentiment']['article_count']} ชิ้น")
            else:
                st.markdown("- ไม่มีข้อมูลข่าวในรอบนี้")

            tech = r["technical"]
            st.markdown("**เทคนิค (กลยุทธ์: ตามเทรนด์ + รอย่อ)**")
            if tech:
                st.markdown(f"- เทรนด์: {tech.get('trend_label', tech.get('technical_bias', '-'))}")
                st.markdown(f"- MA: {tech['ma_signal']}")
                st.markdown(f"- RSI: {tech['rsi_signal']}")
                st.markdown(f"- MACD: {tech['macd_signal']}")
                st.markdown(f"- Bollinger: {tech['bb_signal']}")
            else:
                st.markdown("- ไม่มีข้อมูลราคาในรอบนี้")
