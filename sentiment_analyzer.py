"""
sentiment_analyzer.py
----------------------
วิเคราะห์ความรู้สึก (sentiment) ของข่าวแต่ละชิ้น แล้วรวมคะแนนเป็นภาพรวมต่อสกุลเงิน/คู่เงิน

ใช้ VADER (Valence Aware Dictionary and sEntiment Reasoner)
ข้อดี: เบา ไม่ต้องโหลดโมเดลใหญ่ เหมาะกับข่าวภาษาอังกฤษพาดหัวสั้นๆ
ข้อจำกัด: ไม่เข้าใจบริบทการเงินลึกเท่าโมเดลเฉพาะทาง เช่น FinBERT
  (ถ้าต้องการความแม่นยำสูงขึ้นในอนาคต แนะนำอัปเกรดไปใช้ FinBERT ได้)
"""

from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

_analyzer = SentimentIntensityAnalyzer()


def score_text(text: str) -> float:
    """
    คืนค่าคะแนน sentiment ระหว่าง -1.0 (ลบมากสุด) ถึง +1.0 (บวกมากสุด)
    """
    if not text or not text.strip():
        return 0.0
    result = _analyzer.polarity_scores(text)
    return result["compound"]  # ค่ารวม -1 ถึง +1


def score_article(article: dict) -> dict:
    """
    ให้คะแนนข่าว 1 ชิ้น โดยรวม title + description เข้าด้วยกัน
    (title สำคัญกว่า description เลยให้ weight มากกว่า)
    """
    title_score = score_text(article.get("title", ""))
    desc_score = score_text(article.get("description", ""))

    # ถ่วงน้ำหนัก: title 70% description 30%
    combined_score = (title_score * 0.7) + (desc_score * 0.3)

    article_with_score = dict(article)
    article_with_score["sentiment_score"] = round(combined_score, 4)
    article_with_score["sentiment_label"] = _label_from_score(combined_score)
    return article_with_score


def _label_from_score(score: float) -> str:
    if score >= 0.25:
        return "บวกชัดเจน (Bullish)"
    elif score > 0.05:
        return "บวกเล็กน้อย"
    elif score >= -0.05:
        return "เป็นกลาง (Neutral)"
    elif score > -0.25:
        return "ลบเล็กน้อย"
    else:
        return "ลบชัดเจน (Bearish)"


def aggregate_currency_sentiment(news_list: list) -> dict:
    """
    รวมคะแนน sentiment ของข่าวทั้งหมดสำหรับสกุลเงินหนึ่งตัว

    ให้น้ำหนักข่าวใหม่กว่ามากกว่าข่าวเก่า (recency weighting แบบง่าย)
    คืนค่า: {"average_score": float, "label": str, "article_count": int, "scored_articles": [...]}
    """
    if not news_list:
        return {
            "average_score": 0.0,
            "label": "ไม่มีข่าว",
            "article_count": 0,
            "scored_articles": [],
        }

    scored_articles = [score_article(a) for a in news_list]

    # เรียงข่าวใหม่สุดก่อน แล้วให้ weight ลดหลั่นตามลำดับ (ข่าวล่าสุด weight สูงสุด)
    scored_articles.sort(key=lambda a: a.get("published_at", ""), reverse=True)

    total_weight = 0.0
    weighted_sum = 0.0
    n = len(scored_articles)
    for i, art in enumerate(scored_articles):
        weight = n - i  # ข่าวแรกสุด (ใหม่สุด) น้ำหนักมากสุด
        weighted_sum += art["sentiment_score"] * weight
        total_weight += weight

    average_score = weighted_sum / total_weight if total_weight else 0.0

    return {
        "average_score": round(average_score, 4),
        "label": _label_from_score(average_score),
        "article_count": len(scored_articles),
        "scored_articles": scored_articles,
    }


def analyze_pair_news(pair_news: dict) -> dict:
    """
    วิเคราะห์ sentiment ของทั้งคู่เงิน (base vs quote)
    แล้วคำนวณ "net sentiment" ว่าคู่เงินนี้มีแนวโน้มเอียงไปทางไหน

    หลักการ: ถ้า base currency sentiment ดีกว่า quote currency มาก
    แปลว่าคู่เงินนี้มีแรงหนุนให้ "ราคาขึ้น" (base แข็งกว่า quote)
    """
    base_sentiment = aggregate_currency_sentiment(pair_news["base_news"])
    quote_sentiment = aggregate_currency_sentiment(pair_news["quote_news"])

    net_score = round(base_sentiment["average_score"] - quote_sentiment["average_score"], 4)

    if net_score >= 0.15:
        bias = f"เอียงบวกต่อ {pair_news['base_currency']} (มีแนวโน้มหนุนราคาขึ้น)"
    elif net_score <= -0.15:
        bias = f"เอียงลบต่อ {pair_news['base_currency']} (มีแนวโน้มกดราคาลง)"
    else:
        bias = "ไม่มีความเอียงชัดเจนจากข่าว (สัญญาณอ่อน/เป็นกลาง)"

    return {
        "pair": pair_news["pair"],
        "base_currency": pair_news["base_currency"],
        "quote_currency": pair_news["quote_currency"],
        "base_sentiment": base_sentiment,
        "quote_sentiment": quote_sentiment,
        "net_score": net_score,
        "bias": bias,
    }
