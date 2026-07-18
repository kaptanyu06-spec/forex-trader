# PROJECT BRIEF: ระบบเทรด Forex อัตโนมัติ (News Sentiment + Technical + Risk Management)

> ไฟล์นี้สรุปบริบททั้งหมดของโปรเจกต์ เพื่อส่งต่อให้ Claude Code ดำเนินการพัฒนาต่อ
> วางไฟล์นี้ไว้ที่ root ของโปรเจกต์ แล้วบอก Claude Code ว่า "อ่านไฟล์ PROJECT_BRIEF.md แล้วดำเนินการต่อ"

---

## 1. เป้าหมายสุดท้าย (Goal)

สร้างระบบเทรด Forex อัตโนมัติที่:
- ดึงข่าว/ข้อมูลมหภาคมาวิเคราะห์แนวโน้ม (sentiment analysis)
- วิเคราะห์กราฟด้วย technical indicators + สถิติ
- คำนวณและควบคุมความเสี่ยงอย่างเข้มงวด (risk management)
- เชื่อมต่อ Broker API เพื่อส่งคำสั่งซื้อขายอัตโนมัติแบบเต็มรูปแบบ

## 2. บริบทผู้ใช้ (สำคัญมากสำหรับการออกแบบ)

- **ตลาดเป้าหมาย**: Forex (ยืนยันจากภาพหน้าจอแอปที่ผู้ใช้ใช้อยู่ — หน้าตาคล้าย MetaTrader 4/5 เวอร์ชันภาษาไทย แสดงคู่เงินกลุ่ม AUD เช่น AUDCAD, AUDJPY, AUDNZD พร้อม Bid/Ask/% วัน)
- **ระดับโค้ด**: ผู้ใช้ไม่มีพื้นฐานเขียนโปรแกรมมาก่อน ต้องอธิบาย/คอมเมนต์โค้ดให้เข้าใจง่าย
- **เป้าหมายการเชื่อมต่อ**: ต้องการต่อ Broker API ส่งคำสั่งจริงแบบอัตโนมัติเต็มรูปแบบ (ไม่ใช่แค่สัญญาณ)
- **แพลตฟอร์ม Broker ที่คาดว่าจะใช้**: MetaTrader 4 หรือ 5 (ยังไม่ได้ยืนยันเวอร์ชันชัดเจนจากผู้ใช้ — **ต้องถามผู้ใช้ก่อน** เพราะ MT4 ใช้ MQL4 ส่วน MT5 มี Python API อย่างเป็นทางการ (`MetaTrader5` package) ซึ่งวิธีเชื่อมต่อต่างกันโดยสิ้นเชิง)
- **ที่ตั้งผู้ใช้**: ประเทศไทย — มีประเด็นกฎหมาย/กฎระเบียบเรื่องการเทรด Forex กับโบรกต่างชาติที่ควรแจ้งเตือนผู้ใช้ให้ตรวจสอบกับ ก.ล.ต./ธปท. เอง (ไม่ใช่หน้าที่ระบบหรือ AI ที่จะให้คำแนะนำทางกฎหมาย)

## 3. แนวทางที่ตกลงกันไว้ (Approach)

เนื่องจากผู้ใช้ไม่มีพื้นฐานโค้ดและต้องการต่อเงินจริงในที่สุด จึงวางแผนแบบ **ขั้นบันได** ไม่กระโดดไปต่อบัญชีจริงทันที:

1. เรียน Python พื้นฐานคู่ไปกับการสร้างระบบ
2. สร้าง Data pipeline (ราคา + ข่าว)
3. Backtest กลยุทธ์ technical ง่ายๆ ก่อน (เช่น MA crossover)
4. เพิ่ม News sentiment เข้าไปในกลยุทธ์ ทดสอบซ้ำ
5. รัน Paper Trading (demo account) อย่างน้อย 1-3 เดือน
6. ต่อ Broker จริงด้วยเงินจำนวนน้อยที่ยอมรับการขาดทุนได้ก่อน

