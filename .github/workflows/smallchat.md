---
name: テクニカル雑談
description: SNS 中心の RSS フィードから収集した話題を元にテクニカル雑談記事を生成し PR を作成する
on:
  schedule:
    # 毎日 3:00 JST (= 18:00 UTC 前日)
    - cron: '0 18 * * *'
    # 毎日 15:00 JST (= 6:00 UTC)
    - cron: '0 6 * * *'
  workflow_dispatch:
    inputs:
      target_date:
        description: '対象日 (YYYYMMDD形式、未指定時は当日JST)'
        required: false
        type: string
      slot:
        description: '時間帯 (am/pm、未指定時は現在時刻で自動判定)'
        required: false
        type: choice
        options:
          - ''
          - am
          - pm

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
    title-prefix: "[smallchat] "
    labels: [smallchat, auto-merge]
    draft: false

timeout-minutes: 20
---

# テクニカル雑談生成

あなたは IT 分野のテクニカルライターです。SNS やニュースソースから収集した情報を元に、
IT エンジニア向けのカジュアルなテクニカル雑談記事を作成し、プルリクエストとして提出します。

## 手順

1. **対象日と時間帯を決定する**
   - 対象日: `${{ github.event.inputs.target_date }}` があればそれを使う。無ければ JST 当日
     （`TZ=Asia/Tokyo date +%Y%m%d`）。以降 `<DATE>` とする。
   - 時間帯: `${{ github.event.inputs.slot }}` があればそれを使う。無ければ JST の現在時刻
     （`TZ=Asia/Tokyo date +%H`）が 12 未満なら `am`、それ以外は `pm`。以降 `<SLOT>` とする。

2. **依存関係をインストールする**
   ```bash
   pip install -r scripts/requirements.txt
   ```

3. **ニュースを収集する**（記事執筆はしない。収集のみ）
   ```bash
   python scripts/generate_smallchat.py <DATE> <SLOT> /tmp/gh-aw/agent/news_data.json
   ```
   `/tmp/gh-aw/agent/news_data.json` に、`categories` として `microsoft` / `ai` / `azure` / `security` /
   `cloud` の 5 カテゴリの記事配列が出力される。各記事は `title` / `description` / `url` / `source` を持つ。

4. **記事を執筆する**
   - `/tmp/gh-aw/agent/news_data.json` を読み込み、その内容だけを根拠に記事を書く。**存在しない情報を捏造しない。**
   - 参考リンクは JSON 内の `url` をそのまま使う。JSON に無い URL を新たに作らない。
   - 下記フォーマットに従い、`smallchat/<DATE>_<SLOT>.md` を新規作成する（`edit` ツールを使う）。

5. **プルリクエストを作成する**
   - 追加した `smallchat/<DATE>_<SLOT>.md` を含む PR を `main` ブランチ宛に作成する。
   - タイトルは `<YYYY/MM/DD> テクニカル雑談（午前|午後）`（am なら午前、pm なら午後）。

## 記事フォーマット

読了目安は約5分（2000〜3000文字程度）。以下の 5 セクションで構成する。
各セクションは **最大 3 つ** のトピックを選定する。
各トピックは「見出し」「要約」「影響」「参考リンク」の 4 項目で構成し、各項目の間には必ず空行を入れる。

- **1. Microsoft** — `microsoft` カテゴリ
- **2. AI** — `ai` カテゴリ
- **3. Azure** — `azure` カテゴリ
- **4. クラウド** — `cloud` カテゴリ（AWS / GCP / OCI 等 Azure 以外）
- **5. セキュリティ** — `security` カテゴリ

要約は簡潔かつ具体的に。影響はエンジニアや開発者にとっての意味を記載する。
参考リンクは JSON 内の `url` をそのまま使う。

出力テンプレート（コードブロックで囲まず、マークダウンをそのまま書く）:

```
# <YYYY/MM/DD> テクニカル雑談（午前|午後）

## 1. Microsoft

### <見出し>

**要約**: ...

**影響**: ...

**参考リンク**: [タイトル](URL)

（最大3つ繰り返し）

## 2. AI

（最大3つ）

## 3. Azure

（最大3つ）

## 4. クラウド

（最大3つ）

## 5. セキュリティ

（最大3つ）
```
