"""
dashboard.py
------------
หน้าเว็บ Dashboard สำหรับดูผลวิเคราะห์ (รันในเครื่องตัวเอง เปิดผ่าน browser)

วิธีใช้งาน:
    streamlit run dashboard.py

แล้ว browser จะเปิดหน้า Dashboard ให้อัตโนมัติ (ที่ http://localhost:8501)
กดปุ่ม "รันวิเคราะห์ใหม่" เพื่อดึงข่าว+ราคาล่าสุด หรือดูผลเก่าจากเมนูซ้ายมือ

หน้าตา: ธีมมืดโทนน้ำเงินเข้ม การ์ด KPI + ไอคอน SVG + ชุดกราฟผลเทรด
(ผู้ใช้เลือกแนวนี้ 2026-07-19) สีธีมหลักอยู่ที่ .streamlit/config.toml

แบ่ง 2 แท็บ (ผู้ใช้ขอแยกกราฟกำไรออกจากกราฟเทรด 2026-07-19):
แท็บ "สัญญาณ & ตลาด" — ของเดิม: สัญญาณ, ข่าว+RSI, รายละเอียดรายคู่
  (กราฟรายคู่เป็นแท่งเทียนเขียว/แดง + MA แบบกราฟเทรดทั่วไปที่ผู้ใช้คุ้นจาก MT5)
แท็บ "วิเคราะห์กำไร" — กราฟผลเทรดล้วนๆ:
  1. กำไรสะสม % เทียบทุน (ติ๊กเลือกคู่ได้) + ตัวเลขกำไรรวมใหญ่
  2. ผลรายไม้ (แท่ง) + R สะสม (เส้น)
  3. พาเรโต: แท่งกำไรต่อคู่เรียงเก่งสุด -> แย่สุด + เส้นสะสมรวมทีละคู่
"""

import html
import json
import os
from datetime import datetime, timedelta, timezone

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
# กราฟเงิน (กำไร/ขาดทุน) ใช้เขียว/แดงตามธรรมเนียมเทรด — ตำแหน่งแท่งเหนือ/ใต้ศูนย์
# ช่วยบอกทิศซ้ำอีกชั้น คนตาบอดสีจึงอ่านได้จากตำแหน่งแม้แยกสีไม่ออก
# ============================================
COLOR_PRICE = "#3987e5"    # น้ำเงิน = ราคาปิด / เส้นสะสม / ฝั่งบวกของกราฟตลาด
COLOR_MA_FAST = "#c98500"  # เหลืองทอง = เส้นค่าเฉลี่ยเร็ว
COLOR_MA_SLOW = "#9085e9"  # ม่วง = เส้นค่าเฉลี่ยช้า

COLOR_GOOD = "#0ca30c"     # เขียว = BUY / ชนะ / กำไร
COLOR_BAD = "#e66767"      # แดง = SELL / แพ้ / ขาดทุน
COLOR_MUTED = "#8b94a7"    # เทา = WAIT / ข้อความรอง

SURFACE_CARD = "#121a2b"   # พื้นการ์ด (ตรงกับ secondaryBackgroundColor ใน config.toml)
GRID_COLOR = "#232d45"     # เส้นตารางในกราฟ (จางๆ)

# สีประจำคู่เงิน (สำหรับกราฟเส้นรายคู่ — ตรวจชุดสีบนพื้นมืดผ่านแล้วเช่นกัน)
# น้ำเงินสงวนไว้ให้เส้น "รวม" — สีคู่เงินจึงไม่มีน้ำเงิน
PAIR_COLORS = ["#199e70", "#c98500", "#9085e9", "#d55181", "#d95926"]
TOTAL_LINE = "รวมที่เลือก"  # ชื่อเส้นผลรวมในกราฟกำไรสะสม

st.set_page_config(page_title="Forex Analyzer", page_icon="📈", layout="wide")