**สถานะปัจจุบัน: ขั้น 5.1-5.3 เสร็จแล้ว** (อัปเดต 2026-07-16: มี `price_fetcher.py` (yfinance), `technical_analyzer.py` (MA/RSI/MACD/ATR/Bollinger), `signal_combiner.py` (รวมข่าว+เทคนิค -> BUY/SELL/WAIT), `dashboard.py` (Streamlit), `backtester.py` (เข้าที่ open แท่งถัดไป กัน lookahead, SL/TP จาก ATR, หักสเปรด))

**ผล backtest (อัปเดต 2026-07-16 รอบสอง — เทียบ 2 กลยุทธ์ x 3 timeframes x 4 คู่หลัก):**
1. ระบบโหวตเดิม (v1, ±2): PF รวม ~0.97 ทุก timeframe — ขาดทุนหลังหักต้นทุน / กฎ ±3 ไม่เคย trigger (RSI/BB สวนเทรนด์หักล้าง MA/MACD โดยโครงสร้าง)
2. กลยุทธ์ใหม่ v2 "ตามเทรนด์+รอย่อ" (MA+MACD ตรงกัน = ทิศทาง, RSI ข้าม 50 = จังหวะ): **บน 1h ดีกว่า v1 ทุกคู่** (PF รวม 1.27, avg +6.0%, DD 3-10%) แต่บน 4h แย่ (PF 0.79) — **เปลี่ยนระบบ live มาใช้ v2 แล้ว** (technical_analyzer ส่ง trend_direction/entry_signal, signal_combiner ใช้แทนกฎโหวต)
3. ข้อสรุปที่ซื่อสัตย์: หลักฐานยังไม่แน่นพอเรียกว่า "ใช้ได้" — PF 1.27 จาก 143 เทรดใน 1 ปีเดียว และฟิลเตอร์ข่าว backtest ไม่ได้ (NewsAPI ฟรีไม่มีข่าวย้อนหลัง) ต้องพิสูจน์ด้วย paper trading เดินหน้า

**ขั้น 5.5 เสร็จแล้ว (2026-07-16)**: `scheduler.py` (รันอัตโนมัติทุก 2 ชม. — 12 รอบ/วัน x 8 req = 96 ไม่เกินโควตา NewsAPI 100/วัน), `paper_trader.py` (สมุดเทรดจำลอง: เปิดไม้ตามสัญญาณ เช็ค SL/TP กับราคาจริง กติกาเดียวกับ backtest, เก็บที่ output/paper_trades.json), `notifier.py` (Telegram — ผู้ใช้ยังไม่ได้ตั้งค่า token/chat id), Dashboard มีส่วนแสดงสถิติ paper trading แล้ว

**สถานะปัจจุบัน: เข้าสู่ขั้น Paper Trading (ขั้น 5 ของแผน)** — เก็บผลอย่างน้อย 1-3 เดือน เทียบกับ backtest (เป้า: PF ~1.27, win rate ~40%) ระบบรันอัตโนมัติทุก 1 ชม. บน GitHub Actions (repo: kaptanyu06-spec/forex-trader)

**ขั้น 5.4 โค้ดเสร็จแล้ว (2026-07-18) — รอผู้ใช้สมัคร OANDA**: เลือก OANDA practice แทน MT5 (Mac ต่อ MT5 Python ไม่ได้) `broker_oanda.py` ต่อเข้า scheduler แล้ว: ทุกสัญญาณที่เปิด paper trade จะส่งออเดอร์เข้าบัญชีทดลอง OANDA อัตโนมัติ (SL/TP ฝากไว้กับโบรก, ขนาดไม้จากกฎเสี่ยง 1%, กันเปิดซ้ำคู่เดิม, ล็อกเฉพาะ practice — ปฏิเสธบัญชีจริง) ถ้ายังไม่ใส่คีย์ระบบข้ามส่วนนี้และทำ paper trading ตามปกติ
**สิ่งที่ผู้ใช้ต้องทำเพื่อเปิดใช้**: (1) สมัครบัญชีทดลอง oanda.com -> Manage API Access -> สร้าง token (2) ใส่ OANDA_API_KEY + OANDA_ACCOUNT_ID ใน secrets_local.py (ในเครื่อง) และเพิ่มเป็น GitHub Secrets ชื่อเดียวกัน (Settings -> Secrets and variables -> Actions) (3) ทดสอบ `python broker_oanda.py`

