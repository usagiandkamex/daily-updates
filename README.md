# daily-updates

日々のニュースを自動で収集・要約し、マークダウンファイルとして蓄積するリポジトリです。
ニュース収集からの記事生成・PR 作成を **GitHub Agentic Workflows (gh aw)** で実装しています。

## 仕組み

RSS/Atom フィードからのニュース**収集**は Python スクリプトが担当し、**記事の執筆**は
エージェント（GitHub Copilot）が行います。生成した記事はエージェントがプルリクエストとして
提出し、`auto-merge` ラベル付き PR を companion ワークフローが自動マージします。

### デイリーアップデート（毎日 8:00 JST）

1. **ニュース収集** — `scripts/generate_daily_update.py` が 53 の RSS/Atom フィード
   （Azure・技術系・ビジネス系・SNS）から最新ニュースを取得し JSON 出力
2. **記事執筆** — エージェントが JSON を元に日本語記事を執筆し `updates/YYYYMMDD.md` を作成
3. **PR 作成 & 自動マージ** — `main` への PR を作成し、`auto-merge` ラベルで自動マージ

生成記事の構成: 1. Azure アップデート情報 / 2. ニュースで話題のテーマ / 3. SNSで話題のテーマ /
4. ビジネスホットトピック（各セクション 5〜6 トピック、読了目安 約8分）

### テクニカル雑談（毎日 3:00 / 15:00 JST）

1. **ニュース収集** — `scripts/generate_smallchat.py` が 50 の RSS フィード（SNS・テックブログ中心）
   から直近 12 時間のニュースを取得し JSON 出力
2. **記事執筆** — エージェントが `smallchat/YYYYMMDD_{am,pm}.md` を作成
3. **PR 作成 & 自動マージ**

生成記事の構成: 1. Microsoft / 2. AI / 3. Azure / 4. クラウド / 5. セキュリティ
（各セクション 最大 3 トピック、読了目安 約5分）

### イベントカレンダー（毎日 3:00 JST）

`scripts/generate_events_calendar.py` が connpass（関東・オンラインの IT イベント）と
大手ベンダーの大規模カンファレンス情報（Google News RSS）を収集し、`docs/events.json` を
更新します。`CONNPASS_API_KEY` が設定されていれば connpass v2 API を、未設定時は RSS を使用します。
AI 生成を伴わないため通常の GitHub Actions（`events-calendar.yml`）として実装しています。

### GitHub Pages（記事・カレンダー更新時に自動デプロイ）

`scripts/generate_pages_data.py` が `updates/` `smallchat/` の記事から `docs/data.json` と
`docs/articles/*.json` を生成し、`docs/` 一式を GitHub Pages へデプロイします。
デイリー/雑談/カレンダーの各ワークフロー完了後、または `docs/**` への push で起動します。

## ディレクトリ構成

| パス | 内容 |
|---|---|
| `.github/workflows/daily-update.md` | デイリーアップデートのエージェントワークフロー（gh aw ソース） |
| `.github/workflows/smallchat.md` | テクニカル雑談のエージェントワークフロー（gh aw ソース） |
| `.github/workflows/*.lock.yml` | `gh aw compile` が生成する GitHub Actions 実体（手編集しない） |
| `.github/workflows/auto-merge.yml` | `auto-merge` ラベル付き PR を自動マージする companion ワークフロー |
| `.github/workflows/events-calendar.yml` | connpass イベントを収集し `docs/events.json` を更新（決定論的） |
| `.github/workflows/pages.yml` | 静的サイトを生成し GitHub Pages へデプロイ（決定論的） |
| `scripts/generate_daily_update.py` | デイリー用のニュース収集スクリプト（JSON 出力） |
| `scripts/generate_smallchat.py` | 雑談用のニュース収集スクリプト（JSON 出力） |
| `scripts/generate_events_calendar.py` | connpass イベント収集スクリプト（`docs/events.json` 出力） |
| `scripts/generate_pages_data.py` | 記事から Pages 用データを生成（`docs/data.json` / `docs/articles/` 出力） |
| `docs/` | GitHub Pages 用の静的サイト（HTML/CSS/JS＋生成データ） |
| `updates/` | デイリーアップデート記事の蓄積先 |
| `smallchat/` | テクニカル雑談記事の蓄積先 |

## セットアップ

### 1. gh aw 拡張のインストール

```bash
gh auth login --scopes repo,workflow
gh extension install github/gh-aw
```

### 2. AI エンジン用シークレットの設定

エンジンは GitHub Copilot を使用します。Copilot にアクセスできる **fine-grained PAT**
（*Account permissions → Copilot Requests: Read*）を作成し、リポジトリシークレットに設定します。

```bash
gh secret set COPILOT_GITHUB_TOKEN
```

必要に応じて connpass v2 API キーを設定します（未設定でも RSS で動作しますが API 推奨）。

```bash
gh secret set CONNPASS_API_KEY
```

### 3. Actions 権限

リポジトリの **Settings → Actions → General → Workflow permissions** で以下を有効にします。

- **Read and write permissions**
- **Allow GitHub Actions to create and approve pull requests**

### 4. GitHub Pages

**Settings → Pages → Build and deployment → Source** を **GitHub Actions** に設定します。

### 5. コンパイル

ワークフロー（`.md`）を編集したら再コンパイルし、`.md` と `.lock.yml` を両方コミットします。

```bash
gh aw compile
```

## 手動実行 / デバッグ

```bash
# 手動実行（target_date / slot は省略可）
gh aw run daily-update
gh aw run daily-update --input target_date=20260731
gh aw run smallchat --input slot=am

# 状態確認・ログ・ファイアウォール監査
gh aw status
gh aw logs
gh aw audit <run-id>
```

## ニュース収集の egress について

エージェントは AWF ファイアウォール下で動作し、`network.allowed` に列挙した
フィードのドメインと PyPI のみへアクセスできます（記事執筆はエージェントが行うため、
任意の記事ホストへのアクセスは不要）。フィードを追加した場合は、対応するドメインを
各ワークフローの `network.allowed` に追加してください。