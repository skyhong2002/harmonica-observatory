> 本文件保留接手時的歷史狀態。使用者最新要求的正式品牌是 Harmonica Observatory／口琴觀測站；最新 UI 驗收見 `ui-acceptance-2026-09-23.md`。

# 下一個 agent 完整接手 prompt

請直接接續實作，不只提出計畫。以下是使用者的需求與 2026-09-23 約 02:20（Asia/Taipei）的交接狀態。

## 使用者最重要的最新指示

> 介面上請接近竹梅觀測站越好，那個介面是我刻意設計過的。

目標是將 Harmonica-in-Taiwan 變成全球可用、至少繁中／英文／日文／韓文四語的口琴觀測站，介面與操作方式盡可能忠實沿用 `skyhong2002/chumei`。原本兩小時工作中的後端／部署／四語功能基礎已建成，但前一版做成奶油色、綠色、巨大 hero 的 錯誤命名的舊版風格，**這不符合最新視覺要求，不能當成完成品，也不要繼續美化這個方向**。接下來首要工作是對齊竹梅的實際 UI。使用者已要求提供本交接 prompt；本 prompt 不代表重新開始另一個固定兩小時時限。

## 工作位置及必讀檔案

- 目標 repo：`/Users/skyhong/Documents/Harmonica-in-Taiwan`，GitHub `skyhong2002/harmonica-observatory`，branch `main`。
- 參考 repo：`/Users/skyhong/Projects/chumei`，GitHub `skyhong2002/chumei`。只讀參考，不改動竹梅的服務、資料、憑證或帳號。
- 正式目標：`https://harmonica.observe.tw/`。
- 本機目標：`http://localhost:8330/`，服務實際綁定 `127.0.0.1:8330`。
- 竹梅實際參考：`https://chumei.observe.tw/`，不是其他猜測的域名。
- 先讀：`web/CHUMEI_UI_HANDOFF.md`（精確元件與程式位置、已檢視截圖、移植順序）、`deploy/acceptance-2026-09-23.md`、`deploy/local-hosting.md`、`deploy/apify-pool.md`、`README.md`、`.agents/AGENTS.md`。
- 先檢查 Git dirty state、最新 commit、正在運行的服務。`deploy/instagram-monitoring.md` 是前一輪開始前就存在的使用者未追蹤檔案；不要刪除、覆蓋或順手提交。

## UI 要忠實對齊哪些部分

先用真實瀏覽器開竹梅桌面、手機、明暗模式，再閱讀其原始碼，與目標網站用相同 viewport 對照。

1. 桌面固定左側導覽：≥1080px 約 260px；700–1079px 約 76px 圖示欄。手機 ≤699px 使用約 54px 頂欄、固定底部導覽與 safe area。保留竹梅的 More／外觀操作，加入不擾亂結構的語言切換。
2. 首頁直接進內容河道：上方限動列、下方可獨立垂直捲動的多欄 deck，橫向捲動、每欄篩選及新增／移除欄位。這不是一般三欄卡片格。手機是一條容易閱讀的綜合河道。
3. 貼文沿用竹梅 Threads 式資訊密度：頭像、作者、地區／分類、時間、平台、完整原文的展開、圖片、活動連結、追蹤／分享／原文操作。移除目前大 hero、地球插畫、統計行銷區及全站的大卡片風格。
4. 名錄、來源詳頁、活動、樂譜、訂閱、狀態、貢獻頁皆沿用相同元件語言；名錄應參考竹梅密集的 row/table 與排序，不能只換配色。
5. 竹梅的清大／交大條件改成國家／地區等全球 facet；介面語言與資料國家完全獨立，切語言不能偷偷切国家。預設可以看全球，不把未知國家當臺灣。
6. 使用真正的 light／dark／system 外觀；不是把所有頁面固定黑色。品牌名稱保留全球口琴定位，不直接冒用竹梅字樣或學校身份。
7. 專用日曆、限動 viewer 等若納入 UI，要完整做路由、空狀態、資料語義與測試，不能放無效按鈕。現在 `/calendar/` 沒有新 app 實作，OAuth／推播／跨裝置帳號也尚未做。

參考原始碼：`site/assets/tokens.css`、`site/assets/site.css`、`site/assets/app.js`、`site/index.html`、`scripts/build_site.py`。竹梅貢獻頁由 `scripts/auth_server.py` 動態渲染，不能只找 static HTML。詳盡行號見 UI handoff。可以抽取／改寫合適元件，但不要整包搬入竹梅 school ID、API、OAuth 或身份假設。