**เพิ่ม Capital.com เป็นโบรกทางเลือก (2026-07-18)**: ผู้ใช้ติดปัญหาล็อกอิน OANDA (สมัครผ่านฟอร์ม MT5 demo แล้วตั้งรหัสเว็บ/รีเซ็ตไม่สำเร็จหลายรอบ — ได้บัญชี MT5 demo มาซึ่งใช้กับ REST API ไม่ได้) จึงเพิ่ม `broker_capital.py` อินเทอร์เฟซเดียวกัน scheduler เรียกทั้ง 2 โบรก ใครใส่คีย์อันนั้นทำงาน คีย์ที่ต้องใช้ 3 ค่า: CAPITAL_API_KEY, CAPITAL_IDENTIFIER (อีเมล), CAPITAL_API_PASSWORD (รหัสประจำคีย์ API) — วิธีสมัครอยู่หัวไฟล์ broker_capital.py | หมายเหตุ: ยังไม่เคยยิง API จริงกับ Capital.com — ตอนได้คีย์มาให้ทดสอบ `python broker_capital.py` ก่อน โดยเฉพาะเช็คว่าหน่วย size ของคู่ FX ตรงกับที่คิด (สูตรคิดเป็นหน่วยสกุลเงินหลัก ถ้าโบรกตีความเป็น lot ต้องแก้ calc_size)

**คำตอบจากผู้ใช้ (2026-07-16)**: ใช้ **MT5** | ยังไม่ได้สมัคร NewsAPI key | คู่เงินใช้ตามที่แนะนำ: EURUSD, GBPUSD, USDJPY, AUDUSD
**ประเด็นสำคัญ**: ผู้ใช้ใช้ Mac แต่ package `MetaTrader5` (Python) รองรับเฉพาะ Windows — ตอนทำขั้น 5.4 ต้องเลือก: Windows VM / เครื่อง Windows แยก / หรือโบรกเกอร์ที่มี REST API (เช่น OANDA)

## 4. สิ่งที่สร้างไปแล้ว (Current State — เขียนและทดสอบรันผ่านแล้ว)

โปรเจกต์: `forex_news_bot/`

| ไฟล์ | หน้าที่ | สถานะ |
|---|---|---|
| `config.py` | ตั้งค่า API key, คู่เงินที่ติดตาม (`WATCHED_PAIRS`), คีย์เวิร์ดข่าวต่อสกุลเงิน, ค่า risk % | ใช้งานได้ |
| `news_collector.py` | ดึงข่าวจาก NewsAPI (newsapi.org) ตามคีย์เวิร์ดของแต่ละสกุลเงิน | ใช้งานได้ (ต้องมี API key จริง) |
| `sentiment_analyzer.py` | วิเคราะห์ sentiment ด้วย VADER (`vaderSentiment` lib), ถ่วงน้ำหนัก title 70%/description 30%, ถ่วงน้ำหนักตามความใหม่ของข่าว, เปรียบเทียบ base vs quote currency ได้ "net sentiment score" | ทดสอบผ่านด้วยข้อมูลจำลอง |
| `risk_manager.py` | คำนวณ position size จาก % risk ต่อทุน, เช็ค daily/weekly loss limit, ประเมินความน่าเชื่อถือของสัญญาณข่าว (ต่ำ/ปานกลาง/สูง) | ทดสอบผ่านด้วยข้อมูลจำลอง |
| `main.py` | Orchestrator — รันทุกโมดูล พิมพ์สรุปผล + เซฟ JSON ไปที่ `output/` | ใช้งานได้ |
| `requirements.txt` | `requests`, `vaderSentiment` | - |
| `README.md` | คู่มือติดตั้ง + คำอธิบายผลลัพธ์ + ไกด์ risk management ฉบับเต็ม | - |

**ยังไม่มี**: technical analysis module, backtest engine, broker connection (MT4/MT5), scheduler/automation, database เก็บประวัติ

