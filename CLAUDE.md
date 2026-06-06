# CLAUDE.md

本檔供 Claude Code 在此倉庫工作時參考，概述架構、關鍵決策與慣例。

## 專案是什麼

為 Matters 自動編製「周報／月報」**草稿**的小工具。只讀取 Matters 公開 GraphQL
API，把多篇文章整理成**一張草稿**（含 @作者提及與文章連結），放進指定帳戶的草稿箱。

- **只整草稿、永不自動發佈** —— 由人檢查後手動發佈。
- 與 `repost-bot` 是**兩個獨立專案**，互不相干，不共用程式碼。
- 不爬外部網站，只打 Matters 自家 API。

## 三種模式（`python -m bot.digest --type ...`）

| 模式 | 內容 | 排程（HKT） | Workflow |
|------|------|------|------|
| `weekly` | 合併七個頻道、過去 7 日文章，按「拍手＋留言」排序取前 10，每作者≤2 篇，tag 作者 | 週一 06:00 | `digest-weekly.yml` |
| `snapshot` | 記錄當日各頻道置頂（綠色 pin）文章到 `state/channel_pins.json`，累積一個月 | 每日 07:00 | `digest-snapshot.yml` |
| `monthly` | 先補當日快照，再列出過去 30 日內**曾被置頂過**的所有文章，按頻道分組，tag 作者 | 每月 1 號 10:00 | `digest-monthly.yml` |

cron 以 UTC 計：週一 06:00 HKT = 週日 22:00 UTC；每日 07:00 = 23:00 UTC；月初 10:00 = 02:00 UTC。

## 架構（`bot/`）

- `config.py` — 環境變數、端點解析、host 白名單。**讀／寫端可分離**（見下）。
- `matters_client.py` — 極簡 GraphQL client：只有 `login` / `create_empty_draft` /
  `update_draft`。**無圖片上傳、無發佈**。打的是 `MATTERS_WRITE_ENDPOINT`。
- `digest.py` — 主程式。匿名讀取（打 `MATTERS_READ_ENDPOINT`）→ 計分／快照 →
  組 HTML → 視情況登入寫草稿。`main()` 為 CLI 入口。

資料流：**匿名讀取 SOURCE 環境** → 組稿 →（非 dry-run 才）**登入並寫到 DESTINATION 環境**。

## 關鍵決策（改動前務必理解）

1. **不用官方 `hottest` feed**：官方演算法偏「新」而非互動，會漏掉互動高但稍舊的文。
   改為合併各頻道、用「拍手＋留言」透明計分，數字可逐篇核對。評選準則正式記於
   `CRITERIA.md`（視為憑證，改動會留 git 紀錄）。

2. **頻道精選靠每日快照累積**：Matters 公開 API 只給「目前置頂」狀態、**無 pin 歷史**。
   綠色 pin 一個月輪換多次，舊的被換走就查不到。故 `snapshot` 每日記錄，`monthly`
   據累積狀態列整月。**啟用快照之前**就被換走的舊 pin 無法追溯（約一個月後覆蓋才完整）。

3. **讀／寫端分離**：可從正式站讀真實熱門文，但把草稿貼到 icu 測試站給團隊檢視。
   - `MATTERS_READ_ENDPOINT` — 抓資料來源（預設 `server.matters.news`）
   - `MATTERS_WRITE_ENDPOINT` — 草稿目的地＋登入帳戶（預設＝read）
   - `MATTERS_SITE` — 文章連結網址（預設 `https://matters.town`，指向文章真正所在）
   - `MATTERS_GRAPHQL_ENDPOINT` — back-compat：未設上述兩者時同時設定 read＋write
   - 「讀正式站、寫 icu」只需設 `MATTERS_WRITE_ENDPOINT`，read/site 留預設。

4. **host 白名單**（`ALLOWED_API_HOSTS`）：read/write 只接受
   `server.matters.news / .town / .icu`，打錯網址直接中止，避免把帳號憑證送到未知伺服器。

5. **不放圖片**：HTML 組稿刻意不含 `<figure>`，避開 `putDraft` 的圖片處理坑。

6. **icu 與正式站獨立**：帳戶不共用，需在 matters.icu 另註冊測試帳戶。被 tag 的正式站
   作者**不會收到通知**（草稿從不發佈，@提及只在發佈時通知，且兩系統無法跨系統通知）。

## 慣例

- **頻道清單**改 `bot/digest.py` 的 `CHANNELS`（月報六頻道）/ `WEEKLY_CHANNELS`
  （週報另含「創作・小說」共七頻道）。頻道 id 為 base64 GraphQL node id，註解附解碼值。
- **時間一律 UTC**；日期字串用 ISO `YYYY-MM-DD`。
- **狀態檔** `state/channel_pins.json` 由 snapshot/monthly workflow 自動 commit 回倉庫
  （`permissions: contents: write` + 失敗重試 rebase）。結構：
  `{ channel_id: { shortHash: {title, author, first_seen, last_seen} } }`，
  超過 `PIN_RETENTION_DAYS`（35 天）未見即清除。icu 測試用獨立的 `state/icu-test-pins.json`。
- **憑證**：雲端跑用 GitHub repo secrets（`DIGEST_MATTERS_EMAIL/PASSWORD`；icu 測試用
  `ICU_MATTERS_EMAIL/PASSWORD`），**不要**進 `.env`。本機跑才用 `.env`（已 gitignore）。
- **依賴**極簡，只有 `requests`（見 `requirements.txt`）；Python 3.11。

## 本機試跑

```bash
pip install -r requirements.txt
python -m bot.digest --type weekly --dry-run     # 只印不發
python -m bot.digest --type monthly --dry-run

# 讀正式站、把草稿貼到 icu：
MATTERS_WRITE_ENDPOINT=https://server.matters.icu/graphql \
MATTERS_EMAIL=你的icu帳戶 MATTERS_PASSWORD=你的icu密碼 \
python -m bot.digest --type weekly
```

`--dry-run` 或 `DRY_RUN=true` 皆只組稿不登入不發。

## 已知限制

- 頻道精選的 pin 歷史只能「從開始快照後」累積，無法回溯。
- 「兩周內新人歡迎」**未實作**：公開 API 無「全站所有註冊用戶」查詢，且最新文章 feed
  充斥 SEO／賭博垃圾帳號，需嚴格過濾才可能做。
