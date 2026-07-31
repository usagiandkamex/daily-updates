"""connpass イベントカレンダーデータ生成スクリプト

関東（東京都・神奈川県）またはオンラインで開催される IT 系イベントを
connpass から取得し、docs/events.json に保存する。

Usage:
    python scripts/generate_events_calendar.py
"""

from __future__ import annotations

import json
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse

import feedparser
import requests

# ---------------------------------------------------------------------------
# 定数
# ---------------------------------------------------------------------------

CONNPASS_RSS_URL = "https://connpass.com/search/"
CONNPASS_API_URL = "https://connpass.com/api/v2/events/"
CONNPASS_API_FETCH_COUNT = 100
CONNPASS_API_MAX_PAGES = 10
CONNPASS_API_EARLY_STOP_BUFFER = 100

HTTP_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; daily-updates-bot/1.0)",
    "Accept": "application/rss+xml, application/xml, text/xml",
}

JST = timezone(timedelta(hours=9), "JST")

# 関東の都道府県 ID（connpass search の pref_id パラメータ）
_PREFECTURE_IDS: dict[str, int] = {
    "東京都": 13,
    "神奈川県": 14,
}

# 当月 + 何か月先まで取得するか
CALENDAR_LOOKAHEAD_MONTHS = 2

# 保存する最大イベント件数
MAX_CALENDAR_EVENTS = 500

# イベント説明を取得するイベントの最大件数
MAX_ENRICH_EVENTS = 100

# 説明文の最大文字数（これを超えたら切り詰め）
MAX_DESCRIPTION_CHARS = 400

# 説明取得の並列数
_ENRICH_WORKERS = 5

# イベントページ取得タイムアウト（秒）
_PAGE_FETCH_TIMEOUT = 10

# ベンダーイベントニュース：何日前までの記事を含めるか（デフォルト）
VENDOR_EVENT_LOOKBACK_DAYS = 30

# 参加レポート・参加記など、イベント後に公開されるコンテンツの取り込み期間
# （デフォルトより長めに設定し、直近 3 か月以内の参加レポートを取得する）
VENDOR_REPORT_LOOKBACK_DAYS = 90