# ============================================
# ไอคอน SVG ลายเส้น (แบบเดียวกับไอคอนชุด Lucide — วาดด้วย stroke ตามสีที่ครอบ)
# ============================================
_ICON_PATHS = {
    "trend-up": '<polyline points="22 7 13.5 15.5 8.5 10.5 2 17"/><polyline points="16 7 22 7 22 13"/>',
    "trend-down": '<polyline points="22 17 13.5 8.5 8.5 13.5 2 7"/><polyline points="16 17 22 17 22 11"/>',
    "pause": '<rect x="6" y="4" width="4" height="16" rx="1"/><rect x="14" y="4" width="4" height="16" rx="1"/>',
    "hourglass": ('<path d="M5 22h14"/><path d="M5 2h14"/>'
                  '<path d="M17 22v-4.172a2 2 0 0 0-.586-1.414L12 12l-4.414 4.414A2 2 0 0 0 7 17.828V22"/>'
                  '<path d="M7 2v4.172a2 2 0 0 0 .586 1.414L12 12l4.414-4.414A2 2 0 0 0 17 6.172V2"/>'),
    "target": '<circle cx="12" cy="12" r="10"/><circle cx="12" cy="12" r="6"/><circle cx="12" cy="12" r="2"/>',
    "trophy": ('<path d="M6 9H4.5a2.5 2.5 0 0 1 0-5H6"/><path d="M18 9h1.5a2.5 2.5 0 0 0 0-5H18"/>'
               '<path d="M4 22h16"/><path d="M10 14.66V17c0 .55-.47.98-.97 1.21C7.85 18.75 7 20.24 7 22"/>'
               '<path d="M14 14.66V17c0 .55.47.98.97 1.21C16.15 18.75 17 20.24 17 22"/>'
               '<path d="M18 2H6v7a6 6 0 0 0 12 0V2Z"/>'),
    "coins": ('<circle cx="8" cy="8" r="6"/><path d="M18.09 10.37A6 6 0 1 1 10.34 18"/>'
              '<path d="M7 6h1v4"/><path d="m16.71 13.88.7.71-2.82 2.82"/>'),
    "check": '<polyline points="20 6 9 17 4 12"/>',
    "x": '<line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>',
}


def icon_svg(name: str, size: int = 15) -> str:
    """คืนไอคอน SVG ขนาดเล็ก ใช้สีตามตัวครอบ (currentColor)"""
    return (f'<svg viewBox="0 0 24 24" width="{size}" height="{size}" fill="none" '
            f'stroke="currentColor" stroke-width="2" stroke-linecap="round" '
            f'stroke-linejoin="round" style="vertical-align:-2px">{_ICON_PATHS[name]}</svg>')


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
            align-items:center; justify-content:center; flex:none; }
