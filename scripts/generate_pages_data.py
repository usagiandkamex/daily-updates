"""
Generate docs/data.json from all updates/ and smallchat/ markdown files.

Run this script manually or via GitHub Actions to refresh the GitHub Pages data.
"""

import json
import re
from datetime import datetime, timezone
from pathlib import Path

REPO_URL = "https://github.com/usagiandkamex/daily-updates"

# Section headers → tag names
SECTION_TAG_MAP = {
    "azure": "Azure",
    "microsoft": "Microsoft",
    "ai": "AI",
    "セキュリティ": "セキュリティ",
    "security": "セキュリティ",
    "クラウド": "クラウド",
    "cloud": "クラウド",
    "ニュース": "ニュース",
    "sns": "SNS",
    "twitter": "SNS",
    "ビジネス": "ビジネス",
    "business": "ビジネス",
}

# Keyword → tag (checked against full content)
KEYWORD_TAG_MAP = {
    "Azure": "Azure",
    "AKS": "Azure",
    "ARO": "Azure",
    "Microsoft": "Microsoft",
    "Windows": "Microsoft",
    "OneDrive": "Microsoft",
    "Teams": "Microsoft",
    "AI": "AI",
    "LLM": "AI",
    "ChatGPT": "AI",
    "Claude": "AI",
    "Gemini": "AI",
    "GPT": "AI",
    "生成AI": "AI",
    "機械学習": "AI",
    "脆弱性": "セキュリティ",
    "CVE": "セキュリティ",
    "セキュリティ": "セキュリティ",
    "フィッシング": "セキュリティ",
    "AWS": "クラウド",
    "GCP": "クラウド",
    "Google Cloud": "クラウド",
    "Kubernetes": "クラウド",
    "SNS": "SNS",
    "はてな": "SNS",
    "Reddit": "SNS",
    "ビジネス": "ビジネス",
    "投資": "ビジネス",
    "経済": "ビジネス",
}

TYPE_LABELS = {
    "daily": "Daily",
    "smallchat_am": "SmallChat AM",
    "smallchat_pm": "SmallChat PM",
}


def extract_tags(content: str) -> list[str]:
    """Return sorted list of tags derived from section headers and content keywords."""
    tags: set[str] = set()

    # From section headers (## N. SectionName)
    for heading in re.findall(r"^## \d+\. (.+)$", content, re.MULTILINE):
        lower = heading.lower()
        for key, tag in SECTION_TAG_MAP.items():
            if key.lower() in lower:
                tags.add(tag)

    # From content keywords
    for keyword, tag in KEYWORD_TAG_MAP.items():
        if keyword in content:
            tags.add(tag)

    return sorted(tags)


def _extract_youyaku_blocks(content: str) -> list[str]:
    """Return all 要約 text blocks from content (whitespace-normalised)."""
    parts: list[str] = []
    # Pattern A: **要約**: text on the same line (daily update style)
    for m in re.finditer(
        r"\*\*要約\*\*[：:]\s*(.+?)(?=\n\n|\n\*\*|\Z)", content, re.DOTALL
    ):
        parts.append(re.sub(r"\s+", " ", m.group(1)).strip())
    # Pattern B: **要約** \n text on next line (smallchat style)
    for m in re.finditer(
        r"\*\*要約\*\*\s*\n+\s*(.+?)(?=\n\n|\n\*\*|\Z)", content, re.DOTALL
    ):
        parts.append(re.sub(r"\s+", " ", m.group(1)).strip())
    return parts


def extract_excerpt(content: str) -> str:
    """Return a short excerpt taken from the first topic summary (要約)."""
    blocks = _extract_youyaku_blocks(content)
    if blocks:
        text = blocks[0]
        return text[:120] + ("…" if len(text) > 120 else "")
    return ""


def _extract_connpass_event_fields(content: str) -> list[str]:
    """Return searchable text from connpass event entries (title, date, venue, overview)."""
    parts: list[str] = []
    # Event titles: **[Title](connpass-url)** — greedy .+ so titles containing ] are captured fully
    for m in re.findall(
        r"^\*\*\[(.+)\]\(https?://(?:[^./]+\.)?connpass\.com/[^)]+\)\*\*$",
        content,
        re.MULTILINE,
    ):
        parts.append(m.strip())
    # Event fields: **開催日時** / **場所** / **概要** — strip URLs before indexing
    for m in re.finditer(
        r"^\*\*(?:開催日時|場所|概要)\*\*[：:]\s*(.+)$", content, re.MULTILINE
    ):
        value = re.sub(r"https?://\S+", "", m.group(1))
        value = re.sub(r"\s+", " ", value).strip()
        if value:
            parts.append(value)
    return parts


