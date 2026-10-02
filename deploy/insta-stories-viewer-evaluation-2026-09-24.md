# InstaStoriesViewer 備援實測與實作（2026-09-24）

**結論：可作「欄位完整才收錄」的有限備援，不能取代 Apify 或保證 179 個來源的覆蓋率。**
5 個既有帳號在正常瀏覽器各測一次：2 個有資料、2 個成功空回應、1 個服務失敗。
有資料的兩個帳號中，只有天狼星回傳數字 story ID 與發布時間。
另以獨立 CLI 覆驗天狼星，ID／發布時間與約 6 分鐘前的瀏覽器一致；實際下載、
暫存媒體轉檔及重複匯入也成功。NYCU 能看圖，但該次後端缺少必要欄位，拒絕匯入。

已完成獨立 adapter、預設關閉的設定、診斷／手動收集 CLI 與測試。
**沒有啟用正式排程、部署、寫入正式限動快取、增加 Apify 支出或修改竹梅專案。**

## 查閱與環境

查閱日為 2026-09-24（Asia/Taipei）；下表及 JSON 的時間使用 UTC。
已讀 `.agents/AGENTS.md`、`deploy/apify-pool.md`、`deploy/local-hosting.md`、
`deploy/instagram-monitoring.md`，並檢查 collector、publisher、watchdog、
`story_lifecycle.py`、catalog 與前端更新測試。
`instagram-monitoring.md` 的 Instaloader 描述是舊流程；當前程式及 179 個限動來源
設定使用 Apify。工作開始時已有 24 個追蹤檔修改、7 個未追蹤檔，本次未更動它們。

CUA／原生 Chrome 初始連線失敗，後改用內建協作瀏覽器 `tab_8` 成功導覽。
以頁面自身 Socket.IO 完成事件、DOM 顯示狀態及圖片自然尺寸驗證完成，
沒有把 HTTP 200、初始 0 或隱藏占位文字當成結果。
整頁 screenshot 工具失敗，沒有整頁截圖證據；下載的兩張圖片均實際開啟檢查。
原始 HTML、JS、opaque 媒體值及下載檔只放在權限 0700 的 `/tmp/harmonica-isv-research/`。
Git 內只有去敏 fixture、程式、測試及摘要。未讀取或重用維護者 Instagram Cookie。

## 條款、robots 與 API

| 網址（本次查閱） | 證據及解讀 |
| --- | --- |
| <https://insta-stories-viewer.com/robots.txt> | HTTP 200，196 bytes；`User-agent: *`、`Allow: /`、`Crawl-delay: 175`。不是禁止自動化。本次以至少 175 秒作自主文件查閱／帳號查詢間距；單次頁面載入及連線協定的必要封包仍依正常網站流程進行 |
| <https://insta-stories-viewer.com/> | HTTP 200，導向 `/en/`。提供公開帳號查詢／下載，未要求使用者 IG 登入 |
| <https://insta-stories-viewer.com/terms-of-use/> | HTTP 200；讀取完成於 2026-09-23T18:10:35Z，頁面更新日 2021-11-26。未找到明列禁止 bot/scraping 的條款；不保證可用性、正確性或資訊新鮮度 |
| <https://insta-stories-viewer.com/privacy-policy/> | 首頁有此連結，本輪未讀全文，不宣稱完成隱私政策審核 |

首頁 FAQ 表示媒體權利屬原作者、下載供檢視，並不鼓勵其他用途或修改。
這不是給本站重新發布媒體的授權，robots Allow 也不是著作權授權；此處記錄頁面內容，
不作法律結論。首頁／條款及域名限定 API/developer/integration 搜尋未找到開發者 API
文件，不能因此宣稱技術上無法使用。

觀察到的是**網站內部端點，不是正式公開開發者 API**：

1. 正常導覽 `/<username>/`，取得 profile、更新狀態及限動載入占位。
   原始 HTML 同時含隱藏的 empty/private/not-found/service-error，須等完成事件。
2. 頁面讀同站 `/connect/`，在記憶體取得短期連線資料，再連 `/socket.io/`。
   前端依更新狀態發出 `search`／`fakeSearch`，限動類別為 `serverType: stories`。
