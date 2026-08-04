"""
テクニカル雑談 収集スクリプト

SNS を中心に IT 関連の話題を収集し、カテゴリ別に整理した JSON をファイルへ書き出す。
記事の執筆はエージェント側で行う。

Usage: python generate_smallchat.py YYYYMMDD SLOT [出力先パス]
  SLOT は am / pm。出力先を省略した場合は news_data.json に書き出す。
"""

import json
import sys
from datetime import datetime, timedelta, timezone

import feedparser
import requests
from googlenewsdecoder import new_decoderv1

JST = timezone(timedelta(hours=9))

# --- ニュースソース定義 ---------------------------------------------------------------

FEEDS = {
    # --- Microsoft ---
    "microsoft": [
        {"name": "Reddit Microsoft", "url": "https://www.reddit.com/r/microsoft/.rss"},
        {"name": "Reddit Windows", "url": "https://www.reddit.com/r/Windows11/.rss"},
        {"name": "はてなブックマーク Microsoft", "url": "https://b.hatena.ne.jp/search/tag?q=Microsoft&mode=rss"},
        {"name": "X(Twitter) Microsoft話題", "url": "https://news.google.com/rss/search?q=Microsoft+%E8%A9%B1%E9%A1%8C&hl=ja&gl=JP&ceid=JP:ja"},
        {"name": "Google News Microsoft", "url": "https://news.google.com/rss/search?q=Microsoft+latest&hl=en&gl=US&ceid=US:en"},
        {"name": "Reddit Surface", "url": "https://www.reddit.com/r/Surface/.rss"},
        {"name": "Publickey", "url": "https://www.publickey1.jp/atom.xml"},
        {"name": "Qiita Microsoft", "url": "https://qiita.com/tags/microsoft/feed"},
        {"name": "Google News Microsoft Japan", "url": "https://news.google.com/rss/search?q=Microsoft+%E6%97%A5%E6%9C%AC&hl=ja&gl=JP&ceid=JP:ja"},
        {"name": "Google News Windows", "url": "https://news.google.com/rss/search?q=Windows+update+new&hl=en&gl=US&ceid=US:en"},
        {"name": "GitHub Blog", "url": "https://github.blog/feed/"},
    ],
    # --- AI ---
    "ai": [
        {"name": "Reddit MachineLearning", "url": "https://www.reddit.com/r/MachineLearning/.rss"},
        {"name": "Reddit LocalLLaMA", "url": "https://www.reddit.com/r/LocalLLaMA/.rss"},
        {"name": "はてなブックマーク AI", "url": "https://b.hatena.ne.jp/search/tag?q=AI&mode=rss"},
        {"name": "X(Twitter) AI話題", "url": "https://news.google.com/rss/search?q=AI+%E4%BA%BA%E5%B7%A5%E7%9F%A5%E8%83%BD+%E8%A9%B1%E9%A1%8C&hl=ja&gl=JP&ceid=JP:ja"},
        {"name": "Hacker News AI", "url": "https://hnrss.org/best?q=AI+LLM"},
        {"name": "Reddit Artificial", "url": "https://www.reddit.com/r/artificial/.rss"},
        {"name": "Reddit OpenAI", "url": "https://www.reddit.com/r/OpenAI/.rss"},
        {"name": "Qiita AI", "url": "https://qiita.com/tags/ai/feed"},
        {"name": "Zenn AI", "url": "https://zenn.dev/topics/ai/feed"},
        {"name": "Google News AI Business", "url": "https://news.google.com/rss/search?q=artificial+intelligence+business&hl=en&gl=US&ceid=US:en"},
        {"name": "Google AI Blog", "url": "https://blog.google/technology/ai/rss/"},
    ],
    # --- Azure ---
    "azure": [
        {"name": "Azure Blog", "url": "https://azure.microsoft.com/en-us/blog/feed/"},
        {"name": "Azure Release Communications", "url": "https://www.microsoft.com/releasecommunications/api/v2/azure/rss"},
        {"name": "Reddit Azure", "url": "https://www.reddit.com/r/azure/.rss"},
        {"name": "X(Twitter) Azure話題", "url": "https://news.google.com/rss/search?q=Azure+%E8%A9%B1%E9%A1%8C&hl=ja&gl=JP&ceid=JP:ja"},
        {"name": "Google News Azure", "url": "https://news.google.com/rss/search?q=Azure+cloud&hl=en&gl=US&ceid=US:en"},
        {"name": "Azure SDK Blog", "url": "https://devblogs.microsoft.com/azure-sdk/feed/"},
        {"name": "Qiita Azure", "url": "https://qiita.com/tags/azure/feed"},
        {"name": "DevelopersIO", "url": "https://dev.classmethod.jp/feed/"},
        {"name": "Reddit CloudComputing", "url": "https://www.reddit.com/r/cloudcomputing/.rss"},
        {"name": "Google News Azure Japan", "url": "https://news.google.com/rss/search?q=Azure+%E3%82%A2%E3%83%83%E3%83%97%E3%83%87%E3%83%BC%E3%83%88&hl=ja&gl=JP&ceid=JP:ja"},
    ],
    # --- セキュリティ ---
    "security": [
        {"name": "Reddit netsec", "url": "https://www.reddit.com/r/netsec/.rss"},
        {"name": "Reddit cybersecurity", "url": "https://www.reddit.com/r/cybersecurity/.rss"},
        {"name": "はてなブックマーク IT", "url": "https://b.hatena.ne.jp/hotentry/it.rss"},
        {"name": "X(Twitter) セキュリティ話題", "url": "https://news.google.com/rss/search?q=%E3%82%BB%E3%82%AD%E3%83%A5%E3%83%AA%E3%83%86%E3%82%A3+%E8%84%86%E5%BC%B1%E6%80%A7+IT&hl=ja&gl=JP&ceid=JP:ja"},
        {"name": "Google News Cybersecurity", "url": "https://news.google.com/rss/search?q=cybersecurity+vulnerability&hl=en&gl=US&ceid=US:en"},
        {"name": "Qiita セキュリティ", "url": "https://qiita.com/tags/security/feed"},
        {"name": "Reddit InfoSec", "url": "https://www.reddit.com/r/InfoSecNews/.rss"},
        {"name": "Google News サイバーセキュリティ JP", "url": "https://news.google.com/rss/search?q=%E3%82%B5%E3%82%A4%E3%83%90%E3%83%BC%E6%94%BB%E6%92%83+%E3%82%BB%E3%82%AD%E3%83%A5%E3%83%AA%E3%83%86%E3%82%A3&hl=ja&gl=JP&ceid=JP:ja"},
        {"name": "INTERNET Watch", "url": "https://internet.watch.impress.co.jp/data/rss/1.0/iw/feed.rdf"},
        {"name": "Slashdot Security", "url": "https://slashdot.org/index.rss"},
    ],
    # --- クラウド (Azure以外) ---
    "cloud": [
        {"name": "Reddit AWS", "url": "https://www.reddit.com/r/aws/.rss"},
        {"name": "Reddit GCP", "url": "https://www.reddit.com/r/googlecloud/.rss"},
        {"name": "Reddit CloudComputing", "url": "https://www.reddit.com/r/cloudcomputing/.rss"},
        {"name": "Qiita AWS", "url": "https://qiita.com/tags/aws/feed"},
        {"name": "Qiita GCP", "url": "https://qiita.com/tags/gcp/feed"},
        {"name": "Google News AWS", "url": "https://news.google.com/rss/search?q=AWS+Amazon+Web+Services&hl=en&gl=US&ceid=US:en"},
        {"name": "Google News GCP", "url": "https://news.google.com/rss/search?q=Google+Cloud+Platform&hl=en&gl=US&ceid=US:en"},
        {"name": "Google News OCI", "url": "https://news.google.com/rss/search?q=Oracle+Cloud+Infrastructure&hl=en&gl=US&ceid=US:en"},
        {"name": "Google News クラウド JP", "url": "https://news.google.com/rss/search?q=AWS+GCP+%E3%82%AF%E3%83%A9%E3%82%A6%E3%83%89&hl=ja&gl=JP&ceid=JP:ja"},
        {"name": "DevelopersIO AWS", "url": "https://dev.classmethod.jp/feed/"},
        {"name": "AWS News Blog", "url": "https://aws.amazon.com/blogs/aws/feed/"},
        {"name": "AWS What's New", "url": "https://aws.amazon.com/about-aws/whats-new/recent/feed/"},
        {"name": "Google Cloud Blog", "url": "https://cloudblog.withgoogle.com/rss/"},
    ],
}

