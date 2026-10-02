# 口琴觀測站 · Harmonica Observatory

[English](README.md) · [繁體中文](README.zh-Hant.md) · [日本語](README.ja.md) · [한국어](README.ko.md)

**從一個地方，探索世界各地的口琴活動、演奏者與樂譜資源。**

口琴資訊散落在不同社群平台、網站與語言之間。口琴觀測站整理公開活動、貼文、演奏者、樂團、社團、教學與樂譜來源，讓演奏者、教師、學生與愛好者更容易找到資訊，並回到原始來源深入了解。

**[開啟口琴觀測站](https://harmonica.observe.tw/)** · [GitHub](https://github.com/skyhong2002/harmonica-observatory) · [瀏覽活動](https://harmonica.observe.tw/events/) · [探索來源](https://harmonica.observe.tw/source/) · [尋找樂譜](https://harmonica.observe.tw/scores/)

介面提供 **繁體中文、English、日本語、한국어**。你可以用習慣的介面語言，搜尋不同國家與地區的內容；語言選擇與國家篩選彼此獨立。

## 可以找到什麼？

| 想做的事 | 從這裡開始 |
| --- | --- |
| 找演出、比賽、課程與線上活動 | [活動](https://harmonica.observe.tw/events/)：查看日期、地點與原始公告；首頁也提供 Google Calendar 行事曆。 |
| 追蹤口琴圈的公開動態 | [貼文](https://harmonica.observe.tw/post/)：搜尋公開貼文，查看原文、圖片、影片與來源連結；首頁另有有效限時動態預覽。 |
| 認識演奏者、樂團、社團與教學單位 | [來源名錄](https://harmonica.observe.tw/source/)：依關鍵字、國家與地區探索收錄來源。 |
| 找比賽指定曲、出版者與譜集 | [樂譜](https://harmonica.observe.tw/scores/)與[出版來源](https://harmonica.observe.tw/scores/sources/)：依學年度、編制、組別等條件查找，連回公告或出版／洽詢入口。 |
| 訂閱後續更新 | [訂閱](https://harmonica.observe.tw/feeds/)：使用 RSS 或 ICS，將動態與活動加入自己的閱讀器或行事曆。 |

## 資料與使用方式

- **保留原始來源。** 貼文保留原文與原始連結；來源名稱及簡介提供參考譯文，並保留收錄原名與原文供對照。
- **依實際資料呈現。** 活動保留原始時區；可在[狀態頁](https://harmonica.observe.tw/status/)查看資料更新時間與平台狀態。收錄範圍與更新速度依來源可用性而異。
- **樂譜以索引為主。** 收錄指定曲資訊、官方佐證與出版線索，不代表每筆都有完整樂譜可下載，也不提供未授權檔案。
- **限動有展示期限。** 快取依原始發布時間展示 48 小時，卡片標示「展示至」；Instagram 原文可能較早到期。頁面每分鐘及返回分頁時自動更新。

## 一起補充口琴資源

知道尚未收錄的演奏者、團體、活動或樂譜來源，或發現資料需要修正？歡迎透過[投稿與回報](https://harmonica.observe.tw/submit/)提供公開網址及說明。各內容頁也有回報入口，可帶入已知資料；投稿經審核後才會更新公開內容。

想協助持續更新社群資訊，可透過 [Apify 額度貢獻](https://harmonica.observe.tw/contribute/)設定累計金額上限，並隨時撤回授權。頁面會顯示容量與更新頻率估算，實際更新仍取決於來源與抓取結果。

貢獻與投稿可透過 Google 登入綁定帳號並跨裝置管理；登入時會移轉此瀏覽器尚未綁定的紀錄。未登入仍可使用原瀏覽器的安全 cookie 管理；未綁定前清除 cookie 後，需在 Apify 撤銷原 token。Google 登入不要求 Google Calendar 權限。

開發者也可以協助改善程式、介面翻譯或公開來源資料。以下提供本機啟動方式、資料結構與驗證指令；新增來源請先閱讀[來源收錄規範](.agents/AGENTS.md)，部署以[本機部署文件](deploy/local-hosting.md)為準。

## 本機啟動

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python scripts/build_local.py
.venv/bin/python scripts/serve.py --host 127.0.0.1 --port 8330
```

開啟 **http://localhost:8330/**。已有建置資料的機器可直接啟動 `serve.py`。

`build_local.py` 不抓新資料、不啟動付費 actor、不呼叫 AI，也不 push；它由本機 CSV 與既有抓取快照建立網站資料。全新 clone 沒有私人 runtime 快照時，先提供 CSV 來源目錄與樂譜索引，後續由 pipeline 蒐集貼文。

macOS 常駐服務：

```bash
.venv/bin/python scripts/install_local_service.py --install \
  --public-origin https://harmonica.observe.tw
```

完整的 Caddy、DNS、HTTPS、備份、排程與復原方式見 [本機部署](deploy/local-hosting.md)。DNS 由維護者切換；應用程式不修改 DNS。

## 架構

```text
web/                       四語介面、共用元件、各頁視圖與語系
scripts/global_catalog.py  將現有資料轉成一致的全球公開模型
scripts/serve.py           本機 HTTP 路由、公開 API、同源與 CSRF 控制
scripts/community.py       加密 Apify token、貢獻預算、瀏覽器身份與回報
scripts/apify_pool.py      跨抓取程序的額度、原子預留與帳號輪替
scripts/llm_backend.py     AI 閘道結構化推論與呼叫上限
data/sources/              可追蹤的公開 CSV，穩定 public_id 為來源識別
site/                      產生的 JSON、RSS、ICS、舊網址頁面及快取圖片
state/                     私有 SQLite、密鑰、額度與分類快取（不進 Git）
data/feeds/                本機抓取 inbox 與候選貼文（不進 Git）
```

HTTP 請求只讀快照；不會因訪客切換語言啟動 AI 閘道或 Apify。抓取程序與 web 服務分離，第三方暫時失敗時，仍可瀏覽已有資料。

限動抓取參考竹梅的活躍來源優先與分批配速；每批以同一 Apify 帳號的金額／結果容量規劃，維持既有預算與原子預留。抓取後立即執行 `scripts/publish_story_cache.py`，經定向整理與離線 RSS／JSON 發布，不等待個人頁、YouTube、Facebook 或整輪貼文整理。詳見 [Apify 抓取與額度契約](deploy/apify-pool.md)。

### 資料與網址

- `data/sources/harmonica-source-watchlist-public.csv`：公開來源主清單。
- `data/sources/harmonica-clubs-public.csv`：學生社團。
- `data/sources/harmonica-score-publications.csv`：指定曲與官方佐證。
- `data/sources/harmonica-score-sources.csv`：出版／購譜線索。
- `data/sources/harmonica-public-calendar-overrides.csv`：有公開佐證的活動校正。
- `data/sources/source-url-aliases.csv`：既有來源 URL 別名。
- `data/sources/source-name-translations.json`：經審閱的四語參考譯名，保留收錄原名及來源；不是官方名稱聲明。
- `data/sources/source-description-translations.json`：全部來源簡介及標籤的四語譯文；`event-description-translations.json` 保存活動整理說明譯文。譯文須與原始紀錄完全匹配才使用；詳頁、SSR與SEO跟隨介面語言，原文可展開查看。以 `scripts/validate_description_translations.py` 檢查新資料是否缺譯文，不因訪客瀏覽呼叫翻譯服務。
- `data/sources/score-source-media.json`：逐筆核對的書籍封面、公告圖片及原始頁面。明確執行 `.venv/bin/python scripts/cache_score_source_images.py` 可重建本機預覽；不隨訪客請求或離線建置抓圖。

`public_id` 不因排序或新插入資料而重編。`country` 是主所屬國家／地區，`region` 為較細地理資訊；未知地區不預設國家。新增來源應依 `.agents/AGENTS.md` 取得官方頭像、公開自介並驗證輸出。

### 抓取與 Apify

Facebook、Instagram 貼文與限時動態共用 Harmonica 自己的 Apify 池。YouTube、網站、RSS／RSSHub 仍使用原本的公開管道，不會因介面重構而停用。預算可用量、actor 每次上限與跨程序預留共同約束支出；未確認的結果保留預留，不能藉重試超支。

```bash
# 唯讀更新額度，不會啟動 actor
.venv/bin/python scripts/apify_pool.py --refresh

# 正式抓取／建置（可能消耗設定的 Apify／AI 閘道額度）
.venv/bin/python scripts/run_pipeline.py
```

見 [Apify 額度池](deploy/apify-pool.md) 與 [Instagram 抓取細節](deploy/instagram-public-ingestion.md)。新本機部署不需 `--publish-pages`；[舊 Pages 流程](deploy/github-pages.md) 保留作回退參考。

### AI 閘道推論

預設採 `HARMONICA_LLM_PROVIDER=gateway`：維護者流程（分類、日曆審核、目錄標籤、表單投稿審核）以 OpenAI 相容格式呼叫本機 AI 閘道（`http://127.0.0.1:8317/v1`），只使用語意別名——分類用 `sky-fast`、投稿審核用 `sky-quality`。實際模型由閘道決定，回應中的實際模型會與請求別名一併記錄。金鑰取自 `HARMONICA_LLM_API_KEY` 或 Keychain 項目 `harmonica-ai-gateway`／`harmonica`。

- 四語 UI 是固定語系檔，沒有訪客端 AI 翻譯費用。
- 所有流程共用單一進行中請求與每小時上限（`HARMONICA_LLM_MAX_CALLS_PER_HOUR`，預設 120）；用盡時保留快取。
- `HARMONICA_LLM_PROVIDER=disabled` 可完全停用新推論。

不會向訪客提供閘道金鑰或任意推論入口。

## 公開 API

| 路徑 | 用途 |
| --- | --- |
| `/api/v1/health` | 本機服務健康 |
| `/api/v1/catalog` | 完整全球資料快照 |
| `/api/v1/sources` | 來源目錄 |
| `/api/v1/posts` | 原文貼文 |
| `/api/v1/events` | 日期與時區明確的活動 |
| `/api/v1/scores` | 指定曲 |
| `/api/v1/community` | 社群授權容量與抓取頻率估算 |

清單 API 支援 `q`、`country`（如 `JP`、`KR`）、`limit`（1–200）、`offset`。既有 `/api/sources.json`、`latest.json`、`scores.json` 等依然可讀。所有公開資料只含公開資訊及允許的彙整狀態，不輸出 token。

RSS／ICS 維持 `/feeds/updates.xml`、`events.xml`、`posts-videos.xml`、`sources.xml`、`student-clubs.xml`、`opportunities.xml`、`public-calendar.ics`、`overseas-calendar.ics`、`online-calendar.ics`。

## 驗證

```bash
.venv/bin/python -m unittest discover -s tests
npm --prefix web ci --ignore-scripts
npm --prefix web test
.venv/bin/python scripts/validate_public_outputs.py
.venv/bin/python scripts/check_source_coverage.py
.venv/bin/python scripts/validate_legacy_redirects.py
```

只 commit 原始碼、語系、公開來源 CSV 與部署說明；`site/api`、生成 HTML、抓取快照、圖片快取、token、SQLite、密鑰與 logs 不進 Git。

## 維護文件

- [介面與互動規範](web/CHUMEI_UI_HANDOFF.md)：目前版面要求與歷史設計紀錄。
- [版面驗收](deploy/original-layout-acceptance-2026-09-23.md)、[使用體驗評估](deploy/heuristic-evaluation-2026-09-23.md)、[多語名錄與資訊密度](deploy/density-multilingual-acceptance-2026-09-23.md)：各次變更的驗收紀錄，測試數字僅代表當時版本。

## 授權與致謝

MIT License · Sky Hong。

公開資料瀏覽與 Apify 額度貢獻機制參考 [竹梅活動觀測站（Chumei）](https://github.com/skyhong2002/chumei) 的 MIT 授權實作。口琴觀測站獨立管理資料、登入與服務憑證。
