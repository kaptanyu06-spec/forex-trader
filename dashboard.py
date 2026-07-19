"""
dashboard.py
------------
หน้าเว็บ Dashboard สำหรับดูผลวิเคราะห์ (รันในเครื่องตัวเอง เปิดผ่าน browser)

วิธีใช้งาน:
    streamlit run dashboard.py

แล้ว browser จะเปิดหน้า Dashboard ให้อัตโนมัติ (ที่ http://localhost:8501)
กดปุ่ม "รันวิเคราะห์ใหม่" เพื่อดึงข่าว+ราคาล่าสุด หรือดูผลเก่าจากเมนูซ้ายมือ

หน้าตา: ธีมมืดโทนน้ำเงินเข้ม การ์ด KPI + ป้ายสัญญาณสี (ผู้ใช้เลือกแนวนี้ 2026-07-19)
สีธีมหลักอยู่ที่ .streamlit/config.toml — สีของกราฟอยู่ข้างล่างนี้
"""

import html
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
# สีทั้งหมดของหน้านี้ (ตรวจผ่านเกณฑ์คนตาบอดสีบนพื้นมืด #121a2b แล้ว — อย่าเปลี่ยนมั่ว)
# ============================================
COLOR_PRICE = "#3987e5"    # น้ำเงิน = ราคาปิด
COLOR_MA_FAST = "#c98500"  # เหลืองทอง = เส้นค่าเฉลี่ยเร็ว
COLOR_MA_SLOW = "#9085e9"  # ม่วง = เส้นค่าเฉลี่ยช้า

COLOR_GOOD = "#0ca30c"     # เขียว = BUY / ชนะ / บวก
COLOR_BAD = "#e66767"      # แดง = SELL / แพ้ / ลบ
COLOR_MUTED = "#8b94a7"    # เทา = WAIT / ข้อความรอง

SURFACE_CARD = "#121a2b"   # พื้นการ์ด (ตรงกับ secondaryBackgroundColor ใน config.toml)
GRID_COLOR = "#232d45"     # เส้นตารางในกราฟ (จางๆ)

st.set_page_config(page_title="Forex Analyzer", page_icon="📈", layout="wide")

# ============================================
# CSS แต่งหน้าตา: การ์ด, ป้ายสัญญาณ, ตาราง (ฉีดครั้งเดียวตอนเปิดหน้า)
# ============================================
st.markdown("""
<style>
/* ---- การ์ด KPI แถวบน (เรียงเป็น grid ย่อ-ขยายตามจอ มือถือก็สวย) ---- */
.kpi-row { display:grid; grid-template-columns:repeat(auto-fit, minmax(160px, 1fr));
           gap:12px; margin:4px 0 8px 0; }
.kpi-card { background:linear-gradient(160deg, #16203a 0%, #121a2b 100%);
            border:1px solid rgba(255,255,255,.08); border-radius:14px;
            padding:14px 16px; }
.kpi-top { display:flex; align-items:center; gap:8px; margin-bottom:8px; }
.kpi-icon { width:30px; height:30px; border-radius:9px; display:flex;
            align-items:center; justify-content:center; font-size:15px; }
.kpi-label { color:#8b94a7; font-size:.8rem; }
.kpi-value { font-size:1.7rem; font-weight:700; line-height:1.15; }
.kpi-sub { font-size:.75rem; color:#8b94a7; margin-top:4px; }

/* ---- ป้ายสัญญาณ (BUY/SELL/WAIT และสถานะไม้) ---- */
.pill { display:inline-block; padding:2px 10px; border-radius:99px;
        font-size:.8rem; font-weight:600; white-space:nowrap; }
.pill-buy  { background:rgba(12,163,12,.16);  color:#3ecf3e; }
.pill-sell { background:rgba(230,103,103,.16); color:#ff8f8f; }
.pill-wait { background:rgba(139,148,167,.16); color:#aab2c5; }

/* ---- ตารางแบบการ์ด ---- */
.card-table { width:100%; border-collapse:collapse; background:#121a2b;
              border:1px solid rgba(255,255,255,.08); border-radius:14px;
              overflow:hidden; font-size:.88rem; }
.card-table th { text-align:left; color:#8b94a7; font-weight:600; font-size:.78rem;
                 padding:10px 14px; border-bottom:1px solid rgba(255,255,255,.08);
                 background:rgba(255,255,255,.02); white-space:nowrap; }
.card-table td { padding:9px 14px; border-bottom:1px solid rgba(255,255,255,.05);
                 vertical-align:middle; }
.card-table tr:last-child td { border-bottom:none; }
.td-num { font-variant-numeric:tabular-nums; }
.td-muted { color:#8b94a7; font-size:.8rem; }
.table-scroll { overflow-x:auto; border-radius:14px; }

/* ---- หัวข้อส่วน ---- */
.sec-title { font-size:1.05rem; font-weight:700; margin:20px 0 10px 0;
             display:flex; align-items:center; gap:8px; }
.sec-chip { font-size:.72rem; font-weight:600; color:#8b94a7;
            border:1px solid rgba(255,255,255,.12); padding:1px 9px; border-radius:99px; }

/* ---- กล่องรายละเอียดรายคู่ (expander) ให้เป็นการ์ดมน ---- */
div[data-testid="stExpander"] details { background:#121a2b;
    border:1px solid rgba(255,255,255,.08) !important; border-radius:14px; }
</style>
""", unsafe_allow_html=True)