HTTP_HEADERS = {
    "User-Agent": "daily-updates-bot/1.0 (GitHub Actions; +https://github.com)",
    "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml",
}

MAX_ARTICLES_PER_CATEGORY = 10


# --- URL 解決 -------------------------------------------------------------------


def _resolve_google_news_url(url: str) -> str:
    """Google News RSS のリダイレクト URL を実際の記事 URL に解決する。"""
    if "news.google.com/rss/articles/" not in url:
        return url
    try:
        result = new_decoderv1(url)
        if result.get("status") and result.get("decoded_url"):
            return result["decoded_url"]
    except Exception as e:
        print(f"    URL 解決失敗 ({url}): {e}")
    return url


# --- フィード取得 -----------------------------------------------------------------


def _fetch_feed(url: str, since: datetime, max_items: int = 5) -> list[dict]:
    resp = requests.get(url, headers=HTTP_HEADERS, timeout=30)
    resp.raise_for_status()
    feed = feedparser.parse(resp.content)

    articles = []
    for entry in feed.entries:
        pub_date = None
        for attr in ("published_parsed", "updated_parsed"):
            parsed = getattr(entry, attr, None)
            if parsed:
                try:
                    pub_date = datetime(*parsed[:6], tzinfo=timezone.utc)
                except (ValueError, TypeError):
                    pass
                break

        if pub_date and pub_date < since:
            continue

        article_url = _resolve_google_news_url(entry.get("link", ""))
        articles.append(
            {
                "title": entry.get("title", "").strip(),
                "description": entry.get("summary", "").strip()[:150],
                "url": article_url,
                "datePublished": str(pub_date) if pub_date else "",
            }
        )
        if len(articles) >= max_items:
            break

    return articles