## 5. งานที่ต้องทำต่อ (Next Steps — เรียงตามลำดับที่แนะนำ)

### 5.1 Technical Analysis Module (ลำดับถัดไป)
- เพิ่มไฟล์ `technical_analyzer.py`
- Indicators ที่ต้องการ: MA crossover, RSI, MACD, ATR (สำหรับคำนวณ stop-loss แบบ dynamic), Bollinger Bands
- แนะนำ library: `pandas-ta` หรือ `ta-lib`
- ต้องมีแหล่งดึงราคาย้อนหลัง (historical OHLC) — ถ้าต่อ MT5 แล้วดึงผ่าน `MetaTrader5.copy_rates_from()` ได้เลย, ถ้ายังไม่ต่อ MT5 ให้ใช้ API สำรอง เช่น Alpha Vantage FX หรือ OANDA API สำหรับข้อมูลย้อนหลัง

### 5.2 Signal Combiner
- รวมสัญญาณจาก `sentiment_analyzer.py` + `technical_analyzer.py` เป็นสัญญาณเดียว
- ต้องออกแบบกฎการรวม (เช่น sentiment เป็นตัวกรองทิศทาง, technical เป็นตัว trigger จังหวะเข้า-ออก)

### 5.3 Backtest Engine
- แนะนำ library: `backtrader` หรือ `vectorbt`
- ทดสอบกลยุทธ์กับข้อมูลย้อนหลัง ระวัง overfitting
- Metrics ที่ต้องคำนวณ: Win rate, Profit factor, Sharpe ratio, Max drawdown

### 5.4 Broker Connection (MT4/MT5)
- **ต้องถามผู้ใช้ก่อนว่าใช้ MT4 หรือ MT5** เพราะวิธีต่อต่างกันสิ้นเชิง
- ถ้า MT5: ใช้ package `MetaTrader5` (official Python API) — เชื่อมต่อ terminal ที่ติดตั้งในเครื่องเดียวกัน
- ถ้า MT4: ต้องใช้สะพานเชื่อม เช่น เขียน Expert Advisor (EA) ด้วย MQL4 ที่คุยกับ Python ผ่านไฟล์/socket หรือใช้ library กลาง เช่น `mt4-hst`/ ZeroMQ bridge
- เริ่มจาก **Demo account เท่านั้น** ก่อนต่อบัญชีจริงเด็ดขาด

### 5.5 Automation/Scheduler
- ตั้งเวลารันอัตโนมัติ (cron job บน Linux/Mac หรือ Task Scheduler บน Windows หรือใช้ `schedule` library ใน Python)
- เพิ่ม logging และ alert (เช่น แจ้งเตือนผ่าน Line Notify / Telegram Bot เมื่อมีการเปิด/ปิดออเดอร์ หรือเมื่อชนขาดทุนลิมิต)

### 5.6 Paper Trading Validation
- รันระบบเต็มรูปแบบบน Demo account อย่างน้อย 1-3 เดือนก่อนต่อเงินจริง
- เก็บสถิติผลการเทรดเปรียบเทียบกับที่ backtest ไว้

**การตัดสินใจของผู้ใช้ (2026-07-18)**: ช่วง demo ใช้โหมดอัตโนมัติเต็ม (วัดผลระบบล้วนๆ ไม่มีคนแทรก) | ผู้ใช้อยากได้โหมด "กดยืนยันก่อนเทรด" — ตกลงกันว่าจะสร้างเป็นปุ่มยืนยันใน Telegram **ตอนเปลี่ยนไปเงินจริง** (ก่อนต่อบัญชีจริงต้องทำฟีเจอร์นี้ก่อน)

**ระยะพิสูจน์ demo (ผู้ใช้กำหนด 2026-07-18)**: ผู้ใช้ขอ 1 เดือน (สั้นกว่าที่แนะนำ 1-3 เดือน) — ตกลงเกณฑ์ร่วมกัน: **ครบ 1 เดือน (ประมาณ 18 ส.ค. 2026) และ ไม้ปิดแล้วอย่างน้อย 20 ไม้** (ถ้าไม้ไม่ครบให้รอจนครบ ~12-15 ไม้/เดือนตาม backtest) และถ้าผลแย่กว่า backtest ชัดเจน (ขาดทุนต่อเนื่อง / ชนะต่ำกว่า ~30%) ต้องหยุดคุยกันก่อน ไม่ไปขั้นเงินจริง — Claude Code ควรเตือนเกณฑ์นี้ถ้าผู้ใช้ขอข้ามขั้น