3. `searchResult.data` 的 `status/code/serverType/user.reels` 決定結果；
   `success + stories + reels: []` 才是完成且空，posts/user-info 不代表限動完成。
   前端把資料層 404 分為不存在、403 分為私人、408/430 分為服務失敗；本次遇到的
   436 也按服務失敗處理，不能推論帳號不存在。HTTP 層 401/403/429 一律停止。
4. 不同 `serverCode` 品質不同：NYCU 後端 0 回傳 `UOq1Cwa` 與 opaque 媒體值，
   沒有發布／到期時間；天狼星後端 12 及覆驗後端 14 均回傳數字 ID、Unix 秒
   `taken_at`，但沒有原始到期時間。adapter 不指定或繞過任何後端路由。
5. 媒體 opaque 值原樣 URL-encode 後交給
   `https://cdn.insta-stories-viewer.com/img.php?url=…`，不解密或推造網址。
   圖片採 lazy loading，資料完成和圖片完成是兩個時間點。影片在本站仍使用預覽圖
   加原始 Instagram story 連結，不下載或嵌入整段影片。

公開 JS：<https://insta-stories-viewer.com/static/js/app.js?e56790d9fdb345955a7d>，
2026-09-23T18:13:30Z HTTP 200，562338 bytes，SHA-256
`f1a14dd1f75d3ce5080361d546dbfd9ba2425689cb62357ace37554b6f19fb3c`。
內部端點／schema／分流沒有版本或 SLA 承諾，變動可能使 adapter 失效。
本輪未出現 CAPTCHA 要求；不因 bundle 含表單驗證程式就宣稱帳號查詢必須 CAPTCHA。

## 小量實測表

帳號均來自啟用的既有公開來源。主測為 2026-09-23 18:19:35–18:31:29 UTC，
CLI 覆驗至 18:34:20 UTC（臺灣 09-24 02:19–02:34）。帳號間隔至少 175 秒、
循序、無手動重試、無 CAPTCHA 或 429。每次完成事件最多等待 45 秒；
臺大藍聲錯誤另持續觀察超過兩分鐘，沒有後續成功事件。

| 帳號 | 完成事件 UTC | 耗時 | 狀態／限動數 | 媒體 | 發布時間／原始到期 |
| --- | --- | ---: | --- | --- | --- |
| nycu_harmonica | 18:19:39.582 | 3.817 秒 | 成功，1 則；無合格 ID／時間，拒收 | 圖片 1440×2560；下載 HTTP 200、339780 bytes、2.267 秒 | 均未提供 |
| aidensoon | 18:22:35.166 | 3.404 秒 | 成功空集合，0 則 | 不適用，未下載 | 不適用 |
| taiwanharmonica | 18:25:34.292 | 5.574 秒 | 成功空集合，0 則 | 不適用，未下載 | 不適用 |
| siriusharmonicaensemble | 18:28:37.328 | 11.546 秒 | 成功，1 則，欄位合格 | 影片預覽 640×1136；暫存下載＋轉檔＋匯入 1.392 秒 | `2026-09-23T18:14:39Z`／未提供 |
| ntubluesound | 18:31:23.844 | 1.070 秒 | 服務 `error 436`；數量未知 | 無結果可下載 | 未提供 |
| 天狼星 CLI 覆驗 | 18:34:20.622 | 2.766 秒 | 成功，1 則，同 ID、同發布時間 | 此次只診斷；另有暫存媒體測試 | 同上／未提供 |

「成功空集合」是服務當時的明確回報，未另以 Instagram 帳號驗證完整性，
不能宣稱獨立證實 Instagram 絕對沒有任何限動。未實測不存在的帳號；不存在、
私人、載入中、逾時／失敗及 429 等邊界由 fixture/mock 覆蓋。
另有一次 18:16:25 UTC 的 NYCU 純 HTML 探查，只證明仍在載入，不計為完成查詢。
詳細去敏事件與資源狀態見 [實測 JSON](insta-stories-viewer-results-2026-09-24.json)。

## 與本站快取比對

本機基準讀取於 2026-09-23T18:07:51Z：