def fetch_category(category: str, since: datetime) -> list[dict]:
    all_articles = []
    for source in FEEDS.get(category, []):
        try:
            items = _fetch_feed(source["url"], since)
            for item in items:
                item["source"] = source["name"]
            all_articles.extend(items)
            print(f"    {source['name']}: {len(items)} 件")
        except Exception as e:
            print(f"    {source['name']}: 取得失敗 ({e})")
    if len(all_articles) > MAX_ARTICLES_PER_CATEGORY:
        print(f"  ※ {len(all_articles)} 件 → {MAX_ARTICLES_PER_CATEGORY} 件に制限")
        all_articles = all_articles[:MAX_ARTICLES_PER_CATEGORY]
    return all_articles


# --- メイン処理 -----------------------------------------------------------------


def main():
    if len(sys.argv) < 3:
        print("Usage: python generate_smallchat.py YYYYMMDD SLOT [出力先パス]")
        sys.exit(1)

    target_date = sys.argv[1]
    slot = sys.argv[2]
    output_path = sys.argv[3] if len(sys.argv) > 3 else "news_data.json"

    # 直近 12 時間の記事を対象とする
    target_dt = datetime.strptime(target_date, "%Y%m%d").replace(tzinfo=JST)
    hour = 3 if slot == "am" else 15
    slot_dt = target_dt + timedelta(hours=hour)
    since = slot_dt - timedelta(hours=12)

    print(f"対象日: {target_date} / スロット: {slot}")
    print(f"収集期間: {since.isoformat()} 以降")
    print("ニュースを取得中...")

    categories = {}
    for cat in ("microsoft", "ai", "azure", "security", "cloud"):
        print(f"\n[{cat}]")
        items = fetch_category(cat, since)
        print(f"  → 合計: {len(items)} 件")
        categories[cat] = items

    data = {
        "target_date": target_date,
        "slot": slot,
        "collected_since": since.isoformat(),
        "categories": categories,
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    total = sum(len(v) for v in categories.values())
    print(f"\n収集完了: {output_path} （合計 {total} 件）")


if __name__ == "__main__":
    main()