# 大手ベンダー・大規模カンファレンス情報取得用 RSS フィード（Google News 検索）
# 各フィードには「name」（表示名）「url」（RSS URL）「place」（開催場所候補）を定義する。
# オプションで「lookback_days」を指定すると、フィード個別の取り込み期間を設定できる（未指定時は VENDOR_EVENT_LOOKBACK_DAYS を使用）。
VENDOR_EVENT_NEWS_FEEDS: list[dict] = [
    # Microsoft
    {
        "name": "Microsoft Build",
        "url": "https://news.google.com/rss/search?q=Microsoft+Build+%E3%82%AB%E3%83%B3%E3%83%95%E3%82%A1%E3%83%AC%E3%83%B3%E3%82%B9+%E6%83%85%E5%A0%B1&hl=ja&gl=JP&ceid=JP:ja",
        "place": "Seattle / オンライン",
    },
    {
        "name": "Microsoft Ignite",
        "url": "https://news.google.com/rss/search?q=Microsoft+Ignite+%E3%82%AB%E3%83%B3%E3%83%95%E3%82%A1%E3%83%AC%E3%83%B3%E3%82%B9+%E6%83%85%E5%A0%B1&hl=ja&gl=JP&ceid=JP:ja",
        "place": "Chicago / オンライン",
    },
    # AWS
    {
        "name": "AWS Summit Japan",
        "url": "https://news.google.com/rss/search?q=AWS+Summit+Japan+%E9%96%8B%E5%82%AC+%E3%82%A4%E3%83%99%E3%83%B3%E3%83%88&hl=ja&gl=JP&ceid=JP:ja",
        "place": "東京 / オンライン",
    },
    {
        "name": "AWS re:Invent",
        "url": "https://news.google.com/rss/search?q=AWS+re%3AInvent+%E3%82%A4%E3%83%99%E3%83%B3%E3%83%88+%E6%83%85%E5%A0%B1&hl=ja&gl=JP&ceid=JP:ja",
        "place": "Las Vegas / オンライン",
    },
    # Google Cloud
    {
        "name": "Google Cloud Next",
        "url": "https://news.google.com/rss/search?q=Google+Cloud+Next+%E3%82%AB%E3%83%B3%E3%83%95%E3%82%A1%E3%83%AC%E3%83%B3%E3%82%B9+%E6%83%85%E5%A0%B1&hl=ja&gl=JP&ceid=JP:ja",
        "place": "Las Vegas / オンライン",
    },
    # CNCF・大規模コミュニティカンファレンス
    {
        "name": "KubeCon + CloudNativeCon",
        "url": "https://news.google.com/rss/search?q=KubeCon+CloudNativeCon+%E3%82%AB%E3%83%B3%E3%83%95%E3%82%A1%E3%83%AC%E3%83%B3%E3%82%B9+%E6%83%85%E5%A0%B1&hl=ja&gl=JP&ceid=JP:ja",
        "place": "現地開催 / オンライン",
    },
    # Linux Foundation
    {
        "name": "Open Source Summit Japan",
        "url": "https://news.google.com/rss/search?q=Open+Source+Summit+Japan+%E3%82%A4%E3%83%99%E3%83%B3%E3%83%88+%E6%83%85%E5%A0%B1&hl=ja&gl=JP&ceid=JP:ja",
        "place": "東京 / オンライン",
    },
    # HashiCorp
    {
        "name": "HashiConf",
        "url": "https://news.google.com/rss/search?q=HashiConf+%E3%82%AB%E3%83%B3%E3%83%95%E3%82%A1%E3%83%AC%E3%83%B3%E3%82%B9+%E6%83%85%E5%A0%B1&hl=ja&gl=JP&ceid=JP:ja",
        "place": "現地開催 / オンライン",
    },
    # GitHub
    {
        "name": "GitHub Universe",
        "url": "https://news.google.com/rss/search?q=GitHub+Universe+%E3%82%AB%E3%83%B3%E3%83%95%E3%82%A1%E3%83%AC%E3%83%B3%E3%82%B9+%E6%83%85%E5%A0%B1&hl=ja&gl=JP&ceid=JP:ja",
        "place": "San Francisco / オンライン",
    },
    # Red Hat
    {
        "name": "Red Hat Summit",
        "url": "https://news.google.com/rss/search?q=Red+Hat+Summit+%E3%82%AB%E3%83%B3%E3%83%95%E3%82%A1%E3%83%AC%E3%83%B3%E3%82%B9+%E6%83%85%E5%A0%B1&hl=ja&gl=JP&ceid=JP:ja",
        "place": "Boston / オンライン",
    },
    # VMware (Broadcom)
    {
        "name": "VMware Explore",
        "url": "https://news.google.com/rss/search?q=VMware+Explore+%E3%82%AB%E3%83%B3%E3%83%95%E3%82%A1%E3%83%AC%E3%83%B3%E3%82%B9+%E6%83%85%E5%A0%B1&hl=ja&gl=JP&ceid=JP:ja",
        "place": "Las Vegas / オンライン",
    },
    # Databricks
    {
        "name": "Data + AI Summit",
        "url": "https://news.google.com/rss/search?q=Databricks+Data+AI+Summit+%E3%82%AB%E3%83%B3%E3%83%95%E3%82%A1%E3%83%AC%E3%83%B3%E3%82%B9+%E6%83%85%E5%A0%B1&hl=ja&gl=JP&ceid=JP:ja",
        "place": "San Francisco / オンライン",
    },
    # OpenAI
    {
        "name": "OpenAI DevDay",
        "url": "https://news.google.com/rss/search?q=OpenAI+DevDay+%E3%82%A4%E3%83%99%E3%83%B3%E3%83%88+%E6%83%85%E5%A0%B1&hl=ja&gl=JP&ceid=JP:ja",
        "place": "San Francisco / オンライン",
    },
    # NVIDIA
    {
        "name": "NVIDIA GTC",
        "url": "https://news.google.com/rss/search?q=NVIDIA+GTC+%E3%82%AB%E3%83%B3%E3%83%95%E3%82%A1%E3%83%AC%E3%83%B3%E3%82%B9+%E6%83%85%E5%A0%B1&hl=ja&gl=JP&ceid=JP:ja",
        "place": "San Jose / オンライン",
    },
    # Google
    {
        "name": "Google I/O",
        "url": "https://news.google.com/rss/search?q=Google+IO+%E3%82%AB%E3%83%B3%E3%83%95%E3%82%A1%E3%83%AC%E3%83%B3%E3%82%B9+%E6%83%85%E5%A0%B1&hl=ja&gl=JP&ceid=JP:ja",
        "place": "Mountain View / オンライン",
    },
    # ---------------------------------------------------------------------------
    # 参加レポート・参加記フィード（イベント開催後に公開されるコンテンツを取得）
    # lookback_days に VENDOR_REPORT_LOOKBACK_DAYS を設定し、
    # 直近 90 日以内の参加レポートを収集する。
    # ---------------------------------------------------------------------------
    # Microsoft
    {
        "name": "Microsoft Build 参加レポート",
        "url": "https://news.google.com/rss/search?q=Microsoft+Build+%E5%8F%82%E5%8A%A0%E3%83%AC%E3%83%9D%E3%83%BC%E3%83%88&hl=ja&gl=JP&ceid=JP:ja",
        "place": "Seattle / オンライン",
        "lookback_days": VENDOR_REPORT_LOOKBACK_DAYS,
    },
    {
        "name": "Microsoft Ignite 参加レポート",
        "url": "https://news.google.com/rss/search?q=Microsoft+Ignite+%E5%8F%82%E5%8A%A0%E3%83%AC%E3%83%9D%E3%83%BC%E3%83%88&hl=ja&gl=JP&ceid=JP:ja",
        "place": "Chicago / オンライン",
        "lookback_days": VENDOR_REPORT_LOOKBACK_DAYS,
    },
    # AWS
    {
        "name": "AWS Summit Japan 参加レポート",
        "url": "https://news.google.com/rss/search?q=AWS+Summit+Japan+%E5%8F%82%E5%8A%A0%E3%83%AC%E3%83%9D%E3%83%BC%E3%83%88&hl=ja&gl=JP&ceid=JP:ja",
        "place": "東京 / オンライン",
        "lookback_days": VENDOR_REPORT_LOOKBACK_DAYS,
    },
    {
        "name": "AWS re:Invent 参加レポート",
        "url": "https://news.google.com/rss/search?q=AWS+re%3AInvent+%E5%8F%82%E5%8A%A0%E3%83%AC%E3%83%9D%E3%83%BC%E3%83%88&hl=ja&gl=JP&ceid=JP:ja",
        "place": "Las Vegas / オンライン",
        "lookback_days": VENDOR_REPORT_LOOKBACK_DAYS,
    },
    # Google Cloud
    {
        "name": "Google Cloud Next 参加レポート",
        "url": "https://news.google.com/rss/search?q=Google+Cloud+Next+%E5%8F%82%E5%8A%A0%E3%83%AC%E3%83%9D%E3%83%BC%E3%83%88&hl=ja&gl=JP&ceid=JP:ja",
        "place": "Las Vegas / オンライン",
        "lookback_days": VENDOR_REPORT_LOOKBACK_DAYS,
    },
    # CNCF
    {
        "name": "KubeCon 参加レポート",
        "url": "https://news.google.com/rss/search?q=KubeCon+%E5%8F%82%E5%8A%A0%E3%83%AC%E3%83%9D%E3%83%BC%E3%83%88&hl=ja&gl=JP&ceid=JP:ja",
        "place": "現地開催 / オンライン",
        "lookback_days": VENDOR_REPORT_LOOKBACK_DAYS,
    },
    # Google
    {
        "name": "Google I/O 参加レポート",
        "url": "https://news.google.com/rss/search?q=Google+IO+%E5%8F%82%E5%8A%A0%E3%83%AC%E3%83%9D%E3%83%BC%E3%83%88&hl=ja&gl=JP&ceid=JP:ja",
        "place": "Mountain View / オンライン",
        "lookback_days": VENDOR_REPORT_LOOKBACK_DAYS,
    },
    # NVIDIA
    {
        "name": "NVIDIA GTC 参加レポート",
        "url": "https://news.google.com/rss/search?q=NVIDIA+GTC+%E5%8F%82%E5%8A%A0%E3%83%AC%E3%83%9D%E3%83%BC%E3%83%88&hl=ja&gl=JP&ceid=JP:ja",
        "place": "San Jose / オンライン",
        "lookback_days": VENDOR_REPORT_LOOKBACK_DAYS,
    },
    # GitHub
    {
        "name": "GitHub Universe 参加レポート",
        "url": "https://news.google.com/rss/search?q=GitHub+Universe+%E5%8F%82%E5%8A%A0%E3%83%AC%E3%83%9D%E3%83%BC%E3%83%88&hl=ja&gl=JP&ceid=JP:ja",
        "place": "San Francisco / オンライン",
        "lookback_days": VENDOR_REPORT_LOOKBACK_DAYS,
    },
]

