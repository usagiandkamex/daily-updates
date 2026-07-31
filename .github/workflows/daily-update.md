---
name: デイリーアップデート
description: RSS フィードから収集したニュースを元に日次のデイリーアップデート記事を生成し PR を作成する
on:
  schedule:
    # 毎日 8:00 JST (= 23:00 UTC 前日)
    - cron: '0 23 * * *'
  workflow_dispatch:
    inputs:
      target_date:
        description: '対象日 (YYYYMMDD形式、未指定時は当日JST)'
        required: false
        type: string

engine: copilot

permissions:
  contents: read

# pip(PyPI) と収集対象の RSS フィードドメインのみ egress を許可する。
# リンク検証は行わないため、任意の記事ホストへのアクセスは不要。
network:
  allowed:
    - defaults
    - python
    - news.google.com
    - microsoft.com
    - itmedia.co.jp
    - gigazine.net
    - publickey1.jp
    - impress.co.jp
    - zenn.dev
    - classmethod.jp
    - nikkei.com
    - techcrunch.com
    - theverge.com
    - arstechnica.com
    - hnrss.org
    - technologyreview.com
    - wired.com
    - theregister.com
    - zdnet.com
    - dev.to
    - slashdot.org
    - nhk.or.jp
    - toyokeizai.net
    - bbci.co.uk
    - cnbc.com
    - dj.com
    - hatena.ne.jp
    - reddit.com
    - qiita.com

runtimes:
  python:
    version: "3.12"

tools:
  bash: [":*"]
  edit:

safe-outputs:
  create-pull-request:
    title-prefix: "[daily] "
    labels: [daily-update, auto-merge]
    draft: false

timeout-minutes: 20
---

# デイリーアップデート生成

あなたは IT・ビジネスニュースの専門ライターです。RSS フィードから収集したニュースを元に、
正確で分かりやすい日本語のデイリーアップデート記事を作成し、プルリクエストとして提出します。

## 手順

1. **対象日を決定する**
   - `${{ github.event.inputs.target_date }}` が指定されていればそれを使う。
   - 未指定の場合は JST の当日を使う: `TZ=Asia/Tokyo date +%Y%m%d`
   - 以降この値を `<DATE>`（YYYYMMDD形式）とする。

2. **依存関係をインストールする**
   ```bash
   pip install -r scripts/requirements.txt
   ```

3. **ニュースを収集する**（記事執筆はしない。収集のみ）
   ```bash
   python scripts/generate_daily_update.py <DATE> /tmp/gh-aw/agent/news_data.json
   ```
   `/tmp/gh-aw/agent/news_data.json` に、`categories` として `azure` / `tech` / `business` / `sns` の
   4 カテゴリの記事配列が出力される。各記事は `title` / `description` / `url` / `source` を持つ。

4. **記事を執筆する**
   - `/tmp/gh-aw/agent/news_data.json` を読み込み、その内容だけを根拠に記事を書く。**存在しない情報を捏造しない。**
   - 参考リンクは JSON 内の `url` をそのまま使う。JSON に無い URL を新たに作らない。
   - 下記フォーマットに従い、`updates/<DATE>.md` を新規作成する（`edit` ツールを使う）。

5. **プルリクエストを作成する**
   - 追加した `updates/<DATE>.md` を含む PR を `main` ブランチ宛に作成する。
   - タイトルは `<YYYY/MM/DD> デイリーアップデート`。

## 記事フォーマット

読了目安は約8分（4000〜5000文字程度）。以下の 4 セクションで構成する。
各セクションは **必ず 5〜6 個** のトピックを選定する（ソースが少ない場合のみ減らしてよいが 3 個は下回らない）。
各トピックは「見出し」「要約」「影響」「参考リンク」の 4 項目で構成し、各項目の間には必ず空行を入れる。

- **1. Azure アップデート情報** — `azure` カテゴリから Azure サービスの新機能・更新情報。
- **2. ニュースで話題のテーマ** — IT・テクノロジー関連のトピック。`tech` および `business` カテゴリの
  うち IT 関連（IT企業の決算・AI・半導体など）をここに集める。
- **3. SNSで話題のテーマ** — `sns` カテゴリのはてブ・Reddit 等のトレンド。
- **4. ビジネスホットトピック** — IT **以外** のトピックのみ（世界情勢・経済・金融・政治・社会・産業動向など）。

要約は簡潔かつ具体的に。影響はビジネスや開発者にとっての意味を記載する。

出力テンプレート（コードブロックで囲まず、マークダウンをそのまま `updates/<DATE>.md` に書く）:

```
# <YYYY/MM/DD> デイリーアップデート

## 1. Azure アップデート情報

### <見出し>

**要約**: ...

**影響**: ...

**参考リンク**: [タイトル](URL)

（5〜6個繰り返し）

## 2. ニュースで話題のテーマ

（5〜6個。見出し・要約・影響・参考リンク）

## 3. SNSで話題のテーマ

（5〜6個。見出し・要約・影響・参考リンク）

## 4. ビジネスホットトピック

（5〜6個。IT以外。見出し・要約・影響・参考リンク）
```