| 帳號／原始 story ID | 發布 UTC | 原始到期 UTC | 本站 48 小時截止 UTC |
| --- | --- | --- | --- |
| NYCU `3991885410459699733` | 09-22 15:10:45 | 09-23 15:10:45 | 09-24 15:10:45 |
| NYCU `3991969217629112625` | 09-22 17:57:12 | 09-23 17:57:12 | 09-24 17:57:12 |
| Aiden `3991837276653161364` | 09-22 13:35:06 | 09-23 13:35:06 | 09-24 13:35:06 |
| 其餘三個帳號 | 本機無限動快取 | — | — |

三筆舊限動已過原始期限，仍在本站展示期內；此次未修改或刪除。
NYCU 新圖為演出合照，兩張本機舊圖是社課照片／影片預覽，實際開圖比對明顯不同。
新圖 SHA-256 是 `a5f20beed454011dbfe3c59cf1360ee936f868a2402bd50bf38c681f1b6a88fe`，
兩次受限下載（2.267／2.363 秒）一致，但無原始時間，仍拒收。
不能從服務 ID、檔名、照片內容或抓取時間猜發布時間。

天狼星的 `3992702751863962825` 在瀏覽器／CLI 約 6 分鐘間 ID、發布時間一致；
本機基準無此 ID，因此是新候選。暫存匯入生成既有格式 key
`ig_story_siriusharmonicaensemble:3992702751863962825`，展示截止
`2026-09-25T18:14:39Z`，`story_expires_at=null`，不猜原始到期。
WebP 是 95922 bytes，SHA-256
`ac5e1986cbb73b65c35423b1a02204d2f096b14aec5be1e79364c214a4fd287a`。
首次暫存匯入 1 筆，第二次 0 筆／duplicate 1；正式 cache 未寫入。
Hash 不同本身不足以判別不同圖片，本次另有人工內容比對；沒有完整圖片相似度系統。

## 實作邊界

- `scripts/insta_stories_viewer.py`：獨立 adapter、離線／live 診斷，明確 `--collect`
  才寫快取。`HARMONICA_ISV_ENABLED` 預設關閉，不讀 `.env` 自動啟用。
- `scripts/insta_stories_viewer_transport.mjs`：Node 22+ fetch/WebSocket，單次正常連線；
  無外加套件、IG Cookie、帳密、驗證破解或付費 actor。
- 數字 ID、明確且非未來發布時間為必要條件；用共用 `display_expiry()` 判斷發布後
  48 小時。沒有來源 expiry 保留 null，不猜 24 小時或取抓取時間。
- 沿用 `post_row/record_source`、原 source ID／story key、`/assets/feed-images/*.webp`。
  已知 key 保留原圖與時間，重複回應改時間也不延長期限。空結果、錯誤、全部不合格、
  下載失敗不清除原快取。
- 每次 1–5 個既有啟用公開來源，每帳號最多 5 張新預覽，循序下載；帳號開始間距
  至少 175 秒。持久化節流＋獨占鎖，先記錄下次可查時間，崩潰後不立即重查。
  無自動重試；服務失敗／載入未完成冷卻 1 小時；429、驗證、拒絕或不明 transport
  失敗停止整批並冷卻 24 小時，不換 session／出口繞過。
- HTTP timeout 25 秒、帳號連線 75 秒／子程序 85 秒上限；輸入／文字回應 2 MB，
  媒體每張 10 MB、讀取迴圈 deadline 30 秒（單次阻塞仍受 25 秒 timeout 約束）、
  WebP 轉檔 timeout 30 秒。不跟 redirect，不落盤短期連線資料。
- `state/insta_stories_viewer.json` 只留去敏結果與節流／冷卻，沿用 Git 忽略。
  `--collect` 另持既有 pipeline lock，原子更新 `state/instagram_public.json`。
  state 壞掉拒絕執行，不重設保護；未加入既有排程或改原 Apify 路徑。

## 啟用、停用與切換

離線重播（無網路、無寫入）：

```sh
.venv/bin/python scripts/insta_stories_viewer.py \
  --input tests/fixtures/insta_stories_viewer/nycu-success-redacted.json \
  --account nycu_harmonica --observed-at 2026-09-23T18:19:39.582Z
.venv/bin/python scripts/insta_stories_viewer.py \
  --input tests/fixtures/insta_stories_viewer/sirius-success-redacted.json \
  --account siriusharmonicaensemble --observed-at 2026-09-23T18:28:37.328Z
```