# ベンダーイベントニュース：フィードごとの最大取得記事数
_VENDOR_EVENT_MAX_ENTRIES_PER_FEED = 5

# ---------------------------------------------------------------------------
# IT 関連イベント判定
# ---------------------------------------------------------------------------

_IT_KEYWORDS: list[str] = [
    # クラウド・インフラ
    "cloud", "クラウド", "azure", "aws", "gcp", "google cloud",
    "kubernetes", "k8s", "docker", "terraform", "ansible", "iac",
    "serverless", "サーバーレス", "container", "コンテナ",
    # DevOps・SRE・運用
    "devops", "devsecops", "mlops", "aiops", "finops",
    "platform engineering",
    # AI・機械学習
    "llm", "機械学習", "深層学習", "deep learning",
    "chatgpt", "openai", "anthropic", "copilot", "生成ai", "生成AI",
    "langchain", "hugging face",
    # セキュリティ
    "security", "セキュリティ", "脆弱性", "pentest",
    "zerotrust", "zero trust", "ゼロトラスト",
    # プログラミング言語・フレームワーク
    "python", "javascript", "typescript", "java", "rust",
    "react", "vue", "angular", "django", "rails",
    "マイクロサービス", "microservices",
    # データ・分析
    "データ", "analytics", "アナリティクス", "databricks", "snowflake", "bigquery",
    # IT全般
    "エンジニア", "engineer", "developer", "デベロッパー",
    "プログラミング", "programming", "iot", "5g",
    # コミュニティ・イベント形式
    "勉強会", "ハンズオン", "オープンソース", "open source",
    # コミュニティ名
    "jaws", "jawsug", "azure user group", "jug", "gcpug",
    "microsoft",
    # IT インフラ・その他
    "インフラ", "infra", "database", "blockchain", "web3",
]

_IT_KEYWORDS_WORD_BOUNDARY: frozenset[str] = frozenset({
    "ai", "ml", "go", "sre", "rag", "soc", "db", "api",
})


def _is_it_event(title: str, desc: str) -> bool:
    """イベントが IT 関連かどうかを判定する。"""
    text = (title + " " + desc).lower()
    for kw in _IT_KEYWORDS:
        if kw.lower() in text:
            return True
    for kw in _IT_KEYWORDS_WORD_BOUNDARY:
        if re.search(r"(?<![a-z0-9])" + re.escape(kw) + r"(?![a-z0-9])", text):
            return True
    return False


# ---------------------------------------------------------------------------
# connpass API レスポンスの description フィールド（HTML）からテキストを抽出
# ---------------------------------------------------------------------------