# ============================================
# ฟังก์ชันช่วยโหลด/รันผลวิเคราะห์
# ============================================

def list_saved_results() -> list:
    """
    คืนรายชื่อไฟล์ผลวิเคราะห์ใน output/ (ใหม่สุดก่อน)
    เอาเฉพาะ analysis_*.json — ไฟล์อื่นในโฟลเดอร์ (paper_trades, news_cache)
    ไม่ใช่ผลวิเคราะห์ เปิดแล้วพัง
    "analysis_latest.json" (ผลล่าสุด — ตัวเดียวที่มีบนคลาวด์) ให้อยู่บนสุดเสมอ
    """
    if not os.path.isdir(config.OUTPUT_DIR):
        return []
    files = [f for f in os.listdir(config.OUTPUT_DIR)
             if f.startswith("analysis_") and f.endswith(".json")
             and f != "analysis_latest.json"]
    files = sorted(files, reverse=True)
    if os.path.exists(os.path.join(config.OUTPUT_DIR, "analysis_latest.json")):
        files.insert(0, "analysis_latest.json")
    return files


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
    """กราฟราคาปิด (เส้น + พื้นไล่เฉดใต้เส้น) + เส้น MA สองเส้น — แกนเดียว มี tooltip"""
    df = get_chart_data(pair).reset_index()
    df = df.rename(columns={df.columns[0]: "เวลา"})

    # แปลงเป็นรูปแบบยาว (long format) เพื่อให้ altair แยกสีตามชื่อเส้นได้
    long_df = df.melt(id_vars="เวลา", var_name="เส้น", value_name="ราคา")

    series_order = ["ราคาปิด", "MA เร็ว", "MA ช้า"]
    colors = [COLOR_PRICE, COLOR_MA_FAST, COLOR_MA_SLOW]

    hover = alt.selection_point(fields=["เวลา"], nearest=True, on="mouseover", empty=False)

    # พื้นไล่เฉดใต้เส้นราคา (ฟ้า -> จางหาย) ให้เหมือนแดชบอร์ดตัวอย่าง
    area = alt.Chart(df).mark_area(
        line=False,
        color=alt.Gradient(
            gradient="linear",
            stops=[alt.GradientStop(color="rgba(57,135,229,0.35)", offset=1),
                   alt.GradientStop(color="rgba(57,135,229,0.0)", offset=0)],
            x1=1, x2=1, y1=1, y2=0,
        ),
    ).encode(
        x=alt.X("เวลา:T", title=None),
        y=alt.Y("ราคาปิด:Q", title=None, scale=alt.Scale(zero=False)),
    )

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

    rule = alt.Chart(long_df).mark_rule(color=COLOR_MUTED).encode(
        x="เวลา:T",
        opacity=alt.condition(hover, alt.value(0.4), alt.value(0)),
    )

    return (area + lines + points + rule).properties(height=320).configure(
        background="transparent"
    ).configure_view(stroke=None).configure_axis(
        gridColor=GRID_COLOR, labelColor=COLOR_MUTED,
        tickColor=GRID_COLOR, domainColor=GRID_COLOR,
    ).configure_legend(labelColor="#c7cede")


# ============================================
# ชิ้นส่วน HTML: การ์ด KPI, ป้ายสัญญาณ, ตารางการ์ด
# ============================================

