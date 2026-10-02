# ハーモニカ観測所 · Harmonica Observatory

[English](README.md) · [繁體中文](README.zh-Hant.md) · [日本語](README.ja.md) · [한국어](README.ko.md)

**世界各地のハーモニカイベント、演奏者、楽譜情報を、ひとつの場所から。**

ハーモニカの情報は、さまざまなSNS、ウェブサイト、言語に分散しています。ハーモニカ観測所は、公開イベント、投稿、演奏者、アンサンブル、クラブ、指導・学習情報、楽譜の情報源をまとめ、演奏者、講師、学生、愛好家が情報を見つけ、元の情報源で詳しく確認できるようにするサービスです。

**[ハーモニカ観測所を開く](https://harmonica.observe.tw/)** · [GitHub](https://github.com/skyhong2002/harmonica-observatory) · [イベントを探す](https://harmonica.observe.tw/events/) · [情報源を探す](https://harmonica.observe.tw/source/) · [楽譜を探す](https://harmonica.observe.tw/scores/)

画面の表示言語は **English、繁體中文、日本語、한국어** に対応しています。使い慣れた言語で、さまざまな国・地域のコンテンツを閲覧できます。表示言語と国の絞り込みは独立しています。

## 何が見つかりますか？

| やりたいこと | 入口 |
| --- | --- |
| 演奏会、大会、講座、オンラインイベントを探す | [イベント](https://harmonica.observe.tw/events/)で日程、会場、元の告知を確認できます。ホームには Google Calendar も表示されます。 |
| ハーモニカコミュニティの公開情報を追う | [投稿](https://harmonica.observe.tw/post/)で公開投稿を検索し、原文、画像、動画、元の情報源を確認できます。ホームには表示期間内のストーリーズのプレビューもあります。 |
| 演奏者、アンサンブル、クラブ、指導者を知る | [情報源ディレクトリ](https://harmonica.observe.tw/source/)で、キーワードや国・地域から登録情報を探せます。 |
| 大会の課題曲、出版社、楽譜集を探す | [楽譜](https://harmonica.observe.tw/scores/)と[出版情報](https://harmonica.observe.tw/scores/sources/)を年度、編成、部門などで検索し、告知や出版・問い合わせ先を確認できます。 |
| 今後の更新を購読する | [購読](https://harmonica.observe.tw/feeds/)から RSS や ICS を使って、リーダーやカレンダーに更新情報やイベントを追加できます。 |

## データについて

- **元の情報源を確認できます。** 投稿には原文と元のリンクを保持します。情報源の名称や紹介文には参考訳を提供し、登録時の名称や原文も確認できます。
- **確認できたデータに基づいて表示します。** イベントは元のタイムゾーンを保持します。[稼働状況](https://harmonica.observe.tw/status/)でデータ更新日時と各プラットフォームの状態を確認できます。収録範囲や更新頻度は情報源の利用状況に左右されます。
- **楽譜は索引が中心です。** 課題曲、公式資料、出版情報を収録しています。すべての項目に楽譜全体のダウンロードがあるわけではなく、無許可のファイルも提供しません。
- **ストーリーズには表示期限があります。** キャッシュは元の投稿日時から48時間表示され、カードに表示期限が示されます。Instagram 上の原投稿は、それより早く閲覧できなくなる場合があります。ページは毎分、およびタブに戻った際に更新されます。

## 情報の充実にご協力ください

未登録の演奏者、団体、イベント、楽譜情報をご存じですか？ 修正が必要な情報を見つけた場合も、[情報提供・修正報告](https://harmonica.observe.tw/submit/)から公開URLと説明をお送りください。各コンテンツにも報告リンクがあり、既知の情報が入力されます。提供された内容は、確認後に公開データへ反映されます。

SNS情報の継続的な収集を支援するには、[Apify 利用枠の提供](https://harmonica.observe.tw/contribute/)を利用できます。累計支出上限を設定でき、許可はいつでも撤回できます。画面には収集能力と更新頻度の見積もりが表示されますが、実際の更新は情報源や収集結果に依存します。

利用枠の提供や情報投稿は、Google アカウントに紐づけることで複数の端末から管理できます。ログイン時には、そのブラウザー内の未連携の記録がアカウントへ移行されます。ログインしなくても、元のブラウザーの安全な Cookie で管理できます。アカウント連携前に Cookie を削除した場合は、Apify 側で元のトークンを失効させてください。Google ログインで Google Calendar の権限は要求しません。

開発者はコード、画面翻訳、公開情報源データの改善にも参加できます。以下にローカル起動、データ構造、検証コマンドを記載しています。情報源を追加する前に[収録ルール](.agents/AGENTS.md)を読み、デプロイには[ローカルホスティングの手順](deploy/local-hosting.md)を参照してください。

## ローカルで起動する

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python scripts/build_local.py
.venv/bin/python scripts/serve.py --host 127.0.0.1 --port 8330
```

**http://localhost:8330/** を開きます。ビルド済みデータがある場合は、`serve.py` を直接起動できます。

`build_local.py` はローカルのCSVと既存の収集スナップショットからサイト用データを生成します。新規データの取得、有料 actor の実行、AI の呼び出し、Git への push は行いません。非公開の実行時スナップショットがない新しい clone では、まずCSVの情報源ディレクトリと楽譜索引を利用でき、その後パイプラインで投稿を収集します。

macOS の常駐サービスをインストールするには、次を実行します。

```bash
.venv/bin/python scripts/install_local_service.py --install \
  --public-origin https://harmonica.observe.tw
```

Caddy、DNS、HTTPS、バックアップ、定期実行、復旧の詳細は[ローカルホスティング](deploy/local-hosting.md)を参照してください。DNS は管理者が変更し、アプリケーションは変更しません。

## 構成

```text
web/                       4言語のUI、共通コンポーネント、画面、ロケール
scripts/global_catalog.py  既存データを共通のグローバル公開モデルに正規化
scripts/serve.py           ローカルHTTPルート、公開API、同一オリジン・CSRF検証
scripts/community.py       Apifyトークンの暗号化、予算、ブラウザー識別、報告
scripts/apify_pool.py      収集処理間の予算共有、アトミックな予約、アカウント切り替え
scripts/llm_backend.py     AIゲートウェイ／Codexによる構造化推論と呼び出し上限
data/sources/              Git管理対象の公開CSVと安定したpublic_id
site/                      生成したJSON、RSS、ICS、旧URLのページ、画像キャッシュ
state/                     非公開のSQLite、鍵、分類キャッシュ（Git管理対象外）
data/feeds/                ローカルの収集受信箱と投稿候補（Git管理対象外）
```

HTTP リクエストはスナップショットの読み取りのみを行います。表示言語を切り替えても Codex や Apify は呼び出されません。収集処理とウェブサービスは分離しており、外部サービスに一時的な障害があっても、既存のデータは閲覧できます。

ストーリーズの収集は Chumei の方式を参考に、活動中の情報源を優先し、間隔を調整したバッチで行います。各バッチはひとつの Apify アカウントの金額・取得件数の枠に基づいて計画し、予算制限とアトミックな予約を維持します。収集後は `scripts/publish_story_cache.py` が対象を絞った処理とオフラインでの RSS/JSON 公開を即座に行い、プロフィール、YouTube、Facebook、投稿処理全体の完了を待ちません。[Apify の収集・予算仕様](deploy/apify-pool.md)を参照してください。

### データとURL

- `data/sources/harmonica-source-watchlist-public.csv`：公開情報源の主リスト。
- `data/sources/harmonica-clubs-public.csv`：学生クラブ。
- `data/sources/harmonica-score-publications.csv`：大会の課題曲と公式資料。
- `data/sources/harmonica-score-sources.csv`：出版・楽譜購入に関する情報。
- `data/sources/harmonica-public-calendar-overrides.csv`：公開資料に基づくイベントの修正。
- `data/sources/source-url-aliases.csv`：既存の情報源URLの別名。
- `data/sources/source-name-translations.json`：確認済みの4言語の参考名称。登録時の名称と情報源を保持し、公式名称であるとは主張しません。
- `data/sources/source-description-translations.json`：情報源の紹介文とタグの4言語訳。`event-description-translations.json` はイベント概要の翻訳を保持します。元の記録と完全に一致する場合のみ訳文を使用します。詳細ページ、SSR、SEO は表示言語に従い、原文は展開して確認できます。`scripts/validate_description_translations.py` で新規データの翻訳漏れを確認できます。閲覧時に翻訳サービスは呼び出しません。
- `data/sources/score-source-media.json`：個別に確認した書籍の表紙、告知画像、元のページ。ローカルのプレビューを再生成するには `.venv/bin/python scripts/cache_score_source_images.py` を明示的に実行します。閲覧やオフラインビルドに伴う画像取得は行いません。

`public_id` は並べ替えやレコード追加で変更しません。`country` は主な所属国・地域、`region` はより詳細な地理情報です。所在地が不明な場合、国を既定値で補いません。情報源の追加時は `.agents/AGENTS.md` に従い、公式アバターと公開プロフィールを取得して出力を検証してください。

### 収集と Apify

Facebook の投稿、Instagram の投稿とストーリーズは、ハーモニカ観測所専用の Apify プールを共有します。YouTube、ウェブサイト、RSS/RSSHub は既存の公開経路を使い続け、UIの変更には影響されません。利用可能な予算、actor ごとの上限、プロセス間の予約によって支出を制御します。結果が未確認の処理は予約を保持し、再試行で予算上限を回避しません。

```bash
# actor を実行せず、利用枠の情報を更新
.venv/bin/python scripts/apify_pool.py --refresh

# 収集とビルドを実行（設定済みの Apify/Codex 利用枠を消費する場合があります）
.venv/bin/python scripts/run_pipeline.py
```

[Apify プール](deploy/apify-pool.md)と[Instagram 収集の詳細](deploy/instagram-public-ingestion.md)を参照してください。ローカルでのデプロイには `--publish-pages` は不要です。[旧 Pages の手順](deploy/github-pages.md)はフォールバック用の参考資料として残しています。

### AI ゲートウェイ推論

既定値は `HARMONICA_LLM_PROVIDER=gateway` です。管理者の処理（分類、カレンダー審査、ディレクトリタグ、フォーム投稿審査）は、ローカル AI ゲートウェイ（`http://127.0.0.1:8317/v1`）へ OpenAI 互換形式で、意味的なエイリアスだけを指定して送ります。分類は `sky-fast`、投稿審査は `sky-quality` です。具体的なモデルはゲートウェイが決め、応答が示す実際のモデルを要求したエイリアスと一緒に記録します。キーは `HARMONICA_LLM_API_KEY` または Keychain 項目 `harmonica-ai-gateway` / `harmonica` から読みます。

- 4言語のUIは固定ロケールファイルを使い、閲覧者の操作によるAI翻訳費用は発生しません。
- 全処理で同時実行1件と1時間あたりの上限（`HARMONICA_LLM_MAX_CALLS_PER_HOUR`、既定120）を共有し、上限に達した場合はキャッシュを保持します。
- `HARMONICA_LLM_PROVIDER=disabled` で新しい推論を完全に無効化できます。
- `HARMONICA_LLM_PROVIDER=codex` は予備手段です。管理者のローカル `codex login` CLI を読み取り専用・ツール無効・1時間12回で使います。

閲覧者にゲートウェイのキー、Codex の認証情報、任意の推論エンドポイントは提供しません。

## 公開API

| パス | 用途 |
| --- | --- |
| `/api/v1/health` | ローカルサービスのヘルスチェック |
| `/api/v1/catalog` | グローバルデータ全体のスナップショット |
| `/api/v1/sources` | 情報源ディレクトリ |
| `/api/v1/posts` | 原文の投稿 |
| `/api/v1/events` | 日付とタイムゾーンが明確なイベント |
| `/api/v1/scores` | 大会の課題曲 |
| `/api/v1/community` | コミュニティから許可された利用枠と収集頻度の見積もり |

一覧APIは `q`、`country`（例：`JP`、`KR`）、`limit`（1–200）、`offset` に対応しています。既存の `/api/sources.json`、`latest.json`、`scores.json` なども読み取れます。公開データには公開情報と許可された集計状況のみを含み、トークンは返しません。

RSS/ICS は引き続き `/feeds/` 配下で利用できます：`updates.xml`、`events.xml`、`posts-videos.xml`、`sources.xml`、`student-clubs.xml`、`opportunities.xml`、`public-calendar.ics`、`overseas-calendar.ics`、`online-calendar.ics`。

## 検証

```bash
.venv/bin/python -m unittest discover -s tests
npm --prefix web ci --ignore-scripts
npm --prefix web test
.venv/bin/python scripts/validate_public_outputs.py
.venv/bin/python scripts/check_source_coverage.py
.venv/bin/python scripts/validate_legacy_redirects.py
```

コミットするのはソースコード、ロケールファイル、公開情報源のCSV、デプロイ文書のみです。`site/api`、生成HTML、収集スナップショット、画像キャッシュ、トークン、SQLite データベース、鍵、ログは Git に含めません。

## 管理者向け文書

- [画面と操作の仕様](web/CHUMEI_UI_HANDOFF.md)：現在のレイアウト要件と過去の設計記録。
- [レイアウト検証](deploy/original-layout-acceptance-2026-09-23.md)、[ユーザビリティ評価](deploy/heuristic-evaluation-2026-09-23.md)、[多言語ディレクトリと情報密度](deploy/density-multilingual-acceptance-2026-09-23.md)：各変更の検証記録です。テスト件数は当時のバージョンについてのものです。

## ライセンスと謝辞

MIT License · Sky Hong。

公開データの閲覧と Apify 利用枠の提供機能は、[Chumei Observatory](https://github.com/skyhong2002/chumei) の MIT ライセンスの実装を参考にしています。ハーモニカ観測所は、データ、認証、サービスの認証情報を独立して管理しています。