.kpi-label { color:#8b94a7; font-size:.8rem; }
.kpi-value { font-size:1.7rem; font-weight:700; line-height:1.15; }
.kpi-sub { font-size:.75rem; color:#8b94a7; margin-top:4px; }
.kpi-prog { height:6px; background:rgba(255,255,255,.08); border-radius:99px;
            margin-top:10px; overflow:hidden; }
.kpi-prog > div { height:100%; border-radius:99px; }

/* ---- ป้ายสัญญาณ (BUY/SELL/WAIT และสถานะไม้) ---- */
.pill { display:inline-flex; align-items:center; gap:4px; padding:2px 10px;
        border-radius:99px; font-size:.8rem; font-weight:600; white-space:nowrap; }
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
.chart-note { font-size:.75rem; color:#8b94a7; margin:-6px 0 6px 2px; }

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
    """ดึงราคา OHLC สำหรับวาดกราฟ (จำผลไว้ 1 ชั่วโมง จะได้ไม่ดึงซ้ำทุกครั้งที่กดหน้าจอ)"""
    ohlc = price_fetcher.fetch_ohlc(pair)
    df = ohlc[["open", "high", "low", "close"]].copy()
    df["MA เร็ว"] = technical_analyzer.moving_average(ohlc["close"], config.MA_FAST_PERIOD)
    df["MA ช้า"] = technical_analyzer.moving_average(ohlc["close"], config.MA_SLOW_PERIOD)
    df = df.rename(columns={"open": "เปิด", "high": "สูง", "low": "ต่ำ", "close": "ปิด"})
    return df.dropna()


def _dark(chart: alt.Chart) -> alt.Chart:
    """ตั้งค่าธีมมืดให้กราฟ altair ทุกตัว (พื้นใส เส้นตารางจาง ตัวหนังสือเทา)"""
    return chart.configure(background="transparent").configure_view(
        stroke=None
    ).configure_axis(
        gridColor=GRID_COLOR, labelColor=COLOR_MUTED,
        tickColor=GRID_COLOR, domainColor=GRID_COLOR,
    ).configure_legend(labelColor="#c7cede")


def price_chart(pair: str, bars: int = 120) -> alt.Chart:
    """
    กราฟแท่งเทียน (แบบกราฟเทรดทั่วไปที่ผู้ใช้คุ้นจาก MT5) + เส้น MA สองเส้น
    เขียว = แท่งขึ้น (ปิด >= เปิด), แดง = แท่งลง | แสดง ~120 แท่งล่าสุด (~5 วันบน 1h)
    """
    df = get_chart_data(pair).tail(bars).reset_index()
    df = df.rename(columns={df.columns[0]: "เวลา"})

    up = alt.datum["ปิด"] >= alt.datum["เปิด"]
    candle_color = alt.condition(up, alt.value(COLOR_GOOD), alt.value(COLOR_BAD))
    y_scale = alt.Scale(zero=False)

    base = alt.Chart(df).encode(x=alt.X("เวลา:T", title=None))

    # ไส้เทียน (เส้นบางจากราคาต่ำสุดถึงสูงสุดของแท่ง)
    wick = base.mark_rule(strokeWidth=1).encode(
        y=alt.Y("ต่ำ:Q", title=None, scale=y_scale),
        y2="สูง:Q",
        color=candle_color,
    )
    # ตัวเทียน (แท่งหนาจากราคาเปิดถึงปิด) + tooltip ครบ เปิด/สูง/ต่ำ/ปิด
    body = base.mark_bar(size=4).encode(
        y=alt.Y("เปิด:Q", title=None, scale=y_scale),
        y2="ปิด:Q",
        color=candle_color,
        tooltip=[alt.Tooltip("เวลา:T", format="%d %b %H:%M"),
                 alt.Tooltip("เปิด:Q", format=".5f"),
                 alt.Tooltip("สูง:Q", format=".5f"),
                 alt.Tooltip("ต่ำ:Q", format=".5f"),
                 alt.Tooltip("ปิด:Q", format=".5f")],
    )

    # เส้น MA สองเส้นทับบนแท่งเทียน (สีเหลือง/ม่วง มีป้ายบอกใน legend)
    ma_df = df.melt(id_vars="เวลา", value_vars=["MA เร็ว", "MA ช้า"],
                    var_name="เส้น", value_name="ราคา")
    ma_lines = alt.Chart(ma_df).mark_line(strokeWidth=1.8).encode(
        x="เวลา:T",
        y=alt.Y("ราคา:Q", title=None, scale=y_scale),
        color=alt.Color("เส้น:N", sort=["MA เร็ว", "MA ช้า"],
                        scale=alt.Scale(domain=["MA เร็ว", "MA ช้า"],
                                        range=[COLOR_MA_FAST, COLOR_MA_SLOW]),
                        legend=alt.Legend(orient="top", title=None)),
        tooltip=[alt.Tooltip("เวลา:T", format="%d %b %H:%M"),
                 alt.Tooltip("เส้น:N"),
                 alt.Tooltip("ราคา:Q", format=".5f")],
    )

    return _dark((wick + body + ma_lines).properties(height=320))


# ============================================
# กราฟชุดผลการเทรด (ใช้ข้อมูลจากสมุด paper trading)
# ============================================

def profit_pct(trades: list) -> float:
    """กำไรรวมของรายการไม้ที่ให้มา คิดเป็น % ของทุน (เสี่ยง 1% ต่อไม้ แบบไม่ทบต้น)"""
    return round(sum(t["net_r"] for t in trades) * config.RISK_PER_TRADE_PERCENT, 2)


def cum_profit_chart(closed: list, selected_pairs: list) -> alt.Chart:
    """
    กราฟ 1: กำไรสะสม (แกน Y, % ของทุน) เทียบวันที่ดำเนินการมา (แกน X, รายวัน)
    เส้นรวม = น้ำเงินหนา + พื้นไล่เฉดใต้เส้น | เส้นรายคู่ที่ติ๊ก = เส้นบางสีประจำตัว
    วันไหนไม่มีไม้ปิด เส้นเดินราบ — เห็น "ระยะเวลาที่ผ่านมา" ตรงตามจริง
    """
    risk = config.RISK_PER_TRADE_PERCENT
    trades = sorted([t for t in closed if t["pair"] in selected_pairs],
                    key=lambda t: t.get("exit_time", ""))

    # แกนเวลารายวัน: จากวันที่ไม้แรกปิด ถึงวันนี้ (UTC)
    start = pd.to_datetime(trades[0]["exit_time"]).normalize()
    today = pd.Timestamp(datetime.now(timezone.utc).replace(tzinfo=None)).normalize()
    end = max(today, pd.to_datetime(trades[-1]["exit_time"]).normalize())
    days = pd.date_range(start, end, freq="D")

    pair_order = [p for p in config.WATCHED_PAIRS if p in selected_pairs]
    rows = []
    for day in days:
        upto = [t for t in trades if pd.to_datetime(t["exit_time"]).normalize() <= day]
        rows.append({"วันที่": day, "ชุด": TOTAL_LINE,
                     "กำไรสะสม (%)": round(sum(t["net_r"] for t in upto) * risk, 2)})
        for p in pair_order:
            rows.append({"วันที่": day, "ชุด": p,
                         "กำไรสะสม (%)": round(sum(t["net_r"] for t in upto
                                                   if t["pair"] == p) * risk, 2)})
    df = pd.DataFrame(rows)
    total_df = df[df["ชุด"] == TOTAL_LINE]

    # ลำดับสี: เส้นรวม = น้ำเงิน, คู่เงิน = สีประจำตัว (เรียงตาม config.WATCHED_PAIRS)
    domain = [TOTAL_LINE] + pair_order
    colors = [COLOR_PRICE] + [PAIR_COLORS[config.WATCHED_PAIRS.index(p) % len(PAIR_COLORS)]
                              for p in pair_order]

    # พื้นไล่เฉดใต้เส้นรวม (ฟ้า -> จางหาย) ให้สวยแบบกราฟตัวอย่างที่ผู้ใช้ชอบ
    area = alt.Chart(total_df).mark_area(
        line=False,
        color=alt.Gradient(
            gradient="linear",
            stops=[alt.GradientStop(color="rgba(57,135,229,0.30)", offset=1),
                   alt.GradientStop(color="rgba(57,135,229,0.0)", offset=0)],
            x1=1, x2=1, y1=1, y2=0,
        ),
    ).encode(
        x=alt.X("วันที่:T", title=None),
        y=alt.Y("กำไรสะสม (%):Q", title=None),
    )

    lines = alt.Chart(df).mark_line(point={"filled": True, "size": 28}).encode(
        x=alt.X("วันที่:T", title=None, axis=alt.Axis(format="%d %b")),
        y=alt.Y("กำไรสะสม (%):Q", title=None),
        color=alt.Color("ชุด:N", sort=domain,
                        scale=alt.Scale(domain=domain, range=colors),
                        legend=alt.Legend(orient="top", title=None)),
        strokeWidth=alt.condition(alt.datum["ชุด"] == TOTAL_LINE,
                                  alt.value(3), alt.value(1.5)),
        tooltip=[alt.Tooltip("วันที่:T", format="%d %b %Y"), "ชุด:N",
                 alt.Tooltip("กำไรสะสม (%):Q", format="+.2f")],
    )
    # เส้นประที่ 0% = จุดเริ่มต้น (เหนือเส้น = กำไร ใต้เส้น = ขาดทุน)
    zero = alt.Chart(pd.DataFrame({"y": [0.0]})).mark_rule(
        strokeDash=[4, 4], color=COLOR_MUTED).encode(y="y:Q")
    return _dark((area + lines + zero).properties(height=260))


def trades_r_chart(closed: list) -> alt.Chart:
    """กราฟ 2: ผลรายไม้เป็นแท่ง (เขียวกำไร/แดงขาดทุน) + เส้น R สะสม — หน่วยเดียวกัน (R)"""
    rows, cum = [], 0.0
    for i, t in enumerate(sorted(closed, key=lambda t: t.get("exit_time", "")), start=1):
        cum += t["net_r"]
        rows.append({"ไม้ที่": i, "คู่เงิน": t["pair"], "ผล (R)": round(t["net_r"], 2),
                     "สะสม (R)": round(cum, 2),
                     "ปิดเมื่อ": t.get("exit_time", "")[:16].replace("T", " ")})
    df = pd.DataFrame(rows)

    bars = alt.Chart(df).mark_bar(width={"band": 0.6}, cornerRadiusEnd=4).encode(
        x=alt.X("ไม้ที่:O", title=None, axis=alt.Axis(labelAngle=0)),
        y=alt.Y("ผล (R):Q", title=None),
        color=alt.condition(alt.datum["ผล (R)"] > 0,
                            alt.value(COLOR_GOOD), alt.value(COLOR_BAD)),
        tooltip=["ไม้ที่:O", "คู่เงิน:N", "ผล (R):Q", "สะสม (R):Q", "ปิดเมื่อ:N"],
    )
    cum_line = alt.Chart(df).mark_line(
        strokeWidth=2, color=COLOR_PRICE,
        point={"filled": True, "size": 40, "color": COLOR_PRICE},
    ).encode(
        x="ไม้ที่:O",
        y=alt.Y("สะสม (R):Q", title=None),
        tooltip=["ไม้ที่:O", "สะสม (R):Q"],
    )
    zero = alt.Chart(pd.DataFrame({"y": [0.0]})).mark_rule(color=COLOR_MUTED).encode(y="y:Q")
    return _dark((bars + cum_line + zero).properties(height=230))


def pareto_chart(closed: list) -> alt.Chart:
    """
    กราฟ 3: พาเรโต — เทียบทุกตัวว่าใครทำผลงานยังไง
    แท่ง = กำไร/ขาดทุนของแต่ละคู่ (% ของทุน) เรียงจากเก่งสุดไปแย่สุด
    เส้นน้ำเงิน = กำไรสะสมเมื่อรวมทีละคู่จากซ้าย (จบที่กำไรรวมทั้งระบบ)
    แกนเดียว หน่วยเดียวกันทั้งกราฟ (% ของทุน)
    """
    # เริ่มจาก 0 ครบทุกตัวที่ติดตาม — คู่ที่ยังไม่มีไม้ก็แสดงเป็นแท่ง 0 (ผู้ใช้ขอครบ 5 แท่ง)
    totals = {p: 0.0 for p in config.WATCHED_PAIRS}
    for t in closed:
        totals[t["pair"]] = totals.get(t["pair"], 0.0) + t["net_r"]
    risk = config.RISK_PER_TRADE_PERCENT
    ranked = sorted(totals.items(), key=lambda kv: kv[1], reverse=True)

    rows, cum = [], 0.0
    for pair, r_sum in ranked:
        pct = r_sum * risk
        cum += pct
        rows.append({"คู่เงิน": pair, "กำไร (%)": round(pct, 2), "สะสม (%)": round(cum, 2),
                     "จำนวนไม้": sum(1 for t in closed if t["pair"] == pair)})
    df = pd.DataFrame(rows)
    order = [r["คู่เงิน"] for r in rows]   # ล็อกลำดับแท่งตามอันดับผลงาน

    bars = alt.Chart(df).mark_bar(width={"band": 0.55}, cornerRadiusEnd=4).encode(
        x=alt.X("คู่เงิน:N", title=None, sort=order, axis=alt.Axis(labelAngle=0)),
        y=alt.Y("กำไร (%):Q", title=None),
        color=alt.condition(alt.datum["กำไร (%)"] > 0,
                            alt.value(COLOR_GOOD), alt.value(COLOR_BAD)),
        tooltip=["คู่เงิน:N", alt.Tooltip("กำไร (%):Q", format="+.2f"),
                 alt.Tooltip("สะสม (%):Q", format="+.2f"), "จำนวนไม้:Q"],
    )
    cum_line = alt.Chart(df).mark_line(
        strokeWidth=2, color=COLOR_PRICE,
        point={"filled": True, "size": 45, "color": COLOR_PRICE},
    ).encode(
        x=alt.X("คู่เงิน:N", sort=order),
        y=alt.Y("สะสม (%):Q", title=None),
        tooltip=["คู่เงิน:N", alt.Tooltip("สะสม (%):Q", format="+.2f")],
    )
    zero = alt.Chart(pd.DataFrame({"y": [0.0]})).mark_rule(color=COLOR_MUTED).encode(y="y:Q")
    return _dark((bars + cum_line + zero).properties(height=250))


def sentiment_chart(results: list) -> alt.Chart | None:
    """กราฟ 4ก: ข่าวเอียงทางไหน — แท่งนอนแยกซ้าย(ลง)/ขวา(ขึ้น)จากศูนย์ ต่อคู่เงิน"""
    rows = [{"คู่เงิน": r["pair"], "คะแนนข่าว": r["news_sentiment"]["net_score"]}
            for r in results if r.get("news_sentiment")]
    if not rows:
        return None
    df = pd.DataFrame(rows)

    bars = alt.Chart(df).mark_bar(height={"band": 0.55}, cornerRadiusEnd=4).encode(
        y=alt.Y("คู่เงิน:N", title=None, sort=None),
        x=alt.X("คะแนนข่าว:Q", title=None,
                scale=alt.Scale(domain=[-1, 1]),
                axis=alt.Axis(values=[-1, -0.5, 0, 0.5, 1])),
        color=alt.condition(alt.datum["คะแนนข่าว"] > 0,
                            alt.value(COLOR_PRICE), alt.value(COLOR_BAD)),
        tooltip=["คู่เงิน:N", alt.Tooltip("คะแนนข่าว:Q", format=".3f")],
    )
    zero = alt.Chart(pd.DataFrame({"x": [0.0]})).mark_rule(color=COLOR_MUTED).encode(x="x:Q")
    return _dark((bars + zero).properties(height=200))


def rsi_chart(results: list) -> alt.Chart | None:
    """กราฟ 4ข: จังหวะ RSI — แท่งยื่นจากเส้น 50 (กลยุทธ์ v2 ใช้ RSI ข้าม 50 เป็นจังหวะเข้า)"""
    rows = [{"คู่เงิน": r["pair"], "RSI": r["technical"]["rsi_value"], "กลาง": 50.0}
            for r in results if r.get("technical")]
    if not rows:
        return None
    df = pd.DataFrame(rows)

    bars = alt.Chart(df).mark_bar(height={"band": 0.55}, cornerRadius=4).encode(
        y=alt.Y("คู่เงิน:N", title=None, sort=None),
        x=alt.X("กลาง:Q", title=None, scale=alt.Scale(domain=[0, 100]),
                axis=alt.Axis(values=[0, 30, 50, 70, 100])),
        x2="RSI:Q",
        color=alt.condition(alt.datum["RSI"] > 50,
                            alt.value(COLOR_PRICE), alt.value(COLOR_BAD)),
        tooltip=["คู่เงิน:N", alt.Tooltip("RSI:Q", format=".1f")],
    )
    # เส้นอ้างอิง: 50 = เส้นแบ่งโมเมนตัม, 30/70 = โซน oversold/overbought
    refs = alt.Chart(pd.DataFrame({"x": [30.0, 50.0, 70.0]})).mark_rule(
        strokeDash=[4, 4], color=COLOR_MUTED).encode(x="x:Q")
    return _dark((bars + refs).properties(height=200))


# ============================================
# ชิ้นส่วน HTML: การ์ด KPI, ป้ายสัญญาณ, ตารางการ์ด
# ============================================

def kpi_card(icon_name: str, accent: str, label: str, value: str,
             sub: str = "", progress: float = None) -> str:
    """การ์ดตัวเลขสรุป 1 ใบ: ไอคอน SVG ในกรอบสีจางๆ + ตัวเลขใหญ่ + คำอธิบาย + แถบเป้า"""
    sub_html = f'<div class="kpi-sub">{sub}</div>' if sub else ""
    prog_html = ""
    if progress is not None:
        pct = max(0.0, min(progress, 1.0)) * 100
        prog_html = (f'<div class="kpi-prog">'
                     f'<div style="width:{pct:.0f}%;background:{accent}"></div></div>')
    return f'''<div class="kpi-card">
      <div class="kpi-top">
        <div class="kpi-icon" style="background:{accent}26;color:{accent}">{icon_svg(icon_name)}</div>
        <div class="kpi-label">{label}</div>
      </div>
      <div class="kpi-value">{value}</div>
      {sub_html}{prog_html}</div>'''


def kpi_row(cards: list):
    st.markdown('<div class="kpi-row">' + "".join(cards) + "</div>", unsafe_allow_html=True)


def pill(kind: str, text: str, icon_name: str) -> str:
    return f'<span class="pill pill-{kind}">{icon_svg(icon_name, 11)}{text}</span>'


PILL = {
    "BUY": pill("buy", "BUY", "trend-up"),
    "SELL": pill("sell", "SELL", "trend-down"),
    "WAIT": pill("wait", "WAIT", "pause"),
}
TRADE_PILL = {
    "open": pill("wait", "เปิดอยู่", "hourglass"),
    "won": pill("buy", "ชนะ", "check"),
    "lost": pill("sell", "แพ้", "x"),
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


def chart_note(text: str):
    st.markdown(f'<div class="chart-note">{text}</div>', unsafe_allow_html=True)


def demo_trades() -> list:
    """
    ไม้ตัวอย่างสำหรับโชว์หน้าตากราฟกำไรก่อนมีไม้จริง (ครบ 5 คู่ กระจาย ~2 สัปดาห์)
    ใช้แสดงพร้อมป้ายเตือน "ตัวอย่าง" เท่านั้น — ห้ามปนกับสมุดจริงเด็ดขาด
    """
    base = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=13)
    pattern = [("EURUSD", 1.8), ("GBPUSD", -1.0), ("USDJPY", 2.1), ("AUDUSD", -1.0),
               ("XAUUSD", 1.5), ("EURUSD", -1.0), ("USDJPY", 1.9), ("XAUUSD", -1.0),
               ("GBPUSD", 1.6), ("AUDUSD", 2.0)]
    return [{"pair": p, "status": "won" if r > 0 else "lost", "net_r": r,
             "exit_time": (base + timedelta(days=i * 1.4)).strftime("%Y-%m-%dT%H:%M:%S")}
            for i, (p, r) in enumerate(pattern)]


def render_profit_charts(closed: list, demo: bool = False):
    """ส่วนกราฟกำไรทั้งชุด — ใช้กับข้อมูลจริง หรือข้อมูลตัวอย่าง (demo=True มีป้ายเตือน)"""
    key_suffix = "_demo" if demo else ""
    chip = "ตัวอย่างจำลอง — ไม่ใช่ผลจริง" if demo else "% ของทุนจำลอง · เสี่ยง 1% ต่อไม้"
    section("สรุปกำไร", chip)

    traded_pairs = [p for p in config.WATCHED_PAIRS
                    if any(t["pair"] == p for t in closed)]
    selected_pairs = st.multiselect("ติ๊กเลือกดูรายตัว", traded_pairs,
                                    default=traded_pairs, key=f"pair_filter{key_suffix}")

    sel_trades = [t for t in closed if t["pair"] in selected_pairs]
    sel_pct = profit_pct(sel_trades)
    sel_color = COLOR_GOOD if sel_pct >= 0 else COLOR_BAD
    demo_tag = (' <span style="font-size:.85rem;color:#c98500">(ตัวอย่าง)</span>'
                if demo else "")
    st.markdown(
        f'<div style="font-size:2rem;font-weight:800;color:{sel_color};margin:2px 0 6px 0">'
        f'{sel_pct:+.2f}%{demo_tag}'
        f'<span style="font-size:.85rem;font-weight:400;color:#8b94a7;margin-left:10px">'
        f'กำไร/ขาดทุนจากทุน ({len(sel_trades)} ไม้ที่ปิดแล้ว)</span></div>',
        unsafe_allow_html=True)

    if sel_trades:
        chart_note("กำไรสะสม (%) รายวันตั้งแต่เริ่มดำเนินการ — เส้นน้ำเงินหนา = รวมที่เลือก · "
                   "เส้นบาง = รายคู่ · เหนือเส้นประ 0 = กำไร · วันไม่มีไม้ปิดเส้นเดินราบ")
        st.altair_chart(cum_profit_chart(closed, selected_pairs), width="stretch")
    else:
        st.caption("ยังไม่ได้เลือกคู่เงิน — ติ๊กเลือกด้านบนอย่างน้อย 1 คู่")

    g1, g2 = st.columns(2)
    with g1:
        chart_note("ผลรายไม้ (R) — แท่งเขียว = ชนะ · แดง = แพ้ · เส้นน้ำเงิน = R สะสม")
        st.altair_chart(trades_r_chart(closed), width="stretch")
    with g2:
        chart_note("พาเรโต 5 คู่เงิน — แท่ง: กำไรแต่ละคู่ (%) เรียงเก่งสุด → แย่สุด · "
                   "เส้นน้ำเงิน: รวมสะสมทีละคู่ จบที่กำไรรวมทั้งระบบ")
        st.altair_chart(pareto_chart(closed), width="stretch")


# ============================================
# แถบข้าง (Sidebar): ปุ่มรันใหม่ + เลือกดูผลเก่า
# ============================================

st.sidebar.title("Forex Analyzer")

if st.sidebar.button("รันวิเคราะห์ใหม่", type="primary", width="stretch"):
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
# ส่วนบน: หัวเรื่อง + การ์ดสรุปสัญญาณ + ตารางสัญญาณ
# ============================================

# เวลาอัปเดตของไฟล์ที่กำลังดู (แสดงบนหัวเรื่อง)
mtime = os.path.getmtime(os.path.join(config.OUTPUT_DIR, selected_file))
updated_txt = datetime.fromtimestamp(mtime).strftime("%d/%m/%Y %H:%M")

st.markdown(f'''<div style="display:flex;align-items:baseline;gap:12px;flex-wrap:wrap;">
  <span style="font-size:1.7rem;font-weight:800;">ศูนย์วิเคราะห์ Forex</span>
  <span style="color:#8b94a7;font-size:.85rem;">ข่าว + เทคนิค · อัปเดต {updated_txt}</span>
</div>''', unsafe_allow_html=True)

# แบ่ง 2 แท็บ: กราฟเทรด/สัญญาณ แยกจากกราฟวิเคราะห์กำไร (ผู้ใช้ขอ 2026-07-19)
tab_market, tab_profit = st.tabs(["สัญญาณ & ตลาด", "วิเคราะห์กำไร"])

with tab_market:
    actions = [r["combined_signal"]["action"] for r in results]
    kpi_row([
        kpi_card("trend-up", COLOR_GOOD, "สัญญาณ BUY", str(actions.count("BUY")),
                 f"จาก {len(results)} ตัวที่ติดตาม"),
        kpi_card("trend-down", COLOR_BAD, "สัญญาณ SELL", str(actions.count("SELL")),
                 f"จาก {len(results)} ตัวที่ติดตาม"),
        kpi_card("pause", COLOR_MUTED, "รอจังหวะ (WAIT)", str(actions.count("WAIT")),
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

    # ---- ภาพรวมตลาดตอนนี้ (กราฟข่าว + RSI — มีข้อมูลตั้งแต่ยังไม่มีไม้ปิด) ----
    section("ภาพรวมตลาดตอนนี้", "จากรอบวิเคราะห์ที่เลือก")

    mkt_left, mkt_right = st.columns(2)
    with mkt_left:
        chart_note("ข่าวเอียงทางไหน — ขวา (น้ำเงิน) = ข่าวหนุนขึ้น · ซ้าย (แดง) = ข่าวกดลง")
        c = sentiment_chart(results)
        if c is not None:
            st.altair_chart(c, width="stretch")
        else:
            st.caption("ไม่มีข้อมูลข่าวในรอบนี้")
    with mkt_right:
        chart_note("จังหวะ RSI — แท่งยื่นจากเส้น 50: ขวา = โมเมนตัมขึ้น · ซ้าย = โมเมนตัมลง "
                   "(เส้นประ 30/70 = โซนสุดโต่ง)")
        c = rsi_chart(results)
        if c is not None:
            st.altair_chart(c, width="stretch")
        else:
            st.caption("ไม่มีข้อมูลราคาในรอบนี้")

# ============================================
# แท็บ "วิเคราะห์กำไร": การ์ดสถิติ + ชุดกราฟผลเทรด + ตารางไม้ (แยกจากกราฟเทรด)
# ============================================

with tab_profit:
    section("Paper Trading", "เทรดจำลอง — ไม่มีเงินจริง")

    paper_trades = paper_trader.load_trades()
    paper_stats = paper_trader.summarize(paper_trades)
    closed_trades = [t for t in paper_trades if t["status"] != "open"]

    ret = paper_stats["sim_return_pct"]
    ret_color = COLOR_GOOD if ret >= 0 else COLOR_BAD
    kpi_row([
        kpi_card("hourglass", COLOR_MA_FAST, "เปิดค้างอยู่", str(paper_stats["open_count"])),
        kpi_card("target", COLOR_PRICE, "ปิดแล้ว", f"{paper_stats['closed_count']} ไม้",
                 "เป้าพิสูจน์ระบบ: 20 ไม้ใน 1 เดือน",
                 progress=paper_stats["closed_count"] / 20),
        kpi_card("trophy", COLOR_MA_SLOW, "อัตราชนะ", f"{paper_stats['win_rate_pct']}%",
                 "เป้าจาก backtest: ~40%"),
        kpi_card("coins", ret_color, "ผลตอบแทนจำลอง",
                 f'<span style="color:{ret_color}">{ret:+}%</span>',
                 "จำลองทุนโดยเสี่ยง 1% ต่อไม้"),
    ])

    if closed_trades:
        render_profit_charts(closed_trades)
    else:
        # ยังไม่มีไม้ปิดจริง — โชว์หน้าตากราฟด้วยข้อมูลตัวอย่าง พร้อมป้ายเตือนชัดเจน
        # (พอไม้จริงปิดไม้แรก ส่วนนี้จะสลับเป็นข้อมูลจริงอัตโนมัติ)
        if paper_trades:
            st.info("มีไม้เปิดค้างอยู่ รอปิดไม้แรก (ชน SL หรือ TP) — "
                    "ระหว่างนี้กราฟข้างล่างเป็น **ตัวอย่างจากข้อมูลจำลอง** ให้เห็นหน้าตาไว้ก่อน")
        else:
            st.info("ยังไม่มีไม้เทรดที่ปิดแล้ว — กราฟข้างล่างเป็น **ตัวอย่างจากข้อมูลจำลอง** "
                    "ให้เห็นหน้าตาไว้ก่อน พอมีไม้จริงปิดจะสลับเป็นข้อมูลจริงให้อัตโนมัติ")
        render_profit_charts(demo_trades(), demo=True)

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

# ============================================
# ท้ายแท็บ "สัญญาณ & ตลาด": รายละเอียดรายคู่เงิน (กดเปิดดูทีละคู่ — เหมือนเดิม
# เปลี่ยนเฉพาะกราฟเป็นแท่งเทียนแบบกราฟเทรดทั่วไป)
# ============================================

with tab_market:
    section("รายละเอียดรายคู่เงิน", "กดเปิดดูทีละคู่ · กราฟแท่งเทียน ~5 วันล่าสุด")

    ACTION_LABEL = {"BUY": "▲ BUY", "SELL": "▼ SELL", "WAIT": "⏸ WAIT"}
    for r in results:
        sig = r["combined_signal"]
        with st.expander(f"{r['pair']} — {ACTION_LABEL.get(sig['action'], sig['action'])}"):
            left, right = st.columns([3, 2])

            # ---- ฝั่งซ้าย: กราฟแท่งเทียน + MA ----
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