def kpi_card(icon: str, accent: str, label: str, value: str, sub: str = "") -> str:
    """การ์ดตัวเลขสรุป 1 ใบ: ไอคอนในกรอบสีจางๆ + ตัวเลขใหญ่ + คำอธิบายเล็ก"""
    sub_html = f'<div class="kpi-sub">{sub}</div>' if sub else ""
    return f'''<div class="kpi-card">
      <div class="kpi-top">
        <div class="kpi-icon" style="background:{accent}26;">{icon}</div>
        <div class="kpi-label">{label}</div>
      </div>
      <div class="kpi-value">{value}</div>
      {sub_html}</div>'''


def kpi_row(cards: list):
    st.markdown('<div class="kpi-row">' + "".join(cards) + "</div>", unsafe_allow_html=True)


PILL = {
    "BUY": '<span class="pill pill-buy">▲ BUY</span>',
    "SELL": '<span class="pill pill-sell">▼ SELL</span>',
    "WAIT": '<span class="pill pill-wait">⏸ WAIT</span>',
}
TRADE_PILL = {
    "open": '<span class="pill pill-wait">⏳ เปิดอยู่</span>',
    "won": '<span class="pill pill-buy">✓ ชนะ</span>',
    "lost": '<span class="pill pill-sell">✗ แพ้</span>',
}


def card_table(headers: list, rows: list):
    """ตารางสไตล์การ์ดมืด — rows เป็น list ของ list (HTML ในเซลล์ได้)"""
    head = "".join(f"<th>{h}</th>" for h in headers)
    body = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in row) + "</tr>" for row in rows)
    st.markdown(f'<div class="table-scroll"><table class="card-table">'
                f"<thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>",
                unsafe_allow_html=True)


def section(title: str, chip: str = ""):
    chip_html = f'<span class="sec-chip">{chip}</span>' if chip else ""
    st.markdown(f'<div class="sec-title">{title}{chip_html}</div>', unsafe_allow_html=True)


# ============================================
# แถบข้าง (Sidebar): ปุ่มรันใหม่ + เลือกดูผลเก่า
# ============================================

st.sidebar.title("📈 Forex Analyzer")

if st.sidebar.button("🔄 รันวิเคราะห์ใหม่", type="primary", width="stretch"):
    with st.spinner("กำลังดึงข่าวและราคาล่าสุด... (ใช้เวลา ~1 นาที)"):
        results = analysis_engine.collect_results()
        analysis_engine.save_results(results)
        # หมายเหตุ: ไม่แตะสมุด paper trading จากหน้านี้ — สมุดตัวจริงเป็นหน้าที่
        # ของระบบอัตโนมัติบน GitHub Actions เท่านั้น (กันข้อมูลชนกัน)
    st.rerun()  # โหลดหน้าใหม่เพื่อให้ไฟล์ล่าสุดขึ้นในรายการ

saved_files = list_saved_results()
if not saved_files:
    st.info("ยังไม่มีผลวิเคราะห์ — กดปุ่ม 'รันวิเคราะห์ใหม่' ที่แถบซ้ายมือเพื่อเริ่ม")
    st.stop()

selected_file = st.sidebar.selectbox(
    "ดูผลวิเคราะห์ครั้งไหน",
    saved_files,
    format_func=lambda f: (
        "ล่าสุด (อัปเดตทุก 1 ชม.)" if f == "analysis_latest.json"
        # แปลงชื่อไฟล์ analysis_20260716_202402.json -> "16/07/2026 20:24"
        else datetime.strptime(f.replace("analysis_", "").replace(".json", ""), "%Y%m%d_%H%M%S")
        .strftime("%d/%m/%Y %H:%M")
    ),
)
st.sidebar.caption(f"มีผลวิเคราะห์เก็บไว้ {len(saved_files)} ครั้ง")
st.sidebar.warning(
    "ผลวิเคราะห์นี้เป็นข้อมูลประกอบการตัดสินใจเท่านั้น "
    "ไม่ใช่คำแนะนำการลงทุน และไม่รับประกันผลกำไร"
)

results = load_result_file(selected_file)

# ============================================
# ส่วนบน: หัวเรื่อง + การ์ดสรุปสัญญาณ
# ============================================

# เวลาอัปเดตของไฟล์ที่กำลังดู (แสดงบนหัวเรื่อง)
mtime = os.path.getmtime(os.path.join(config.OUTPUT_DIR, selected_file))
updated_txt = datetime.fromtimestamp(mtime).strftime("%d/%m/%Y %H:%M")

st.markdown(f'''<div style="display:flex;align-items:baseline;gap:12px;flex-wrap:wrap;">
  <span style="font-size:1.7rem;font-weight:800;">ศูนย์วิเคราะห์ Forex</span>
  <span style="color:#8b94a7;font-size:.85rem;">ข่าว + เทคนิค · อัปเดต {updated_txt}</span>
</div>''', unsafe_allow_html=True)