def extract_body(content: str) -> str:
    """Return condensed text for full-text search: H3 headings, 要約 blocks, and connpass event fields."""
    parts: list[str] = []
    # All H3 topic titles
    for heading in re.findall(r"^### (.+)$", content, re.MULTILINE):
        parts.append(heading.strip())
    parts.extend(_extract_youyaku_blocks(content))
    parts.extend(_extract_connpass_event_fields(content))
    return " ".join(parts)


def _build_search_text(entry: dict) -> str:
    """Pre-compute a single lowercased search string for fast client-side lookup."""
    title = entry.get("title") or ""
    excerpt = entry.get("excerpt") or ""
    tags = " ".join(entry.get("tags") or [])
    body = entry.get("body") or ""
    return f"{title} {excerpt} {tags} {body}".lower()


def _date_parts(date_str: str) -> tuple[str, str, str]:
    return date_str[:4], date_str[4:6], date_str[6:8]


def parse_daily_update(filepath: Path) -> dict:
    content = filepath.read_text(encoding="utf-8")
    date_str = filepath.stem  # "20260408"
    y, mo, d = _date_parts(date_str)

    title_m = re.match(r"^# (.+)$", content, re.MULTILINE)
    title = title_m.group(1).strip() if title_m else f"{y}/{mo}/{d} デイリーアップデート"

    return {
        "slug": f"{date_str}_daily",
        "date": date_str,
        "date_formatted": f"{y}/{mo}/{d}",
        "type": "daily",
        "title": title,
        "github_url": f"{REPO_URL}/blob/main/updates/{filepath.name}",
        "tags": extract_tags(content),
        "excerpt": extract_excerpt(content),
        "body": extract_body(content),
        "content": content,
    }


def parse_smallchat(filepath: Path) -> dict:
    content = filepath.read_text(encoding="utf-8")
    stem = filepath.stem  # "20260408_am"
    parts = stem.split("_")
    date_str = parts[0]
    slot = parts[1] if len(parts) > 1 else "am"
    y, mo, d = _date_parts(date_str)

    title_m = re.match(r"^# (.+)$", content, re.MULTILINE)
    slot_ja = "午前" if slot == "am" else "午後"
    title = title_m.group(1).strip() if title_m else f"{y}/{mo}/{d} テクニカル雑談（{slot_ja}）"

    return {
        "slug": f"{date_str}_smallchat_{slot}",
        "date": date_str,
        "date_formatted": f"{y}/{mo}/{d}",
        "type": f"smallchat_{slot}",
        "title": title,
        "github_url": f"{REPO_URL}/blob/main/smallchat/{filepath.name}",
        "tags": extract_tags(content),
        "excerpt": extract_excerpt(content),
        "body": extract_body(content),
        "content": content,
    }


def main() -> None:
    repo_root = Path(__file__).parent.parent
    docs_dir = repo_root / "docs"
    docs_dir.mkdir(exist_ok=True)

    articles_dir = docs_dir / "articles"
    articles_dir.mkdir(exist_ok=True)

    updates: list[dict] = []

    updates_dir = repo_root / "updates"
    if updates_dir.exists():
        for fp in sorted(updates_dir.glob("*.md")):
            try:
                updates.append(parse_daily_update(fp))
            except Exception as exc:
                print(f"[WARN] skip {fp.name}: {exc}")

    smallchat_dir = repo_root / "smallchat"
    if smallchat_dir.exists():
        for fp in sorted(smallchat_dir.glob("*.md")):
            try:
                updates.append(parse_smallchat(fp))
            except Exception as exc:
                print(f"[WARN] skip {fp.name}: {exc}")

    # Sort: newest date first; within same date: daily → pm → am
    # Higher value = earlier in descending sort
    type_priority = {"daily": 2, "smallchat_pm": 1, "smallchat_am": 0}
    updates.sort(
        key=lambda x: (x["date"], type_priority.get(x["type"], -1)),
        reverse=True,
    )

    # Write individual article JSON files (includes full content)
    for entry in updates:
        slug = entry["slug"]
        article_out = articles_dir / f"{slug}.json"
        article_out.write_text(
            json.dumps(entry, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    # Strip large fields from entries before writing the index data.json.
    # 'content' and 'body' are kept only in per-article JSON.
    # Instead, add a pre-lowercased 'search_text' for fast client-side search.
    _article_only = {"content", "body"}
    index_updates = []
    for u in updates:
        idx = {k: v for k, v in u.items() if k not in _article_only}
        idx["search_text"] = _build_search_text(u)
        index_updates.append(idx)

    data = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "updates": index_updates,
    }

    out = docs_dir / "data.json"
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Generated {out} with {len(updates)} entries.")
    print(f"Generated {len(updates)} article files in {articles_dir}.")


if __name__ == "__main__":
    main()
