# Google 帳號登入

每一頁的頂端導覽（含首頁、桌面與手機）都提供可見的 Google 登入入口，登入後改顯示「我的帳號」。首頁登入會返回首頁；貢獻 `/contribute/` 和投稿 `/submit/` 提供四語帳號資訊及登出。未登入仍能用原瀏覽器管理；第一次登入會原子移轉該瀏覽器尚未綁定的貢獻與投稿。同一 Google 帳號可跨裝置取回；切換 Google 帳號不會移轉已綁定的紀錄。

## 設定

1. 在 Google Auth Platform 的 Web application client 加入 **`https://harmonica.observe.tw/auth/google/callback`**。使用後端 authorization code flow，不需要 JavaScript origin。
2. 本機 `.env`（0600、不可提交）設定 `HARMONICA_LOGIN_GOOGLE_CLIENT_ID` 與 `HARMONICA_LOGIN_GOOGLE_CLIENT_SECRET`。部署沿用維護者現有 observe.tw OAuth client；不共用其他服務的資料庫、登入 cookie 或加密密鑰。
3. `.venv/bin/python -m pip install -r requirements.txt`，再依 `local-hosting.md` 重啟 `tw.observe.harmonica.web`。
4. 正式環境必須有 `HARMONICA_PUBLIC_ORIGIN=https://harmonica.observe.tw`、`HARMONICA_TRUST_PROXY=1`，由本機 HTTPS proxy 轉送。若要本地 Google 真人登入，須另外在同一 Google client 加上對應 `http://localhost:8330/auth/google/callback`。

Google Audience 必須允許預期使用者登入；Testing 時依 Google 設定加入測試使用者。登入只要求 `openid email profile`，不要求行事曆、Gmail 或 Drive 權限，也不要求 offline access。

## 安全與儲存

- `POST /auth/google/start` 要求有效 session、同源 Origin 和 CSRF header；回傳 Google URL，設定短效 HttpOnly／SameSite=Lax 流程 cookie，正式環境加 Secure。
- 流程狀態存於既有私有 SQLite 的 `oauth_flows`，10 分鐘有效，一次性 state 與獨立 cookie 綁定，另使用 nonce、PKCE S256。重啟登入會取代同 session 的舊流程。
- callback 僅接受已記錄的 origin。以 Google 官方 `google-auth` 驗證 ID token 簽章、issuer、audience、期限，並核對 nonce、azp 與 verified email。錯誤回傳固定訊息，不記錄授權碼、token 或 Secret。
- 以 Google `sub` 作為穩定身份；`google_accounts` 儲存 subject、內部 owner、姓名和 email。不保留 Google access/refresh/ID tokens。
- 登入完成後更換 session 和 CSRF token，HttpOnly／SameSite=Strict，正式環境加 Secure，30 天有效。匿名 cookie 保留原本 180 天期限。
- 匿名紀錄移轉與 session 更新在單一 SQLite transaction 進行。登出只撤銷目前裝置 session 和待處理登入，不撤回 Apify 貢獻，也不影響其他裝置。
- 姓名和 email 只出現在私有的 `/api/v1/session` 回應，頁面顯示經 HTML escaping；公開 community API 不含帳號資訊。

## 驗證

```sh
.venv/bin/python -m unittest discover -s tests -p 'test_google_login.py'
node --test web/tests/google_login.test.mjs
```

測試涵蓋 cookie/state 綁定、重播、期限、CSRF、HTTPS、取消、provider failure、真實 RSA 簽署的測試 ID token 驗證、匿名資料移轉、跨裝置存取、帳號切換隔離、撤回貢獻、登出、四語 UI、身分文字 escaping 與表單草稿保留。Google 真人帳號的完整登入須由使用者在 Google 畫面完成。
