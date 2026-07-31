"""
デイリーアップデート収集スクリプト

複数の RSS/Atom フィードから最新ニュースを収集し、カテゴリ別に整理した JSON を
ファイルへ書き出す。記事の執筆はエージェント側で行う。

Usage: python generate_daily_update.py YYYYMMDD [出力先パス]
  出力先を省略した場合は news_data.json に書き出す。
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
    # --- Azure ---
    "azure": [
        {"name": "Azure Release Communications", "url": "https://www.microsoft.com/releasecommunications/api/v2/azure/rss"},
        {"name": "Azure Blog", "url": "https://azure.microsoft.com/en-us/blog/feed/"},
        {"name": "Google News Azure", "url": "https://news.google.com/rss/search?q=Azure+%E3%82%A2%E3%83%83%E3%83%97%E3%83%87%E3%83%BC%E3%83%88&hl=ja&gl=JP&ceid=JP:ja"},
    ],
    # --- 技術系 (日本語) ---
    "tech_ja": [
        {"name": "ITmedia NEWS", "url": "https://rss.itmedia.co.jp/rss/2.0/news_bursts.xml"},
        {"name": "GIGAZINE", "url": "https://gigazine.net/news/rss_2.0/"},
        {"name": "Publickey", "url": "https://www.publickey1.jp/atom.xml"},
        {"name": "INTERNET Watch", "url": "https://internet.watch.impress.co.jp/data/rss/1.0/iw/feed.rdf"},
        {"name": "Zenn トレンド", "url": "https://zenn.dev/feed"},
        {"name": "ITmedia テクノロジー", "url": "https://rss.itmedia.co.jp/rss/2.0/news_technology.xml"},
        {"name": "PC Watch", "url": "https://pc.watch.impress.co.jp/data/rss/1.0/pcw/feed.rdf"},
        {"name": "DevelopersIO", "url": "https://dev.classmethod.jp/feed/"},
        {"name": "日経クロステック IT", "url": "https://xtech.nikkei.com/rss/xtech-it.rdf"},
        {"name": "Impress Watch", "url": "https://www.watch.impress.co.jp/data/rss/1.0/ipw/feed.rdf"},
    ],
    # --- 技術系 (英語) ---
    "tech_en": [
        {"name": "TechCrunch", "url": "https://techcrunch.com/feed/"},
        {"name": "The Verge", "url": "https://www.theverge.com/rss/index.xml"},
        {"name": "Ars Technica", "url": "https://feeds.arstechnica.com/arstechnica/index"},
        {"name": "Hacker News (Best)", "url": "https://hnrss.org/best"},
        {"name": "MIT Technology Review", "url": "https://www.technologyreview.com/feed/"},
        {"name": "Wired", "url": "https://www.wired.com/feed/rss"},
        {"name": "The Register", "url": "https://www.theregister.com/headlines.atom"},
        {"name": "ZDNet", "url": "https://www.zdnet.com/news/rss.xml"},
        {"name": "Dev.to", "url": "https://dev.to/feed"},
        {"name": "Slashdot", "url": "https://slashdot.org/index.rss"},
    ],
    # --- ビジネス系 (日本語) ---
    "business_ja": [
        {"name": "NHK ビジネス", "url": "https://www.nhk.or.jp/rss/news/cat4.xml"},
        {"name": "東洋経済オンライン", "url": "https://toyokeizai.net/list/feed/rss"},
        {"name": "ITmedia エンタープライズ", "url": "https://rss.itmedia.co.jp/rss/2.0/enterprise.xml"},
        {"name": "Google News 経済", "url": "https://news.google.com/rss/search?q=%E7%B5%8C%E6%B8%88+%E3%83%93%E3%82%B8%E3%83%8D%E3%82%B9&hl=ja&gl=JP&ceid=JP:ja"},
        {"name": "Google News IT企業", "url": "https://news.google.com/rss/search?q=IT%E4%BC%81%E6%A5%AD+%E3%82%B9%E3%82%BF%E3%83%BC%E3%83%88%E3%82%A2%E3%83%83%E3%83%97&hl=ja&gl=JP&ceid=JP:ja"},
        {"name": "Google News AI", "url": "https://news.google.com/rss/search?q=AI+%E4%BA%BA%E5%B7%A5%E7%9F%A5%E8%83%BD+%E6%96%B0%E6%A9%9F%E8%83%BD&hl=ja&gl=JP&ceid=JP:ja"},
        {"name": "Google News DX", "url": "https://news.google.com/rss/search?q=DX+%E3%83%87%E3%82%B8%E3%82%BF%E3%83%AB%E3%83%88%E3%83%A9%E3%83%B3%E3%82%B9%E3%83%95%E3%82%A9%E3%83%BC%E3%83%A1%E3%83%BC%E3%82%B7%E3%83%A7%E3%83%B3&hl=ja&gl=JP&ceid=JP:ja"},
        {"name": "Google News スタートアップ", "url": "https://news.google.com/rss/search?q=%E3%82%B9%E3%82%BF%E3%83%BC%E3%83%88%E3%82%A2%E3%83%83%E3%83%97+%E8%B3%87%E9%87%91%E8%AA%BF%E9%81%94+IT&hl=ja&gl=JP&ceid=JP:ja"},
        {"name": "Google News 半導体", "url": "https://news.google.com/rss/search?q=%E5%8D%8A%E5%B0%8E%E4%BD%93+%E3%83%86%E3%82%AF%E3%83%8E%E3%83%AD%E3%82%B8%E3%83%BC&hl=ja&gl=JP&ceid=JP:ja"},
        {"name": "Google News サイバーセキュリティ", "url": "https://news.google.com/rss/search?q=%E3%82%B5%E3%82%A4%E3%83%90%E3%83%BC%E3%82%BB%E3%82%AD%E3%83%A5%E3%83%AA%E3%83%86%E3%82%A3+%E8%84%86%E5%BC%B1%E6%80%A7&hl=ja&gl=JP&ceid=JP:ja"},
    ],
    # --- ビジネス系 (英語) ---
    "business_en": [
        {"name": "BBC Business", "url": "https://feeds.bbci.co.uk/news/business/rss.xml"},
        {"name": "CNBC Tech", "url": "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=19854910"},
        {"name": "Google News (Reuters Business)", "url": "https://news.google.com/rss/search?q=business+technology+site:reuters.com&hl=en&gl=US&ceid=US:en"},
        {"name": "Google News (Bloomberg Tech)", "url": "https://news.google.com/rss/search?q=technology+site:bloomberg.com&hl=en&gl=US&ceid=US:en"},
        {"name": "Google News (Financial Times)", "url": "https://news.google.com/rss/search?q=technology+business+site:ft.com&hl=en&gl=US&ceid=US:en"},
        {"name": "WSJ Tech", "url": "https://feeds.a.dj.com/rss/RSSWSJD.xml"},
        {"name": "Google News (Cloud Computing)", "url": "https://news.google.com/rss/search?q=cloud+computing+AWS+Azure+GCP&hl=en&gl=US&ceid=US:en"},
        {"name": "Google News (AI Business)", "url": "https://news.google.com/rss/search?q=artificial+intelligence+business&hl=en&gl=US&ceid=US:en"},
        {"name": "Google News (Startup Funding)", "url": "https://news.google.com/rss/search?q=startup+funding+technology&hl=en&gl=US&ceid=US:en"},
        {"name": "Google News (Semiconductor)", "url": "https://news.google.com/rss/search?q=semiconductor+chip+technology&hl=en&gl=US&ceid=US:en"},
    ],
    # --- SNS / トレンド ---
    "sns": [
        {"name": "はてなブックマーク IT", "url": "https://b.hatena.ne.jp/hotentry/it.rss"},
        {"name": "Reddit Technology", "url": "https://www.reddit.com/r/technology/.rss"},
        {"name": "Reddit Programming", "url": "https://www.reddit.com/r/programming/.rss"},
        {"name": "X(Twitter) IT話題 (国内)", "url": "https://news.google.com/rss/search?q=X+Twitter+IT+%E8%A9%B1%E9%A1%8C+%E3%83%88%E3%83%AC%E3%83%B3%E3%83%89&hl=ja&gl=JP&ceid=JP:ja"},
        {"name": "X(Twitter) Tech Trends", "url": "https://news.google.com/rss/search?q=twitter+X+trending+tech&hl=en&gl=US&ceid=US:en"},
        {"name": "Reddit DevOps", "url": "https://www.reddit.com/r/devops/.rss"},
        {"name": "Reddit SysAdmin", "url": "https://www.reddit.com/r/sysadmin/.rss"},
        {"name": "Qiita トレンド", "url": "https://qiita.com/popular-items/feed"},
        {"name": "Reddit Artificial Intelligence", "url": "https://www.reddit.com/r/artificial/.rss"},
        {"name": "Reddit Cloud Computing", "url": "https://www.reddit.com/r/cloudcomputing/.rss"},
    ],
}

HTTP_HEADERS = {
    "User-Agent": "daily-updates-bot/1.0 (GitHub Actions; +https://github.com)",
    "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml",
}

# カテゴリ別の記事数上限（出力サイズ制御用）
MAX_ARTICLES = {
    "azure": 20,
    "tech": 30,
    "business": 30,
    "sns": 20,
}


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


def _fetch_feed(url: str, since: datetime, max_items: int = 10) -> list[dict]:
    """単一の RSS/Atom フィードを取得し、since 以降の記事を返す。"""
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
    """カテゴリに属する全フィードから記事を収集する。"""
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
    return all_articles


def _limit_articles(articles: list[dict], category: str) -> list[dict]:
    """記事リストをカテゴリ上限に制限する。"""
    limit = MAX_ARTICLES.get(category, 10)
    if len(articles) > limit:
        print(f"  ※ {len(articles)} 件 → {limit} 件に制限")
    return articles[:limit]


# --- メイン処理 -----------------------------------------------------------------


def main():
    if len(sys.argv) < 2:
        print("Usage: python generate_daily_update.py YYYYMMDD [出力先パス]")
        sys.exit(1)

    target_date = sys.argv[1]
    output_path = sys.argv[2] if len(sys.argv) > 2 else "news_data.json"

    # 前日 8:00 JST 以降の記事を対象とする
    target_dt = datetime.strptime(target_date, "%Y%m%d").replace(tzinfo=JST)
    since = target_dt - timedelta(days=1) + timedelta(hours=8)

    print(f"対象日: {target_date}")
    print(f"収集期間: {since.isoformat()} 以降")
    print("ニュースを取得中...")

    print("\n[Azure]")
    azure_news = _limit_articles(fetch_category("azure", since), "azure")
    print(f"  → 合計: {len(azure_news)} 件")

    print("\n[技術系 日本語]")
    tech_ja = fetch_category("tech_ja", since)
    print(f"  → 合計: {len(tech_ja)} 件")

    print("\n[技術系 英語]")
    tech_en = fetch_category("tech_en", since)
    print(f"  → 合計: {len(tech_en)} 件")

    tech_news = _limit_articles(tech_ja + tech_en, "tech")

    print("\n[ビジネス系 日本語]")
    biz_ja = fetch_category("business_ja", since)
    print(f"  → 合計: {len(biz_ja)} 件")

    print("\n[ビジネス系 英語]")
    biz_en = fetch_category("business_en", since)
    print(f"  → 合計: {len(biz_en)} 件")

    business_news = _limit_articles(biz_ja + biz_en, "business")

    print("\n[SNS / トレンド]")
    sns_news = _limit_articles(fetch_category("sns", since), "sns")
    print(f"  → 合計: {len(sns_news)} 件")

    data = {
        "target_date": target_date,
        "collected_since": since.isoformat(),
        "categories": {
            "azure": azure_news,
            "tech": tech_news,
            "business": business_news,
            "sns": sns_news,
        },
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    total = len(azure_news) + len(tech_news) + len(business_news) + len(sns_news)
    print(f"\n収集完了: {output_path} （合計 {total} 件）")


if __name__ == "__main__":
    main()
