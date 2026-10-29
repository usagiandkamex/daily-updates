---
name: デイリーアップデート
description: RSS フィードから収集したニュースを元に日次のデイリーアップデート記事を生成し PR を作成する
on:
  schedule:
    # 毎日 5:00 JST 前後に分散し、8:00までの完了を目指す
    - cron: daily around 5:00 utc+9
  workflow_dispatch:
    inputs:
      target_date:
        description: '対象日 (YYYYMMDD形式、未指定時は当日JST)'
        required: false
        type: string

engine: copilot

permissions:
  contents: read

# pip(PyPI) と収集対象の RSS フィードドメイン／ecosystem のみ egress を許可する。
# Google News RSS の取得と URL デコードには chrome ecosystem
# （*.google.com / *.googleapis.com / *.gvt1.com への egress）が必要。
# 個別ドメインの列挙ではデコードが不安定になり収集が失敗するため、
# 収集を安定して動作させることを目的に、あえて chrome ecosystem をまとめて許可している。
# リンク検証は行わないため、任意の記事ホストへのアクセスは不要。
network:
  allowed:
    - defaults
    - python
    - chrome
    - microsoft.com
    - azure.microsoft.com
    - devblogs.microsoft.com
    - blogs.windows.com
    - code.visualstudio.com
    - techcommunity.microsoft.com
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
    - feeds.arstechnica.com
    - hnrss.org
    - technologyreview.com
    - wired.com
    - theregister.com
    - zdnet.com
    - dev.to
    - slashdot.org
    - aws.amazon.com
    - cloudblog.withgoogle.com
    - github
    - blog.google
    - openai.com
    - huggingface.co
    - feed.infoq.com
    - nhk.or.jp
    - toyokeizai.net
    - bbci.co.uk
    - feeds.bbci.co.uk
    - cnbc.com
    - search.cnbc.com
    - dj.com
    - feeds.a.dj.com
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
    github-token: ${{ secrets.GITHUB_TOKEN }}

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
   `/tmp/gh-aw/agent/news_data.json` に、`categories` として `azure` / `microsoft` / `ai` / `tech` / `business` / `sns` の
   6 カテゴリの記事配列が出力される。各記事は `title` / `description` / `url` / `source` を持つ。

4. **コミュニティイベントデータを読む**
   - `docs/events.json` を読み込む。
   - `events` 配列には、東京・神奈川中心のコミュニティイベントと、大手ベンダー/大規模カンファレンス関連情報が含まれる。
   - `vendor_event: true` の `started_at` は「開催日時」ではなく「記事公開日時」として扱う。

5. **記事を執筆する**
   - `/tmp/gh-aw/agent/news_data.json` と `docs/events.json` を読み込み、その内容だけを根拠に記事を書く。**存在しない情報を捏造しない。**
   - リンクは JSON 内の `url` / `event_url` をそのまま使う。JSON に無い URL を新たに作らない。
   - `docs/events.json` の `catch` に含まれる HTML 断片はそのまま出力しない（必要なら無視する）。
   - 下記フォーマットに従い、`updates/<DATE>.md` を新規作成する（`edit` ツールを使う）。

6. **プルリクエストを作成する**
   - 追加した `updates/<DATE>.md` を含む PR を `main` ブランチ宛に作成する。
   - タイトルは `<YYYY/MM/DD> デイリーアップデート`。

## 記事フォーマット

読了目安は記事全体で約10分（5000〜6500文字程度）。以下の 7 セクションで構成する。
1・3〜6 セクションは **必ず 5〜6 個** のトピックを選定する（ソースが少ない場合のみ減らしてよいが 3 個は下回らない）。
2 セクションは 5〜6 個を目安とし、該当する技術アップデートが少ない場合は実際の件数のみ掲載する。該当情報がなければ「対象期間の技術アップデート情報なし」と明記し、件数合わせの捏造や古い情報の流用はしない。
1〜6 セクションの各トピックは「見出し」「要約」「影響」「リンク」の 4 項目で構成し、各項目の間には必ず空行を入れる。