前者 `eligible_count=0`，後者 1；fixture 不含可下載的 opaque 值。
`collector_available` 只表示該回應有通過資料門檻的項目，不是長期健康／完整性承諾。

單次 live 診斷，不寫正式快取、不碰 Apify：

```sh
HARMONICA_ISV_ENABLED=1 .venv/bin/python scripts/insta_stories_viewer.py \
  --accounts siriusharmonicaensemble
```

以下是**後續操作指令，本次未對正式資料執行**。當 Apify 因預算／provider 暫停而
尚有未覆蓋來源時，可明確選 1–5 個來源，先診斷再進行可選備援；成功空或資料缺欄
不自動擴大範圍、不重試、不清除舊快取：

```sh
HARMONICA_ISV_ENABLED=1 .venv/bin/python scripts/insta_stories_viewer.py \
  --accounts siriusharmonicaensemble --collect
# 授權發布後才執行：
.venv/bin/python scripts/publish_story_cache.py
```

`--collect` 僅更新快取與媒體；publisher 再走既有 watchdog → offline RSS/JSON。
沒有自動退回付費 actor；沒有動登入或前端更新。正式排程／部署另行授權；
本次可選流程是 standalone，不宣稱已排程接線。

可選單張媒體診斷（正常取得的未去敏回應必須放 Git 外）：

```sh
HARMONICA_ISV_DIAGNOSTIC_ENABLED=1 .venv/bin/python scripts/insta_stories_viewer.py \
  --input /tmp/isv-search-result.json --account nycu_harmonica --probe-media
```

最多一張，只輸出 hash／大小／類型、不存圖；不參與 collector 跨程序節流，
不可迴圈呼叫，人工檢查至少間隔 175 秒，遇到驗證或封鎖停止。

停用（不刪 state 或現有快取）：

```sh
unset HARMONICA_ISV_ENABLED HARMONICA_ISV_DIAGNOSTIC_ENABLED
```

一次性環境前綴不會永久啟用。本次未改 `.env`、LaunchAgent、pipeline 或既有部署檔。
Node 與 cwebp 在此機可用；缺工具會安全失敗，不自動安裝。

## 測試與限制

新增測試涵蓋真實 NYCU／天狼星 fixture、成功／空集合、載入中／失敗、不存在、
私人、429、缺失／未來時間、48 小時界線、重複／時間衝突、下載失敗／大小上限、
驗證／拒絕停止、禁 redirect、預設關閉、來源與數量上限、節流／冷卻、壞 state、
既有 watchdog 相容，以及 mock Socket.IO 正常流程。

```sh
.venv/bin/python -m unittest discover -s tests -p 'test_insta_stories_viewer.py'
node --check scripts/insta_stories_viewer_transport.mjs
```

另跑既有 Instagram collector、publisher、catalog、Google 登入、watchdog、
Apify pool 與前端全套（每分鐘／返回分頁更新及失敗保留卡片）。
結果：新增 40 項、既有 Python 104 項、前端 128 項，合計 **272 項通過**；
Node 語法檢查與 diff whitespace 檢查通過。開工時 31 個既有修改／未追蹤檔的
SHA-256 均維持不變。正式 NYCU／Aiden 快取仍在，正式天狼星快取及對應新圖片未寫入。

只有 5 個帳號、6 次完成狀態觀察及一次短時間同帳號覆驗，沒有 179 帳號批次或
長期證據。不能量化真實覆蓋率、新鮮度、完整性、跨日去重、後端分流比例或長期限流。
兩個有資料帳號均未提供原始 expiry，忠實保留未知。天狼星原先無同 ID 的 Apify 快取，
未作跨 provider 實體比對；去重由相同 ID 的實際重播及格式測試證實。
正式排程仍需更長期、低頻、小範圍觀察。

## 後續啟用

本文件記錄初次研究交付狀態。使用者隨後授權加入系統；實際接線、四帳號啟用與
公開發布驗收見[試跑部署紀錄](insta-stories-viewer-rollout-2026-09-24.md)。
