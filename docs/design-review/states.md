# 設計評審截圖清單

每一輪都照這份清單截圖，ID 與 `tools/states.mjs` 一致。每個狀態截兩張：

| 尺寸 | 視窗 | 像素比 | 截圖高度 |
|---|---|---|---|
| `desktop` | 2560 × 1440（1440p） | 1 | 從頁首或指定錨點起，最多 2160 px |
| `mobile` | 390 × 844（觸控） | 2 | 從頁首或指定錨點起，最多 1688 CSS px |

固定條件：資料為 `harmonica.observe.tw` 公開 `/api/v1/catalog` 於 2026-11-05 的快照（366 來源、591 貼文、3 則有效限動、14 活動、797 樂譜）；瀏覽器時鐘固定在 2026-11-05 17:30（Asia/Taipei）；字型以 Noto Sans TC／JP／KR 補齊 CJK；淺色外觀（另列深色狀態）；減少動態效果。圖片與 Google 日曆 iframe 先捲動載入後再截。

## 頁面與狀態

| ID | 頁面 | 狀態 | 語言 | 重現方式 |
|---|---|---|---|---|
| `home-zh` | 首頁 `/` | 有資料（限動、日曆、貼文） | 繁中 | — |
| `home-en` | 首頁 | 有資料 | 英文 | — |
| `home-ja` | 首頁 | 有資料 | 日文 | — |
| `home-ko` | 首頁 | 有資料 | 韓文 | — |
| `home-feed-zh` | 首頁 | 捲到「最新公開貼文」區 | 繁中 | 錨點 `.home-posts` |
| `home-dark-zh` | 首頁 | 深色外觀 | 繁中 | `prefers-color-scheme: dark` |
| `home-loading-zh` | 首頁 | 載入中 | 繁中 | catalog 請求不回應 |
| `home-error-zh` | 首頁 | 載入錯誤 | 繁中 | catalog 回 500 |
| `home-empty-zh` | 首頁 | 空資料 | 繁中 | catalog 各清單為空 |
| `menu-open-zh` | 全站導覽 | 「更多」選單展開 | 繁中 | 點 `.nav-more > summary`，只截視窗 |
| `home-signed-in-zh` | 首頁 | Google 登入後的頁首 | 繁中 | 模擬 session，只截視窗 |
| `posts-zh` | 動態 `/post/` | 有資料 | 繁中 | — |
| `posts-en` | 動態 | 有資料 | 英文 | — |
| `posts-search-zh` | 動態 | 搜尋「口琴樂團」 | 繁中 | `?q=口琴樂團` |
| `posts-no-results-zh` | 動態 | 搜尋無結果 | 繁中 | `?q=zzqxv` |
| `posts-following-empty-zh` | 動態 | 「追蹤中」但尚未追蹤 | 繁中 | `?kind=following` |
| `posts-expanded-zh` | 動態 | 第一則長文展開 | 繁中 | 點第一個「展開」，錨點在該按鈕 |
| `posts-empty-zh` | 動態 | 空資料 | 繁中 | catalog 各清單為空 |
| `events-zh` | 活動 `/events/` | 即將舉行 | 繁中 | — |
| `events-ja` | 活動 | 即將舉行 | 日文 | — |
| `events-past-zh` | 活動 | 過去活動 | 繁中 | `?period=past` |
| `events-country-zh` | 活動 | 篩選日本、全部期間 | 繁中 | `?country=JP&period=allEvents` |
| `events-empty-zh` | 活動 | 空資料 | 繁中 | catalog 各清單為空 |
| `sources-zh` | 來源名錄 `/source/` | 有資料 | 繁中 | — |
| `sources-ko` | 來源名錄 | 有資料 | 韓文 | — |
| `sources-search-zh` | 來源名錄 | 搜尋「口琴社」 | 繁中 | `?q=口琴社` |
| `sources-country-zh` | 來源名錄 | 篩選日本 | 繁中 | `?country=JP` |
| `sources-followed-empty-zh` | 來源名錄 | 只看追蹤、尚無追蹤 | 繁中 | `?followed=1` |
| `source-detail-zh` | 來源頁 `/source/54-cy-leo/` | 貼文多的來源 | 繁中 | — |
| `source-detail-en` | 來源頁（同上） | 貼文多的來源 | 英文 | — |
| `source-detail-sparse-zh` | 來源頁 `/source/134-crossover-harmonica-ensemble/` | 沒有貼文的來源 | 繁中 | — |
| `scores-zh` | 樂譜 `/scores/` | 有資料 | 繁中 | — |
| `scores-no-results-zh` | 樂譜 | 搜尋無結果 | 繁中 | `?q=zzqxv` |
| `score-sources-zh` | 找譜與購譜 `/scores/sources/` | 有資料 | 繁中 | — |
| `score-sources-books-en` | 找譜與購譜 | 篩選「書籍與樂譜」 | 英文 | `?scoreKind=books` |
| `contribute-zh` | 貢獻 API 額度 `/contribute/` | 登入前 | 繁中 | — |
| `contribute-signed-in-zh` | 貢獻 API 額度 | 登入後、有一筆貢獻 | 繁中 | 模擬 session |
| `submit-zh` | 回報來源 `/submit/` | 登入前 | 繁中 | — |
| `submit-signed-in-zh` | 回報來源 | 登入後、有兩筆回報 | 繁中 | 模擬 session，錨點 `#submission-form` |
| `feeds-zh` | 訂閱 `/feeds/` | 有資料 | 繁中 | — |
| `status-zh` | 系統狀態 `/status/` | 有資料 | 繁中 | — |
| `about-zh` | 關於 `/about/` | FAQ 收合 | 繁中 | — |
| `about-faq-open-zh` | 關於 | 第一題 FAQ 展開 | 繁中 | 點第一個 `details.faq summary` |
| `privacy-zh` | 隱私 `/privacy/` | — | 繁中 | — |
| `not-found` | 不存在的網址 `/no-such-page/` | 404 | 繁中 | — |