**ความชอบผู้ใช้ (2026-07-18)**: ถนัด/ชอบหน้าจอ MT5 มากกว่า — ช่วง demo ให้ใช้ MT5 (บัญชี OANDA MT5 demo) เป็นจอดูกราฟคู่ไปกับระบบ | ตอนออกแบบขั้นเงินจริง ให้พิจารณาโหมดกดยืนยัน Telegram + ผู้ใช้กดเทรดเองใน MT5 เป็นตัวเลือกหลัก (ไม่ต้องมี bridge) | บัญชี MT5 demo ที่ผู้ใช้ใช้ดูกราฟอยู่ปัจจุบัน: 10011767709 (แจ้ง 2026-07-18 — ไม่ได้เชื่อมกับระบบ ใช้ดูกราฟอย่างเดียว)

## 6. กฎ Risk Management ที่ต้องคงไว้เสมอ (Non-negotiable)

ค่าเหล่านี้ตั้งไว้แล้วใน `config.py` — Claude Code ไม่ควรลบหรือ bypass โดยไม่ถามผู้ใช้ก่อน:

- `RISK_PER_TRADE_PERCENT = 1.0` — ไม่เสี่ยงเกิน 1-2% ของทุนต่อออเดอร์
- `MAX_DAILY_LOSS_PERCENT = 3.0` — หยุดเทรดทันทีถ้าขาดทุนวันนี้ถึงลิมิต
- `MAX_WEEKLY_LOSS_PERCENT = 6.0` — หยุดเทรดถึงสัปดาห์หน้าถ้าถึงลิมิต
- ทุกออเดอร์ต้องมี stop-loss บังคับ ห้ามเปิดแบบไม่มี SL
- ห้ามมี logic ที่ทำ "revenge trading" (เพิ่ม position size หลังขาดทุนเพื่อเอาคืน)

## 7. ข้อมูล Setup ที่ผู้ใช้ต้องเตรียม/ยืนยันกับ Claude Code

- [ ] API Key จาก newsapi.org (มีแล้วหรือยัง — ใส่ใน `config.py` หรือ environment variable `NEWSAPI_KEY`)
- [ ] MT4 หรือ MT5? (ยืนยันเวอร์ชันแอปที่ใช้อยู่)
- [ ] มี Demo account พร้อมใช้หรือยัง (ต้องมีก่อนเชื่อมต่อทดสอบ)
- [ ] คู่เงินที่ต้องการเทรดจริง (ปัจจุบันตั้งไว้ตัวอย่างใน `WATCHED_PAIRS`: AUDCAD, AUDJPY, AUDNZD, EURUSD, USDJPY, GBPUSD — ควรปรับให้ตรงกับที่ผู้ใช้สนใจจริง)
- [ ] เงินทุนเริ่มต้น (สำหรับคำนวณ position sizing ตัวอย่างใน `main.py` ปัจจุบันใช้ 1000 USD เป็นตัวอย่าง)

## 8. ข้อจำกัดและคำเตือนที่ต้องคงไว้ในทุกเวอร์ชันถัดไป

- ระบบนี้ให้ "สัญญาณประกอบการตัดสินใจ" ไม่ใช่การรับประกันกำไร — ต้องมีคำเตือนนี้ในทุก output/README ที่ Claude Code สร้างเพิ่ม
- ไม่ควรมีการยืนยันหรือรับประกันผลตอบแทนใดๆ ในเอกสารหรือ comment ของโค้ด
- ประเด็นกฎหมายการเทรด Forex กับโบรกต่างชาติในไทย เป็นเรื่องที่ผู้ใช้ต้องตรวจสอบเองกับหน่วยงานกำกับดูแล ไม่ใช่สิ่งที่ระบบหรือ AI ควรให้คำยืนยัน
