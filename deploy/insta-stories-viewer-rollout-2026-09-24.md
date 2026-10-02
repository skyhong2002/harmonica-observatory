# InstaStoriesViewer 備援試跑：2026-09-24

使用者在研究交付後授權「直接開始試試看、加進系統」。本文件記錄實際啟用狀態，
取代[初次評估](insta-stories-viewer-evaluation-2026-09-24.md)中「尚未接排程／發布」的階段性描述。
研究明細與五帳號實測仍見該文件及[去敏結果](insta-stories-viewer-results-2026-09-24.json)。

## 現在的接線

`run_pipeline.py` 在既有 Apify 限動抓取、快取發布之後，profile 抓取之前，
依 `HARMONICA_ISV_ENABLED=1` 執行 `insta_stories_viewer.py --scheduled --pipeline-lock-held`。
`--skip-instagram` 或 `--skip-watch` 會跳過。備援錯誤是 optional step，保留其他流程。
不修改 Apify 額度、actor 參數或既有排程頻率；備援及其 publisher 不啟動任何付費 actor。

這台主機的 `.env` 已設：

```dotenv
HARMONICA_ISV_ENABLED=1
HARMONICA_ISV_ACCOUNTS=siriusharmonicaensemble,nycu_harmonica,aidensoon,taiwanharmonica,toshimiller
HARMONICA_ISV_BATCH_SIZE=1
```

版本庫 `.env.example` 仍預設 `0`，未提交本機 `.env`。不擴至所有 179 個來源。
排程每輪最多 1 帳號，跨程序至少 3 小時；每帳號至少間隔 12 小時。
最近 12 小時已有來源成功快取（包括 Apify）或備援查詢者會跳過，優先輪到最久未查者。
明確名單最多 5 帳號；batch 設定硬上限 2，本機保持 1。
跨帳號正常請求至少間隔 175 秒，無立即重試；服务失敗／仍載入冷卻 1 小時，
429、驗證、拒絕存取或未知傳輸失敗停止整批並冷卻 24 小時。
每個傳輸最多 85 秒、單張下載最多 10 MB、每帳號最多 5 張預覽。
詳細逾時與降級處理見 adapter；影片只取靜態預覽，不下載影片。

`state/insta_stories_viewer.json` 記錄下次允許時間、逐帳號查詢結果及最後發布結果。
預約時間在網路請求前落盤，程序中斷也不會立即重試。使用 adapter 自己的鎖與
現有 pipeline 鎖；由 pipeline 呼叫時不重複取得／釋放父程序的鎖。
空結果、缺時間、下載失敗不清除既有資料。合格資料沿用 story ID、既有本機媒體
和 `publish_story_cache.py`，展示期限保持原始發布時間加 48 小時。

已讀取並確認兩個 launchd job 均載入、間隔 1800 秒、指向此 checkout：
`tw.observe.harmonica.pipeline`、`tw.observe.harmonica.social-fast`。
下次啟動會讀取新程式與 `.env`，不需重新安裝 LaunchAgent 或重啟網站。
兩個 job 共用同一份節流 state，不會加倍查詢。這次未手動啟動整條 pipeline，
避免為驗收額外呼叫付費 actor；既有例行 Apify 流程仍按原預算執行。

## 實際發布驗收

2026-09-24 02:58（Asia/Taipei），以獨立 collector 取得共用 pipeline 鎖後執行：

```sh
HARMONICA_ISV_ENABLED=1 .venv/bin/python scripts/insta_stories_viewer.py \
  --accounts siriusharmonicaensemble --collect --publish
```

| 項目 | 實際結果 |
| --- | --- |
| 查詢完成時間 | 2026-09-23T18:58:33.501097Z |
| 查詢耗時 | 2.284 秒（下載／轉檔另計） |
| 限動數／合格數／匯入數 | 1 / 1 / 1 |
| Story ID | `3992702751863962825` |
| 原始發布時間 | 2026-09-24 02:14:39 +08:00 |
| 展示期限 | 2026-09-26 02:14:39 +08:00 |
| 原始到期時間 | 未提供，保持未知 |
| 發布 | `published`, sources=1, pendingStories=1, publishedStories=1 |
| 公開媒體 | HTTP 200, image/webp, 95,922 bytes, 640 × 1136 |
| 公開媒體 SHA-256 | `ac5e1986cbb73b65c35423b1a02204d2f096b14aec5be1e79364c214a4fd287a` |