actions = [r["combined_signal"]["action"] for r in results]
kpi_row([
    kpi_card("▲", COLOR_GOOD, "สัญญาณ BUY", str(actions.count("BUY")),
             f"จาก {len(results)} ตัวที่ติดตาม"),
    kpi_card("▼", COLOR_BAD, "สัญญาณ SELL", str(actions.count("SELL")),
             f"จาก {len(results)} ตัวที่ติดตาม"),
    kpi_card("⏸", COLOR_MUTED, "รอจังหวะ (WAIT)", str(actions.count("WAIT")),
             "ไม่มีเทรนด์ชัด = ไม่เทรด"),
])

# ตารางสรุปสัญญาณทุกคู่เงิน
sig_rows = []
for r in results:
    sig = r["combined_signal"]
    tech = r["technical"]
    price = f'<span class="td-num">{tech["price_now"]}</span>' if tech else "-"
    sig_rows.append([
        f"<b>{r['pair']}</b>",
        PILL.get(sig["action"], sig["action"]),
        sig["confidence"],
        price,
        f'<span class="td-muted">{html.escape(str(sig["reason"]))}</span>',
    ])
card_table(["คู่เงิน", "สัญญาณ", "ความเชื่อมั่น", "ราคาล่าสุด", "เหตุผล"], sig_rows)

# ============================================
# ส่วนกลาง: สถิติ Paper Trading (เทรดจำลอง)
# ============================================

section("Paper Trading", "เทรดจำลอง — ไม่มีเงินจริง")

paper_trades = paper_trader.load_trades()
paper_stats = paper_trader.summarize(paper_trades)

ret = paper_stats["sim_return_pct"]
ret_color = COLOR_GOOD if ret >= 0 else COLOR_BAD
kpi_row([
    kpi_card("⏳", COLOR_MA_FAST, "เปิดค้างอยู่", str(paper_stats["open_count"])),
    kpi_card("🎯", COLOR_PRICE, "ปิดแล้ว", f"{paper_stats['closed_count']} ไม้",
             "เป้าพิสูจน์ระบบ: 20 ไม้ใน 1 เดือน"),
    kpi_card("🏆", COLOR_MA_SLOW, "อัตราชนะ", f"{paper_stats['win_rate_pct']}%",
             "เป้าจาก backtest: ~40%"),
    kpi_card("💰", ret_color, "ผลตอบแทนจำลอง",
             f'<span style="color:{ret_color}">{ret:+}%</span>',
             "จำลองทุนโดยเสี่ยง 1% ต่อไม้"),
])

if paper_trades:
    trade_rows = []
    for t in reversed(paper_trades):       # ใหม่สุดขึ้นก่อน
        r_val = t.get("net_r", "-")
        if isinstance(r_val, (int, float)):
            r_color = COLOR_GOOD if r_val > 0 else COLOR_BAD
            r_cell = f'<span class="td-num" style="color:{r_color}">{r_val:+.2f}</span>'
        else:
            r_cell = "-"
        trade_rows.append([
            f"<b>{t['pair']}</b>",
            PILL.get(t["direction"], t["direction"]),
            TRADE_PILL.get(t["status"], t["status"]),
            f'<span class="td-num">{t["entry_price"]}</span>',
            f'<span class="td-num">{t["sl_price"]}</span>',
            f'<span class="td-num">{t["tp_price"]}</span>',
            r_cell,
            f'<span class="td-muted">{t["entry_time"][:16].replace("T", " ")} UTC</span>',
        ])
    card_table(["คู่เงิน", "ทิศทาง", "สถานะ", "ราคาเข้า", "SL", "TP", "ผล (R)", "เวลาเข้า"],
               trade_rows)
else:
    st.caption("ยังไม่มีเทรดจำลอง — ระบบจะบันทึกให้อัตโนมัติเมื่อเกิดสัญญาณ BUY/SELL "
               "(รันผ่านปุ่มด้านซ้าย หรือเปิด scheduler ทิ้งไว้)")

# ============================================
# ส่วนล่าง: รายละเอียดรายคู่เงิน (กดเปิดดูทีละคู่)
# ============================================

section("รายละเอียดรายคู่เงิน", "กดเปิดดูทีละคู่")

ACTION_LABEL = {"BUY": "🟢 BUY", "SELL": "🔴 SELL", "WAIT": "⏸️ WAIT"}
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