class _HTMLTextExtractor(HTMLParser):
    """HTML タグを除去してプレーンテキストを抽出するシンプルなパーサー。

    connpass v2 API が返す ``description`` フィールド（HTML 形式）を
    プレーンテキストに変換するために使用する。
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._parts: list[str] = []

    def handle_data(self, data: str) -> None:
        if data.strip():
            self._parts.append(data)

    def get_text(self) -> str:
        return " ".join(self._parts)


def _extract_text_from_html(html_text: str) -> str:
    """HTML タグを除去してプレーンテキストを返す。

    取得した文字列の余分な空白を正規化して返す。
    パース失敗時は空文字列を返す。
    """
    if not html_text:
        return ""
    try:
        parser = _HTMLTextExtractor()
        parser.feed(html_text)
        return " ".join(parser.get_text().split())
    except Exception as exc:
        print(f"  connpass: HTML テキスト抽出で予期しないエラー: {type(exc).__name__}")
        return ""


# ---------------------------------------------------------------------------
# connpass イベントページから説明文を取得
# ---------------------------------------------------------------------------

class _ConnpassEventPageParser(HTMLParser):
    """connpass イベントページから説明文（event_description_content）を抽出する。"""

    _TARGET_CLASS = "event_description_content"

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._in_target = False
        self._target_tag = ""
        self._depth = 0
        self._parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if not self._in_target:
            attr_dict = dict(attrs)
            classes = set((attr_dict.get("class") or "").split())
            if self._TARGET_CLASS in classes:
                self._in_target = True
                self._target_tag = tag
                self._depth = 0
        elif tag == self._target_tag:
            self._depth += 1

    def handle_endtag(self, tag: str) -> None:
        if not self._in_target:
            return
        if tag == self._target_tag:
            if self._depth == 0:
                self._in_target = False
            else:
                self._depth -= 1

    def handle_data(self, data: str) -> None:
        if self._in_target:
            self._parts.append(data)

    def get_text(self) -> str:
        return " ".join(part for part in self._parts if part.strip())


_PAGE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; daily-updates-bot/1.0)",
    "Accept": "text/html",
}


def _is_connpass_event_url(url: str) -> bool:
    """URL が connpass.com（サブドメイン可）の HTTPS イベント URL かを判定する。

    SSRF 対策として、`_enrich_descriptions()` の HTTP 取得対象を connpass.com に
    限定するために使用する。
    """
    if not url:
        return False
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    if parsed.scheme != "https":
        return False
    host = (parsed.hostname or "").lower()
    if host != "connpass.com" and not host.endswith(".connpass.com"):
        return False
    # 説明文取得対象は connpass の「イベントページ」(/event/...) のみに限定する。
    return parsed.path.startswith("/event/")


def _truncate_description(text: str, max_chars: int = MAX_DESCRIPTION_CHARS) -> str:
    """説明文を max_chars 文字以内に切り詰める（"…" を含めて max_chars 以内）。

    超過時は単語境界（最後のスペース）で切り詰めて末尾に "…" を付与する。
    """
    if len(text) <= max_chars:
        return text
    if max_chars <= 1:
        return "…"[:max_chars]
    # "…" 1 文字分を確保した上で単語境界を探す。
    head = text[: max_chars - 1]
    boundary = head.rsplit(" ", 1)[0] if " " in head else head
    return boundary + "…"


def _fetch_event_description(url: str) -> str:
    """connpass イベントページから説明文テキストを取得して返す。

    取得に失敗した場合は空文字列を返す。
    """
    try:
        resp = requests.get(
            url,
            headers=_PAGE_HEADERS,
            timeout=_PAGE_FETCH_TIMEOUT,
            allow_redirects=False,
        )
        # SSRF 対策: リダイレクトに追従しない。3xx は connpass 外への遷移
        # 可能性があるため失敗扱いとする（allow_redirects=False のため
        # requests は 3xx をそのまま返す）。
        if 300 <= resp.status_code < 400:
            print(
                f"  connpass: 説明文取得スキップ (リダイレクト {resp.status_code}): {url}"
            )
            return ""
        resp.raise_for_status()
        parser = _ConnpassEventPageParser()
        parser.feed(resp.text)
        # 余分な空白を正規化して返す
        return " ".join(parser.get_text().split())
    except requests.RequestException as exc:
        print(f"  connpass: 説明文取得失敗 ({url}): {type(exc).__name__}")
        return ""
    except Exception as exc:
        print(f"  connpass: 説明文取得で予期しないエラー ({url}): {type(exc).__name__}")
        return ""


def _enrich_descriptions(events: list[dict]) -> None:
    """connpass イベントページからイベント説明を取得し description フィールドを追加する。

    対象は connpass.com の HTTPS URL を持ち、かつ description が未設定の
    先頭 MAX_ENRICH_EVENTS 件のみ（SSRF 対策で他ホストは除外）。
    connpass v2 API 経路ではすでに description が設定済みのため実質スキップされる。
    取得したテキストは MAX_DESCRIPTION_CHARS 文字に切り詰めて保存する。
    """
    targets = [
        ev for ev in events
        if _is_connpass_event_url(ev.get("event_url", "")) and not ev.get("description")
    ]
    targets = targets[:MAX_ENRICH_EVENTS]
    if not targets:
        return

    print(f"  イベント説明を取得中 ({len(targets)} 件)…")

    def _fetch_one(ev: dict) -> tuple[dict, str]:
        return ev, _fetch_event_description(ev["event_url"])

    done = 0
    with ThreadPoolExecutor(max_workers=_ENRICH_WORKERS) as executor:
        futures = {executor.submit(_fetch_one, ev): ev for ev in targets}
        for future in as_completed(futures):
            try:
                ev, text = future.result()
                if text:
                    ev["description"] = _truncate_description(text)
            except Exception as exc:
                print(f"  connpass: 説明文補完で予期しないエラー: {type(exc).__name__}")
            done += 1
            if done % 20 == 0:
                print(f"    {done}/{len(targets)} 件完了")

    print(f"  説明文取得完了（{sum(1 for ev in targets if ev.get('description'))} 件取得）")


# ---------------------------------------------------------------------------
# RSS パース
# ---------------------------------------------------------------------------

def _parse_started_at(entry) -> str:
    """feedparser エントリから開催日時文字列（JST）を取得する。"""
    pub = entry.get("published_parsed")
    if pub is None:
        return ""
    try:
        dt = datetime(*pub[:6], tzinfo=timezone.utc).astimezone(JST)
        return dt.strftime("%Y/%m/%d %H:%M")
    except Exception:
        return ""


def _parse_started_at_api(started_at: str) -> str:
    """connpass v2 API の started_at を JST 文字列（YYYY/MM/DD HH:MM）に変換する。"""
    if not started_at:
        return ""
    try:
        # connpass v2 API は ISO8601（例: 2026-05-20T10:00:00+09:00 / ...Z）を返す。
        dt = datetime.fromisoformat(started_at.replace("Z", "+00:00")).astimezone(JST)
        return dt.strftime("%Y/%m/%d %H:%M")
    except (TypeError, ValueError):
        return ""


# ---------------------------------------------------------------------------
# イベント取得
# ---------------------------------------------------------------------------

def _build_search_months(today: datetime, lookahead: int) -> list[str]:
    """当月から lookahead か月先までの YYYYMM リストを返す。"""
    months: list[str] = []
    y, m = today.year, today.month
    for _ in range(lookahead + 1):
        months.append(f"{y:04d}{m:02d}")
        m += 1
        if m > 12:
            m = 1
            y += 1
    return months


def _fetch_rss_events(
    params: dict,
    place: str,
    today_str: str,
    seen_urls: set[str],
    label: str,
) -> tuple[list[dict], bool]:
    """connpass RSS を1回呼び出してイベントリストを返す（共通処理）。

    - URL 重複（seen_urls）と IT キーワードフィルタを適用
    - 開催日が today_str より前のイベントは除外（日付単位、当日は表示対象）
    - 取得件数はログに出力
    - 戻り値は (収集したイベント, 成功フラグ)。HTTP 例外、または
      ``feedparser`` がパース失敗（``feed.bozo`` が真かつ ``entries`` が空）
      とした場合は成功フラグ False を返す。
    """
    collected: list[dict] = []
    try:
        resp = requests.get(
            CONNPASS_RSS_URL,
            params=params,
            headers=HTTP_HEADERS,
            timeout=15,
        )
        resp.raise_for_status()
        feed = feedparser.parse(resp.content)
        # feedparser はパース失敗を例外ではなく feed.bozo フラグで通知する。
        # 壊れた RSS / 想定外レスポンス（HTML エラーページ等）を成功扱いに
        # してしまうと events.json を空で上書きする恐れがあるため、
        # entries が空のときに限り bozo を失敗扱いとする。
        if getattr(feed, "bozo", False) and not feed.entries:
            bozo_exc = getattr(feed, "bozo_exception", None)
            print(f"  connpass RSS ({label}): RSS パース失敗 ({bozo_exc})")
            return collected, False
        for entry in feed.entries:
            url = entry.get("link", "")
            if not url or url in seen_urls:
                continue
            # 想定外ホスト/パスの URL（SSRF / 表示崩れの原因）は破棄する。
            if not _is_connpass_event_url(url):
                continue
            title = entry.get("title", "").strip()
            desc = entry.get("summary", "").strip()
            if not _is_it_event(title, desc):
                continue
            started_at = _parse_started_at(entry)
            # started_at が無いイベントはカレンダー上に表示できないため除外する。
            if not started_at:
                continue
            # 開催日（日付部分）が今日より前のイベントをスキップ。
            # 当日開始のイベントは開始時刻に関わらず表示対象とする。
            if started_at[:10] < today_str:
                continue
            seen_urls.add(url)
            collected.append({
                "title": title,
                "event_url": url,
                "started_at": started_at,
                "place": place,
                "catch": desc[:200],
            })
        print(f"  connpass RSS ({label}): {len(collected)} 件取得")
    except Exception as e:
        print(f"  connpass RSS ({label}): 取得失敗 ({e})")
        return collected, False
    return collected, True


def _fetch_one_vendor_feed(feed_info: dict, today: datetime) -> list[dict]:
    """単一のベンダーイベント RSS フィードを取得し、イベントリストを返す。

    - feed_info は ``name``、``url`` 必須、``place``・``lookback_days`` 省略可
    - ``lookback_days`` は int かつ 1 以上のみ受け付け、不正値は
      VENDOR_EVENT_LOOKBACK_DAYS にフォールバック
    - 計算した cutoff より前に公開された記事は除外
    - 取得失敗時は空リストを返す（fetch_vendor_news_events でのログ出力のため例外を抑制）
    """
    results: list[dict] = []
    try:
        name = feed_info["name"]
        url = feed_info["url"]
        place = feed_info.get("place", "")
        lookback_days = feed_info.get("lookback_days", VENDOR_EVENT_LOOKBACK_DAYS)
        if isinstance(lookback_days, bool) or not isinstance(lookback_days, int) or lookback_days <= 0:
            print(
                f"  ベンダーイベント RSS ({name}): lookback_days が不正 ({lookback_days!r}) のため "
                f"{VENDOR_EVENT_LOOKBACK_DAYS} 日にフォールバック"
            )
            lookback_days = VENDOR_EVENT_LOOKBACK_DAYS
        cutoff = today - timedelta(days=lookback_days)
        cutoff_str = cutoff.strftime("%Y/%m/%d")
        resp = requests.get(url, headers=HTTP_HEADERS, timeout=10)
        resp.raise_for_status()
        feed = feedparser.parse(resp.content)
        if getattr(feed, "bozo", False) and not feed.entries:
            bozo_exc = getattr(feed, "bozo_exception", None)
            detail = f" ({bozo_exc})" if bozo_exc is not None else ""
            print(f"  ベンダーイベント RSS ({name}): RSS パース失敗{detail}")
            return results
        for entry in feed.entries[:_VENDOR_EVENT_MAX_ENTRIES_PER_FEED]:
            article_url = entry.get("link", "")
            if not article_url:
                continue
            title = entry.get("title", "").strip()
            desc = entry.get("summary", "").strip()
            if not title:
                continue
            started_at = _parse_started_at(entry)
            if not started_at:
                continue
            # 公開日が cutoff より前の記事は除外する。
            if started_at[:10] < cutoff_str:
                continue
            results.append({
                "title": f"[{name}] {title}",
                "event_url": article_url,
                "started_at": started_at,
                "place": place,
                "catch": desc[:200],
                "vendor_event": True,
            })
        print(f"  ベンダーイベント RSS ({name}): {len(results)} 件取得")
    except Exception as e:
        label = feed_info.get("name", repr(feed_info))
        print(f"  ベンダーイベント RSS ({label}): 取得失敗 ({e})")
    return results


def fetch_vendor_news_events(today: datetime) -> list[dict]:
    """大手ベンダー・大規模コミュニティカンファレンスの最新情報を Google News RSS から取得する。

    VENDOR_EVENT_NEWS_FEEDS に定義された各カンファレンス（Microsoft Build / Ignite、
    AWS Summit / re:Invent、Google Cloud Next、KubeCon 等）の最新ニュース記事を取得し、
    記事の公開日をカレンダー表示日として events.json に追加する。

    各フィードに ``lookback_days`` が設定されている場合はその期間を使用し、
    未設定の場合は VENDOR_EVENT_LOOKBACK_DAYS（デフォルト 30 日）を適用する。
    参加レポート・参加記フィードには VENDOR_REPORT_LOOKBACK_DAYS（90 日）を
    設定することを推奨する（各フィードの ``lookback_days`` フィールドで指定）。

    各エントリには「ベンダーイベント情報」であることを示す place フィールドおよび
    vendor_event フラグが設定される。

    取得失敗は警告のみでスキップし、connpass 系の取得には影響しない。
    全フィードを並列取得してレイテンシを削減する（ThreadPoolExecutor）。
    """
    if not VENDOR_EVENT_NEWS_FEEDS:
        return []
    print(f"  ベンダーイベント RSS を並列取得中 ({today.strftime('%Y/%m/%d')} 時点)...")
    events: list[dict] = []
    seen_urls: set[str] = set()

    with ThreadPoolExecutor(max_workers=min(len(VENDOR_EVENT_NEWS_FEEDS), 8)) as executor:
        futures = {
            executor.submit(_fetch_one_vendor_feed, feed_info, today): feed_info
            for feed_info in VENDOR_EVENT_NEWS_FEEDS
        }
        for future in as_completed(futures):
            try:
                for ev in future.result():
                    if ev["event_url"] not in seen_urls:
                        seen_urls.add(ev["event_url"])
                        events.append(ev)
            except Exception as e:
                feed_info = futures[future]
                name = feed_info.get("name", str(feed_info))
                print(f"  ベンダーイベント RSS ({name}): フューチャー取得失敗 ({e})")

    return events


def _fetch_api_events(
    params: dict,
    place: str,
    today_str: str,
    seen_urls: set[str],
    label: str,
    api_key: str,
) -> tuple[list[dict], bool]:
    """connpass v2 API を呼び出してイベントリストを返す（APIキー利用）。

    v2 API の ``count``（最大100）+ ``start``（1-indexed）でページングし、
    ``CONNPASS_API_MAX_PAGES`` の上限内で順次取得する。
    戻り値は ``(収集したイベント, 成功フラグ)``。
    """
    collected: list[dict] = []
    connpass_headers = {
        **HTTP_HEADERS,
        "Accept": "application/json",
        "X-API-Key": api_key,
    }
    start = 1
    fetched_any_page = False
    for page_num in range(1, CONNPASS_API_MAX_PAGES + 1):
        try:
            resp = requests.get(
                CONNPASS_API_URL,
                params={
                    **params,
                    "count": CONNPASS_API_FETCH_COUNT,
                    "start": start,
                    "order": 2,
                },
                headers=connpass_headers,
                timeout=30,
                allow_redirects=False,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            if not fetched_any_page:
                print(f"  connpass API ({label}): 取得失敗 ({e})")
                return collected, False
            print(f"  connpass API ({label} p{page_num}): 追加取得失敗 ({e})")
            break

        if not isinstance(data, dict):
            if not fetched_any_page:
                print(
                    f"  connpass API ({label}): 応答形式が不正 "
                    f"({type(data).__name__})"
                )
                return collected, False
            print(
                f"  connpass API ({label} p{page_num}): 追加取得の応答形式が不正 "
                f"({type(data).__name__})"
            )
            break

        events_raw = data.get("events")
        if events_raw is None:
            events = []
        elif not isinstance(events_raw, list):
            if not fetched_any_page:
                print(
                    f"  connpass API ({label}): events の形式が不正 "
                    f"({type(events_raw).__name__})"
                )
                return collected, False
            print(
                f"  connpass API ({label} p{page_num}): 追加取得の events 形式が不正 "
                f"({type(events_raw).__name__})"
            )
            break
        else:
            events = events_raw

        fetched_any_page = True
        has_returned = "results_returned" in data
        has_available = "results_available" in data
        returned_raw = data.get("results_returned")
        available_raw = data.get("results_available")
        returned = returned_raw if type(returned_raw) is int else len(events)
        available = available_raw if type(available_raw) is int else 0
        if has_returned and type(returned_raw) is not int:
            print(
                f"  警告: connpass API ({label}): results_returned の形式が不正 "
                f"({type(returned_raw).__name__})"
            )
        if has_available and type(available_raw) is not int:
            print(
                f"  警告: connpass API ({label}): results_available の形式が不正 "
                f"({type(available_raw).__name__})"
            )
        for event in events:
            if not isinstance(event, dict):
                continue
            url_raw = event.get("url") or event.get("event_url", "")
            if not isinstance(url_raw, str):
                continue
            url = url_raw.strip()
            if not url or url in seen_urls:
                continue
            if not _is_connpass_event_url(url):
                continue
            title_raw = event.get("title")
            catch_raw = event.get("catch")
            desc_html_raw = event.get("description")
            title = title_raw.strip() if isinstance(title_raw, str) else ""
            catch = catch_raw.strip() if isinstance(catch_raw, str) else ""
            desc_html = desc_html_raw.strip() if isinstance(desc_html_raw, str) else ""
            desc_plain = _extract_text_from_html(desc_html) if desc_html else ""
            # catch と description 両方を IT フィルタに使用する
            filter_text = (catch + " " + desc_plain).strip()
            if not _is_it_event(title, filter_text):
                continue
            started_at = _parse_started_at_api(event.get("started_at", ""))
            if not started_at:
                continue
            if started_at[:10] < today_str:
                continue
            seen_urls.add(url)
            ev_dict: dict = {
                "title": title,
                "event_url": url,
                "started_at": started_at,
                "place": place,
                "catch": catch[:200],
            }
            # API から取得した説明文（HTML）をプレーンテキストに変換して保存する。
            # これにより connpass ページへのスクレイピングが不要になる。
            if desc_plain:
                ev_dict["description"] = _truncate_description(desc_plain)
            collected.append(ev_dict)

        # seen_urls は全検索条件で共有しており、最終的な events.json の件数上限
        # （MAX_CALENDAR_EVENTS）付近まで到達したら全体の取得コストを抑えるため
        # この検索条件の追加ページ取得を早期終了する。
        if len(seen_urls) >= MAX_CALENDAR_EVENTS + CONNPASS_API_EARLY_STOP_BUFFER:
            print(
                f"  connpass API ({label}): 取得件数が上限付近のため追加ページ取得を終了 "
                f"({len(seen_urls)} 件)"
            )
            break

        next_start = start + returned
        if (
            (available > 0 and next_start > available)
            or returned < CONNPASS_API_FETCH_COUNT
        ):
            break
        start = next_start

    print(f"  connpass API ({label}): {len(collected)} 件取得")
    return collected, True


def fetch_events(today: datetime) -> list[dict]:
    """今日以降のイベントを connpass から取得する。

    CONNPASS_API_KEY が設定されている場合は v2 API（X-API-Key）を優先し、
    未設定時は既存 RSS 検索を使用する。
    関東（東京都・神奈川県）とオンラインの 2 系統で取得し、重複を排除して
    日時昇順に返す。
    なお v2 API では pref_id/online 相当の構造化パラメータが無いため、
    keyword ベースの絞り込みは best effort（誤検出・取りこぼしあり）となる。

    全リクエスト失敗時は :class:`RuntimeError` を送出する
    （docs/events.json を空で上書きしないため）。
    """
    today_str = today.strftime("%Y/%m/%d")
    months = _build_search_months(today, CALENDAR_LOOKAHEAD_MONTHS)

    events: list[dict] = []
    seen_urls: set[str] = set()
    attempts = 0
    failures = 0
    api_key = os.environ.get("CONNPASS_API_KEY", "").strip()
    use_api = bool(api_key)
    if use_api:
        print("  CONNPASS_API_KEY を検出: connpass v2 API を利用します")
    early_stop_limit = MAX_CALENDAR_EVENTS + CONNPASS_API_EARLY_STOP_BUFFER

    def _api_limit_reached() -> bool:
        return use_api and len(seen_urls) >= early_stop_limit

    # --- 都道府県別検索 ---
    for pref, pref_id in _PREFECTURE_IDS.items():
        for ym in months:
            if use_api:
                # v2 API には RSS の pref_id 相当パラメータが無いため、
                # keyword に都道府県名を指定して近似的に抽出する。
                # 地名の言及ベースのため誤検出/取りこぼしがあり得る（best effort）。
                collected, ok = _fetch_api_events(
                    params={"keyword": pref, "ym": ym},
                    place=pref,
                    today_str=today_str,
                    seen_urls=seen_urls,
                    label=f"{pref} {ym}",
                    api_key=api_key,
                )
            else:
                collected, ok = _fetch_rss_events(
                    params={"format": "rss", "pref_id": pref_id, "ym": ym},
                    place=pref,
                    today_str=today_str,
                    seen_urls=seen_urls,
                    label=f"{pref} {ym}",
                )
            attempts += 1
            if not ok:
                failures += 1
            events.extend(collected)
            if _api_limit_reached():
                print(
                    f"  connpass API: 収集件数が上限付近のため以降の検索を終了 "
                    f"({len(seen_urls)} 件)"
                )
                break
        if _api_limit_reached():
            break

    # --- オンラインイベント検索 ---
    if _api_limit_reached():
        print("  connpass API: オンライン検索をスキップします")
    else:
        for ym in months:
            if use_api:
                # v2 API には RSS の online=1 相当パラメータが無いため、
                # keyword="オンライン" を用いてオンライン系イベントを補完する。
                # 表現ゆれ（リモート/Web開催等）により取りこぼし/誤検出の可能性がある。
                collected, ok = _fetch_api_events(
                    params={"keyword": "オンライン", "ym": ym},
                    place="オンライン",
                    today_str=today_str,
                    seen_urls=seen_urls,
                    label=f"オンライン {ym}",
                    api_key=api_key,
                )
            else:
                collected, ok = _fetch_rss_events(
                    params={"format": "rss", "online": 1, "ym": ym},
                    place="オンライン",
                    today_str=today_str,
                    seen_urls=seen_urls,
                    label=f"オンライン {ym}",
                )
            attempts += 1
            if not ok:
                failures += 1
            events.extend(collected)
            if _api_limit_reached():
                print(
                    f"  connpass API: 収集件数が上限付近のためオンライン検索を終了 "
                    f"({len(seen_urls)} 件)"
                )
                break

    # 全リクエスト失敗時は例外（既存 events.json の上書き防止）
    if attempts > 0 and failures == attempts:
        raise RuntimeError(
            f"connpass {'API' if use_api else 'RSS'} 取得が全 {attempts} 件失敗しました。"
            "既存の docs/events.json を保持するため処理を中断します。"
        )

    # --- 大手ベンダー・大規模カンファレンス情報 ---
    print("  ベンダーイベント情報を取得中...")
    vendor_events = fetch_vendor_news_events(today)
    # connpass と URL の重複がなければ追加（seen_urls は connpass・ベンダーイベント共通で管理）
    added_vendor_count = 0
    for ev in vendor_events:
        if ev["event_url"] not in seen_urls:
            seen_urls.add(ev["event_url"])
            events.append(ev)
            added_vendor_count += 1
    print(f"  ベンダーイベント追加: {added_vendor_count} 件（取得 {len(vendor_events)} 件）")

    # 日時昇順ソート（日時不明は末尾）
    events.sort(
        key=lambda e: (0, e["started_at"]) if e.get("started_at") else (1, "")
    )

    if len(events) > MAX_CALENDAR_EVENTS:
        print(f"  ※ {len(events)} 件 → {MAX_CALENDAR_EVENTS} 件に制限")
        events = events[:MAX_CALENDAR_EVENTS]

    # connpass イベントページからイベント説明を取得（ベンダーイベントは対象外）
    _enrich_descriptions(events)

    return events


# ---------------------------------------------------------------------------
# メイン
# ---------------------------------------------------------------------------

def main() -> None:
    today = datetime.now(JST)
    print(f"イベントカレンダーデータ生成開始: {today.strftime('%Y-%m-%d %H:%M JST')}")

    try:
        events = fetch_events(today)
    except RuntimeError as e:
        # 全取得失敗時は events.json を上書きせず終了する。
        # ワークフロー自体は失敗にせず、前回データを保持する。
        print(f"警告: {e}", file=sys.stderr)
        print("イベント取得に失敗したため、events.json の更新をスキップします。", file=sys.stderr)
        return
    print(f"取得イベント数: {len(events)}")

    data = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "events": events,
    }

    docs_dir = Path(__file__).parent.parent / "docs"
    docs_dir.mkdir(exist_ok=True)
    out = docs_dir / "events.json"
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"保存完了: {out} ({len(events)} イベント)")


if __name__ == "__main__":
    main()