公開 `/api/v1/catalog` 查到同一 ID、原始發布與 48 小時期限；媒體 hash 與本機相同。
新開瀏覽器載入 `https://harmonica.observe.tw/`，DOM 中天狼星限動卡及圖片均可見，
圖片 `complete=true`、naturalWidth=640、naturalHeight=1136，錯誤提示為 hidden。
畫面顯示 9 月 24 日 02:14 發布、9 月 26 日 02:14 展示截止，沒有手動更新按鈕。
持續觀察該瀏覽器頁面，catalog 請求在載入後約 0.24、60.47、120.47 秒出現，
證實每分鐘自動更新仍實際執行，更新後同一張卡片及圖片仍存在。
既有 NYCU 與 Aiden 的完整來源快取物件與發布前完全相同。

隨後執行 `--scheduled`，回覆 `scheduled_wait`，未追加任何上游請求。
本次手動發布也預約三小時排程間隔：最早 2026-09-24 05:58:31 +08:00 可再查詢，
實際執行仍取決於例行 pipeline 與來源是否到期。尚未等候／宣稱下一輪計時觸發已完成。

## 操作與停用

在專案目錄執行。永久停用只改本機開關，不移除快取：

```sh
.venv/bin/python - <<'PY'
from pathlib import Path
import re
p = Path('.env')
s = p.read_text()
s = re.sub(r'^HARMONICA_ISV_ENABLED=.*$', 'HARMONICA_ISV_ENABLED=0', s, flags=re.M)
p.write_text(s)
PY
```

重新啟用將上面 `=0` 改成 `=1`，保留本文件的四帳號名單與 batch=1。
設定只影響新程序，已在執行中的 bounded 查詢會完成；不需刪 state、解鎖或重啟服務。
若 shell/LaunchAgent 顯式設定同名環境變數，環境優先於 `.env`；本次兩個已載入 job
均未設定 ISV 變數。只做單次停用驗證可用：

```sh
HARMONICA_ISV_ENABLED=0 .venv/bin/python scripts/insta_stories_viewer.py --scheduled
# 回覆 disabled，exit 2；不網路請求、不寫快取。
```

手動沿用排程限制試跑（會抓取並發布，未到時間則直接略過）：

```sh
.venv/bin/python scripts/insta_stories_viewer.py --scheduled
```

不要人工循環呼叫 `--accounts` 或刪節流 state。`--pipeline-lock-held` 只供確實持鎖的
orchestrator 使用，人工操作不用此參數。保留 `.env`、nonce、原始含媒體存取值的回應於 Git 外。

## 驗證與未證實範圍

152 個 Python 測試及 128 個前端測試通過，共 **280 項**；Node 語法、Git whitespace
檢查通過。Python 包括 adapter 44、pipeline 4，以及 collector、publisher、catalog、
watchdog、Apify pool、Google 登入共 104。新增覆蓋輪替／最近成功略過、三小時預約、
父鎖保留、發布失敗保留快取、開關與 skip 參數、pipeline 呼叫順序。
前端原有每分鐘／返回分頁更新測試仍通過，這輪沒有修改前端或登入程式。

這是四個帳號的備援試跑，不是已證實的長期／179 帳號替代方案。
NYCU 後端曾回傳無原始時間、非原始數字 ID；目前仍會拒絕匯入該種資料。
ntubluesound 的 436 服務錯誤未解決，未納入排程名單。
沒有官方公開 API 合約；內部 Socket.IO 與 CDN 格式可能變動。
天狼星同 ID 在短時間多次一致，不足以证明跨日新鮮度或完整覆蓋。

原工作樹的 31 個既有修改／未追蹤檔中，29 個 SHA-256 完全保持；僅在
`.env.example` 與 `deploy/apify-pool.md` 保留原修改後補上本次設定／文件。
其餘本輪接線為 `scripts/run_pipeline.py`、`tests/test_run_pipeline.py`，及研究階段
新增的 adapter／transport／fixture／測試／部署紀錄。本機 state、媒體及 `.env` 未追蹤於 Git。