- **1. Azure アップデート情報** — `azure` カテゴリから Azure サービスの新機能・更新情報（AVD は 2 に掲載）。
- **2. Microsoft アップデート情報** — `microsoft` カテゴリを中心に、Microsoft 製品全般の技術的なアップデートを紹介する。Microsoft Copilot・Windows・GitHub（GitHub Copilot・Actions など）・VS Code（Visual Studio Code）・AVD（Azure Virtual Desktop）などを対象とし、例示した製品に限定しない。新機能・仕様変更・更新情報を取り上げ、企業動向や一般的な活用記事は含めない。AVD 以外の Azure サービスは 1 に掲載する。
- **3. AI トピック** — `ai` カテゴリから、新しい AI モデル・エージェント・サービス・ソリューション・MCP 連携・Skill などのニュース。
- **4. ニュースで話題のテーマ** — IT・テクノロジー関連のトピック。`tech` および `business` カテゴリの
  うち IT 関連（IT企業の決算・AI以外の技術・半導体など）をここに集める。
- **5. SNSで話題のテーマ** — `sns` カテゴリのはてブ・Reddit 等のトレンド。
- **6. ビジネスホットトピック** — IT **以外** のトピックのみ（世界情勢・経済・金融・政治・社会・産業動向など）。
- **7. コミュニティイベント情報（東京・神奈川）および大手ベンダー・大規模カンファレンス** —
  `docs/events.json` の `events` から作成。**東京・神奈川などの地域ごとに小見出しを分けたり分類したりせず**、
  収集済みイベントの中から代表的なものを数件ピックアップして紹介する。`vendor_event` が付かないイベントは
  コミュニティイベントとして扱い、`vendor_event: true` は参加レポート/ベンダーカンファレンス関連として扱う。

AVD（Azure Virtual Desktop）の更新は、収集カテゴリが `azure` の場合も 2 に集約する。それ以外の Azure サービスの更新（Azure 向け Copilot を含む）は 1 に掲載する。`ai`・`tech` 等にも含まれる Microsoft 製品（AVD を含み、それ以外の Azure サービスを除く）の技術アップデートは 2 を優先し、同じ話題を他セクションに重複掲載しない。

要約は簡潔かつ具体的に。1〜6 セクションの影響はビジネスや開発者にとっての意味を記載する。

出力テンプレート（コードブロックで囲まず、マークダウンをそのまま `updates/<DATE>.md` に書く）:

```
# <YYYY/MM/DD> デイリーアップデート

## 1. Azure アップデート情報

### <見出し>

**要約**: ...

**影響**: ...

**リンク**: [タイトル](URL)

（5〜6個繰り返し）

## 2. Microsoft アップデート情報

（5〜6個が目安。Microsoft Copilot・Windows・GitHub・VS Code・AVD など、Microsoft 製品全般の技術アップデート。Azure サービスの分類は上記ルールに従う。見出し・要約・影響・リンク。少ない場合や該当情報がない場合は上記ルールに従う）

## 3. AI トピック

（5〜6個。新モデル・エージェント・サービス・ソリューション・MCP連携・Skill など。見出し・要約・影響・リンク）

## 4. ニュースで話題のテーマ

（5〜6個。見出し・要約・影響・リンク）

## 5. SNSで話題のテーマ

（5〜6個。見出し・要約・影響・リンク）

## 6. ビジネスホットトピック

（5〜6個。IT以外。見出し・要約・影響・リンク）

## 7. コミュニティイベント情報（東京・神奈川）および大手ベンダー・大規模カンファレンス

### 📅 申し込み受付中のイベント

（`vendor_event` が付かないイベントから、地域で分けず代表的なものを 4〜6 件ピックアップして記載。次の形式で記載）

**イベント名**

**開催日時**: started_at

**場所**: place

**概要**: description（description が無い場合は「概要データなし」）

**リンク**: [イベント名](event_url)

---

### 📝 参加レポート・イベント宣伝まとめ

（`vendor_event: true` のイベントから 3〜5 件。次の形式で記載）

### <見出し>

**要約**: title と place の情報に基づいて簡潔に記載（推測しない）

**記事公開日時**: started_at

**リンク**: [タイトル](event_url)

---
```
