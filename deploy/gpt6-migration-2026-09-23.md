# GPT-6 專案設定遷移（#33）

> 2026-10-02 起由 AI 閘道取代：預設 `HARMONICA_LLM_PROVIDER=gateway`，只請求 `sky-fast`／`sky-quality` 別名，部署模板不再指定具體模型；2026-10-03 起移除 Codex CLI 備援與 `HARMONICA_CODEX_MODEL`。見 [本機服務](local-hosting.md#ai-閘道推論)。下文為當時紀錄。

依使用者要求，所有口琴觀測站的模型預設及執行設定改為GPT-6系列。參照 [OpenAI GPT-6 遷移說明](https://developers.openai.com/api/docs/guides/latest-model/gpt-6-astra.md#migration-quickstart)，保留各流程原有用途與成本層級：

| 流程 | 設定 | 模型 |
| --- | --- | --- |
| 預設本機Codex分類 | HARMONICA_CODEX_MODEL | gpt-6-sol |
| 明確指定外部投稿審核命令 | HARMONICA_INTAKE_AI_MODEL | gpt-6-sol |
| 選用的獨立API計費模式 | HARMONICA_LLM_MODEL | gpt-6-luna |

程式預設、實際Codex `--model` 參數、`.env.example`、本機`.env`、pipeline／social-fast／submission-intake部署模板及已安裝的LaunchAgent檔案同步更新。CLI不再繼承不明的隱含模型。日曆維護與HTTP伺服器本身不執行模型推論，未修改其工作方式；其他專案、全域Codex／Bamboo設定和歷史資料中的模型來源不改寫。

GPT-6的舊Chat Completions分類請求在reasoning不是none時移除不相容的temperature、top_p、top_logprobs、logprobs，保留推理設定、JSON輸出與原始輸入。沒有更換endpoint、放開工具或新增訪客端推論。

本機Codex保存登入、唯讀隔離、每小時共用12次上限、180秒期限及禁止自動切換付費API皆保留；站方Apify每月US$4上限未更動。重載排程使用RunAtLoad=false，沿用原間隔，避免設定修改立即觸發抓取。等待原本正在執行的social-fast自然結束後才重載，未中止抓取；三個工作均已由launchctl核對載入的環境為GPT-6模型。

驗證：模型預設、CLI參數、API序列化、快取來源、原上限與隔離的55項聚焦測試通過；完整當前工作目錄299項Python測試通過。真實Codex以gpt-6-sol完成一次公開口琴活動分類，回傳musicEvent=true及instrument=harmonica；前一個通用JSON smoke test雖返回可解析JSON但未符合測試欄位，未計為語意通過。兩次均經原共用額度帳本，未呼叫付費API或啟動pipeline。