模擬登入的 session 見 `tools/states.mjs` 的 `SIGNED_IN_SESSION`（虛構帳號，未連到任何真實服務）。

## 參考對手

第一輪截一次，之後每輪重用同一組檔案：

| ID | 網址 | 對應的我方頁面 |
|---|---|---|
| `luma-discover` | https://luma.com/discover | 首頁／探索 |
| `luma-city-calendar` | https://luma.com/taipei | 活動與行事曆 |
| `bandsintown-home` | https://www.bandsintown.com/ | 首頁／活動探索 |
| `bandsintown-artist` | https://www.bandsintown.com/a/15521707-the-search | 來源（藝人）頁 |
| `bluesky-profile-feed` | https://bsky.app/profile/bsky.app | 來源頁的貼文串、動態 |

## 重現

```bash
# 1. 公開 catalog 快照（每次 hill climb 只抓一次）
curl -s https://harmonica.observe.tw/api/v1/catalog > /tmp/hc-review/data/catalog.json
curl -s https://harmonica.observe.tw/api/v1/community > /tmp/hc-review/data/community.json
# 2. 唯讀預覽（基準版用 `git archive main web scripts/render_shell.py site` 匯出的目錄）
python3 docs/design-review/tools/snapshot_server.py --repo . --port 8402 \
  --catalog /tmp/hc-review/data/catalog.json --community /tmp/hc-review/data/community.json
# 3. 截圖（tools/node_modules 指向裝有 playwright 的目錄；FONTCONFIG_FILE 加入 Noto Sans CJK）
node docs/design-review/tools/capture.mjs site http://127.0.0.1:8402 OUT_DIR
node docs/design-review/tools/capture.mjs references OUT_DIR
```
