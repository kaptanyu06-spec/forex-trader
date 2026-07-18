"""
news_collector.py
------------------
ดึงข่าวที่เกี่ยวข้องกับแต่ละสกุลเงินจาก NewsAPI
เอกสาร API: https://newsapi.org/docs/endpoints/everything
"""

import requests
from datetime import datetime, timedelta
import config


def fetch_news_for_currency(currency: str, api_key: str, lookback_days: int = 2) -> list:
    """
    ดึงข่าวที่เกี่ยวข้องกับสกุลเงินหนึ่งตัว (เช่น "USD")

    คืนค่าเป็น list ของ dict แต่ละอันคือข่าว 1 ชิ้น มี key:
    - title, description, source, published_at, url
    """
    keywords = config.CURRENCY_KEYWORDS.get(currency, [])
    if not keywords:
        return []

    # รวมคีย์เวิร์ดด้วย OR สำหรับ query ของ NewsAPI
    query = " OR ".join([f'"{kw}"' for kw in keywords])

    from_date = (datetime.utcnow() - timedelta(days=lookback_days)).strftime("%Y-%m-%d")

    url = "https://newsapi.org/v2/everything"
    params = {
        "q": query,
        "from": from_date,
        "language": "en",
        "sortBy": "publishedAt",
        "apiKey": api_key,
        "pageSize": 30,
    }

    try:
        response = requests.get(url, params=params, timeout=15)
        response.raise_for_status()
        data = response.json()
    except requests.exceptions.RequestException as e:
        print(f"[ERROR] ดึงข่าวสำหรับ {currency} ไม่สำเร็จ: {e}")
        return []

    if data.get("status") != "ok":
        print(f"[ERROR] NewsAPI ตอบกลับผิดพลาด: {data.get('message', 'unknown error')}")
        return []

    articles = []
    for item in data.get("articles", []):
        articles.append({
            "currency": currency,
            "title": item.get("title", ""),
            "description": item.get("description", "") or "",
            "source": item.get("source", {}).get("name", "unknown"),
            "published_at": item.get("publishedAt", ""),
            "url": item.get("url", ""),
        })

    return articles


def fetch_news_for_pair(pair: str, api_key: str, lookback_days: int = 2) -> dict:
    """
    ดึงข่าวสำหรับคู่เงินหนึ่งคู่ เช่น "EURUSD" -> ดึงข่าวทั้ง EUR และ USD

    คืนค่าเป็น dict: {"base": [...ข่าว...], "quote": [...ข่าว...]}
    """
    base_currency = pair[:3]
    quote_currency = pair[3:]

    base_news = fetch_news_for_currency(base_currency, api_key, lookback_days)
    quote_news = fetch_news_for_currency(quote_currency, api_key, lookback_days)

    return {
        "pair": pair,
        "base_currency": base_currency,
        "quote_currency": quote_currency,
        "base_news": base_news,
        "quote_news": quote_news,
    }


def fetch_all_watched_news(api_key: str = None, lookback_days: int = None) -> list:
    """
    ดึงข่าวสำหรับคู่เงินทั้งหมดใน config.WATCHED_PAIRS
    """
    api_key = api_key or config.NEWSAPI_KEY
    lookback_days = lookback_days or config.NEWS_LOOKBACK_DAYS

    if not api_key or api_key.startswith("ใส่"):
        raise ValueError(
            "ยังไม่ได้ตั้งค่า NEWSAPI_KEY กรุณาสมัครฟรีที่ https://newsapi.org/register "
            "แล้วนำ key มาใส่ในไฟล์ config.py หรือ environment variable NEWSAPI_KEY"
        )

    results = []
    for pair in config.WATCHED_PAIRS:
        print(f"กำลังดึงข่าวสำหรับ {pair} ...")
        results.append(fetch_news_for_pair(pair, api_key, lookback_days))

    return results


if __name__ == "__main__":
    # ทดสอบดึงข่าวคู่เดียว
    news = fetch_news_for_pair("EURUSD", config.NEWSAPI_KEY)
    print(f"พบข่าว EUR: {len(news['base_news'])} ชิ้น")
    print(f"พบข่าว USD: {len(news['quote_news'])} ชิ้น")
