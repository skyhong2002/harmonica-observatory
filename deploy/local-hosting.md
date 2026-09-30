# Harmonica Observatory 本機服務

此部署從 GitHub Pages 靜態首頁轉為本機 Python 服務。Caddy 只反代此服務；資料抓取與瀏覽服務分開運行。既有 `site/api/`、圖片、來源 permalink、RSS／ICS 仍可使用。

## 快速啟動

```bash
cd /Users/skyhong/Documents/Harmonica-in-Taiwan
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python scripts/build_local.py
.venv/bin/python scripts/serve.py --host 127.0.0.1 --port 8330
```

開啟 <http://localhost:8330/>。語言可使用 `?lang=zh-Hant`、`en`、`ja`、`ko`。國家條件與語言無關。

`build_local.py` 只重建本機已有的 CSV／抓取快照，不啟動 Apify actor、不跑 Codex、不寫 Google Calendar、不 push。全新 clone 尚無歷史貼文／抓取圖片屬正常；來源目錄與指定曲可由追蹤的 CSV 建出。既有安裝的 `state/`、`data/feeds/` 與 `site/assets/` 是 runtime 資料，遷移時需另行備份。

## macOS 常駐

```bash
.venv/bin/python scripts/install_local_service.py --install \
  --public-origin https://harmonica.observe.tw
```

服務 `tw.observe.harmonica.web` 使用此 checkout `.venv/bin/python`，監聽 `127.0.0.1:8330`，由 launchd 自動重啟。Logs 在 `logs/web.log`、`logs/web.err.log`。安裝器不更動 DNS 或 Caddy。

```bash
launchctl print gui/$(id -u)/tw.observe.harmonica.web
curl http://127.0.0.1:8330/api/v1/health
```

更新 Python 程式後重啟：

```bash
launchctl kickstart -k gui/$(id -u)/tw.observe.harmonica.web
```

## DNS 與 HTTPS

將 `deploy/Caddyfile.snippet` 的站台區塊併入 Caddy 設定。不要覆蓋其他網站的設定。

- DNS 指向這台機器的可連線公開 IP；若路由器後面，需讓 80／443 到達 Caddy。
- Caddy 反代 `127.0.0.1:8330`。無需向外開放 8330。
- `HARMONICA_PUBLIC_ORIGIN=https://harmonica.observe.tw` 限定可接受的公開 Host／Origin。
- `HARMONICA_TRUST_PROXY=1` 僅信任 loopback 的 HTTPS proxy header；直接公開 HTTP 不接受 token 貢獻。
- 本機 `localhost:8330`／`127.0.0.1:8330` 可直接測試，包括社群功能。

正式切換後驗證 `/`、`/source/`、`/contribute/`、`/api/v1/health`、既有來源 URL 與 RSS，不只看 DNS 查詢成功。新版本不需要 `gh-pages`；舊版 Pages 是切換前的快照。

## 排程與額度

`deploy/tw.observe.harmonica.pipeline.plist` 與 `social-fast.plist` 已改用專案 venv 並直接更新本機產物；不再依賴 `--publish-pages`。安裝到 `~/Library/LaunchAgents/` 後重新載入。保留既有調度間隔和 IG 每次嘗試上限，避免額度突增。

詳見 [Apify 池](apify-pool.md)。所有新 actor 請求先預留完整上限；不明結果保留預留，不能以重試繞過額度。社群貢獻上限為累計授權，不會在換月自動重置。

## Codex 額度

預設 `HARMONICA_LLM_PROVIDER=codex`：利用本機 `codex login` 已保存的 ChatGPT 登入，在維護者的抓取／整理流程中執行只讀結構化分類。沒有公開 inference endpoint；訪客只讀快取資料與隨程式附帶的四語文字。

- `HARMONICA_CODEX_BIN`：CLI 執行檔，可省略。
- `HARMONICA_CODEX_MODEL=gpt-6.1-sol`：明確傳入 Codex CLI；未設定時程式也使用此值，不再依賴 CLI 的隱含模型。
- `HARMONICA_LLM_MODEL=gpt-6-luna`：僅供明確啟用的舊 API 模式使用。
- `HARMONICA_CODEX_MAX_CALLS_PER_HOUR=12`：所有抓取程序共用的上限。
- `HARMONICA_CODEX_TIMEOUT=180`：每次最長秒數。
- `HARMONICA_LLM_PROVIDER=disabled`：完全停用新推論。
- 僅明確設定 `HARMONICA_LLM_PROVIDER=openai` 才使用原 API key 模式與其獨立計費。

登入失效、額度耗盡、鎖被占用或逾時會保留現有資料，不會自動切換付費 API。`state/codex/usage.json` 記錄呼叫數與最後結果。不要複製或公開 Codex 登入憑證。這是本機維護者流程，不是將個人登入暴露為訪客服務。

官方方式參考：[Codex non-interactive mode](https://learn.chatgpt.com/docs/non-interactive-mode)。

## 貢獻與資料回報

Apify token 以 Fernet 加密放在 `state/community/community.sqlite3`，密鑰 `state/community/encryption.key`，目錄 0700、檔案 0600。SQLite／密鑰都需備份；遺失密鑰即無法再解密。任何 public API 不含 token 或 Apify 個人身份。

目前使用此瀏覽器的 HttpOnly cookie 識別貢獻者，不是跨裝置 OAuth 帳號。使用者可在原瀏覽器撤回授權；清除 cookie 後，可到 Apify 撤銷原 token。撤回不會取消已開始的 actor，也不會抹掉必要的支出記錄。

公開資料回報保存在本機審核佇列，送出頁面會標明待審核：

```bash
.venv/bin/python scripts/review_community_submissions.py list
.venv/bin/python scripts/review_community_submissions.py export sub_ID --name 'Verified name' --kind source
.venv/bin/python scripts/review_community_submissions.py mark sub_ID accepted
```

`export` 僅送到現有來源驗證 intake，並標記 `reviewing`；不直接信任回報內容、不直接增加 CSV、不自動發文。`accepted` 應僅在公開來源完成驗證與發布後標記，狀態會出現在提交者原瀏覽器。

## API 與模組

- `web/`：新版介面及語系，與產生資料分離。
- `scripts/global_catalog.py`：來源／貼文／活動／樂譜統一模型，保留原文、原始連結和活動時區。
- `scripts/serve.py`：路由、公開 API、CSRF／同源驗證及檔案白名單。
- `scripts/community.py`：瀏覽器身份、加密 token、貢獻預算及回報。
- `scripts/apify_pool.py`：額度刷新、原子預留、平台分配與頻率估算。
- `scripts/llm_backend.py`：維護者的 Codex 批次資料整理。

`GET /api/v1/catalog` 是完整快照；`GET /api/v1/sources`、`posts`、`events`、`scores` 支援 `q`、`country`、`limit`（最高 200）、`offset`。讀取不需要登入。社群寫入需 session CSRF token 及同源 Origin。