## 已完成而且要保留的功能

- `web/assets/i18n.js` 四語字典，URL／本機偏好／瀏覽器語言選擇；國家使用 Intl.DisplayNames；來源名稱、簡介、貼文保留原文，獨立原始來源按鈕。
- `web/assets/app.js` 路由、搜尋、IME、國家／平台／類別篩選、分頁、瀏覽器追蹤、history、來源標題及 canonical/hreflang/OG 更新。
- `web/assets/utils.js` 正確處理 date-only civil date、活動當地時區、全天事件排他結束日與 DST，不可退回用 UTC 導致美洲日期偏一天。
- `web/assets/community.js` 提供 Apify 貢獻、明確 consent、累計 USD 上限、驗證／錯誤／撤回、前後抓取週期估算與回報佇列。背景刷新已修正，不會清除正在輸入的表單或焦點。
- `scripts/global_catalog.py` 統一現有來源／貼文／活動／樂譜。快照約 322 sources、788 posts、12 events、797 scores、39 score collections；數字隨時間可能改變。28 個實際國家／地區，countries 選項另含 International／Online 等，不要混報。
- 過期限動保留 archive 標記；`catalog.stories` 只包含有效限動，目前可能是 0。不得把數百則歷史限動冒充正在播出的限動。
- `scripts/serve.py` 同源本機 HTTP server、gzip JSON、CSP、Host/Origin/CSRF、檔案白名單、真實 404、四語 SSR。只暴露 `web/assets` 與生成的 `site` 公開資料。
- `scripts/render_shell.py` 來源 permalink、SSR 可讀原文與本地化 SEO；`/directory/`→`/source/`、`/score-sources/`→`/scores/sources/` 308 並保留 query。
- 既有 RSS、JSON、ICS、來源 URL 仍可讀。不要只重做首頁而破壞收藏連結。

主要路由：`/`、`/post/`、`/events/`、`/source/`、`/source/:slug/`、`/post/source/:slug/`、`/scores/`、`/scores/sources/`、`/feeds/`、`/status/`、`/contribute/`、`/submit/`、`/about/`、`/privacy/`。

## API／Apify／AI 閘道邊界

- 公開讀取：`GET /api/v1/health`、`catalog`、`sources`、`posts`、`events`、`scores`、`community`。清單支援 q/country/limit/offset。
- `GET /api/v1/session` 回傳 csrfToken 與此瀏覽器的 records；寫入需要同源 Origin、cookie 和 X-CSRF-Token。
- `POST /api/v1/contributions`：`{token,name,budgetUsd,consent:true}`；撤回 `DELETE /api/v1/contributions/:id`；回應包含 crawlImpact before/after。
- `POST /api/v1/submissions`：`{url,note,countryCode}`；只進審核佇列，不是自動公開。`scripts/review_community_submissions.py` 支援 list/export/mark。
- `scripts/community.py` 使用獨立 SQLite + Fernet，private state 在 `state/community/`。不複製竹梅的 DB、session、OAuth、token 或密鑰。資料庫與 encryption.key 必須一起備份。
- 現在管理身份是原瀏覽器 HttpOnly cookie，不是跨裝置登入；清 cookie 會失去本機管理入口，可於 Apify 撤銷 token。UI 必須誠實說明。撤回停止新任務，不會取消已在跑的 actor。
- `scripts/apify_pool.py` 已完成同 provider identity 去重、owner+community 共池、原子預留、累計授權／月額／日分配／run cap，未知結果保留預留避免重試超支。主帳號預設月上限 US$4，不要擅自增加。
- Facebook／Instagram／Stories 用 Apify。YouTube／RSS／網站既有公開管道仍保留，不能假稱所有 provider 都已轉成 Apify。Instagram public fallback 預設關閉。
- 貢獻頁總容量應用 `crawlSchedule.pool`（包含站方），不是只讀社群貢獻數而誤顯示 0。檢查時真實值曾是 1 帳號、US$3.34；這是變動資料，不可寫死。頻率是估算，不可承諾即時。
- `scripts/llm_backend.py` 只走本機 AI 閘道（`HARMONICA_LLM_PROVIDER=gateway`，別名 `sky-fast`／`sky-quality`，見 [本機服務](local-hosting.md#ai-閘道推論)）；所有程序共用單一請求槽與每小時上限，沒有公開任意推論 API。失敗保留快取。Codex CLI 備援已於 2026-10-03 移除。
- 只有明確設定 HARMONICA_LLM_PROVIDER=openai 才使用其他 OpenAI 相容端點。不要複製登入憑證、在 logs/截圖/聊天顯示真實 token 或登入資料。

## 真實部署狀態，不要重建成另一台服務

- 本機 LaunchAgent `tw.observe.harmonica.web` 已安裝且運行，使用專案 `.venv/bin/python`，localhost8330。
- Caddy `/usr/local/etc/caddy/Caddyfile` 的 Harmonica block 已改為 `reverse_proxy 127.0.0.1:8330`；其他網站逐項確認未改。
- DNS 已查得 A `140.113.240.11`，無 AAAA；Mac 在 NAT 後面。本輪沒有修改 DNS。
- 舊 HTTPS 憑證過期已修復。新 Let's Encrypt 憑證到 2026-12-21，已用正常 hostname/system trust 驗證，不是略過 TLS。
- `tw.observe.harmonica.pipeline`、`tw.observe.harmonica.social-fast` 都已恢復載入，每1800秒；用 venv、AI 閘道，移除 publish-pages。此輪安装的 RunAtLoad=false 避免立即付費抓取，正常間隔仍運作。
- social-fast 原本有 September18 遺留 mkdir lock，導致一直 skip；已清除確認無程序的 stale lock，並移除 source+installed plist 外層 mkdir wrapper，沿用 run_pipeline 自帶 PID/stale-aware lock。不要把舊 wrapper 放回來。
- 靜態 UI 檔直接服務；Python 變更後用 `launchctl kickstart -k gui/$(id -u)/tw.observe.harmonica.web`。
- 不要重新發布 GitHub Pages，不要改其他站 Caddy。真實部署驗收必須訪問 https://harmonica.observe.tw，不能只有localhost200。

## 驗證、工作順序與交付

目前驗證基準：224 Python tests passed；26 Node/DOM tests passed；114 localhost HTTP checks、37 public HTTPS checks；396 sitemap URLs 零錯誤；全新 source copy 在 network-denied 環境完整建置成功。這些只證明功能基礎，不代表 UI 已達竹梅要求。

```bash
cd /Users/skyhong/Documents/Harmonica-in-Taiwan
.venv/bin/python -m unittest discover -s tests
npm --prefix web ci --ignore-scripts
npm --prefix web test
.venv/bin/python scripts/build_local.py
.venv/bin/python scripts/validate_public_outputs.py
.venv/bin/python scripts/check_source_coverage.py
.venv/bin/python scripts/validate_legacy_redirects.py
.venv/bin/python scripts/validate_sitemap_seo.py
```

`build_local.py` 是離線重建，無 Apify／Codex／外部 Calendar write／push；正常 `run_pipeline.py` 可能消耗額度，不要為驗收反覆跑。

先忠實移植 UI shell/tokens → 河道與多欄互動 → 密集名錄與詳頁 → 其餘全站頁面。可以分派互不衝突的 agent 做 shell、river、其餘視圖與獨立驗收；使用者已明確希望多 agent 並行。各 agent 分配檔案所有權，避免整份重寫互相覆蓋。

使用者已明確允許 Playwright 獨立瀏覽器。原 Computer Use Chrome/Safari 曾 cgWindowNotFound，但新發現的 `mcp__t3_code__preview_*` 協作瀏覽器能開正式網址；遠端 preview 不能開這台機器的 localhost。可用專案可用的工具／隔離 Playwright 完成驗收，不要再卡在同一個視窗問題。

至少比較桌面1440×900、平板、手機390×844，四種語言及明暗模式；檢查底部safearea、獨立欄捲動、觸控／trackpad、篩選、原文展開、來源連結、回上一頁、IME、追蹤、貢獻成功/錯誤/撤回及刷新不清草稿。測試 API mutation 用 mock 或隔離 state，勿為測試提交真 token／污染正式回報。保留可檢視的截圖。

做完相關驗證後 commit/push 聚焦檔案，保留無關 dirty檔；公開網站驗收完成再回報。最後清楚區分「已實際完成」「尚待完成」與限制，不能把 UI 換色或 test全綠當成忠實沿用竹梅設計。
