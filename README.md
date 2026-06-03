# Matters Newsletter Bot（周報 / 月報）

自動為 Matters 編製「周報」「月報」草稿的小工具。**與 repost-bot 是兩個獨立專案，互不相干。**

它只讀取 Matters 自己的公開 GraphQL API，把多篇文章整理成**一張草稿**（內含 @作者
提及與文章連結），放進指定帳戶的草稿箱。**只整草稿、不會自動發佈** —— 由你檢查後手動發佈。

## 三種模式

| 類型 | 內容 | 排程 |
|------|------|------|
| `weekly`（一周熱門） | 合併七個頻道、過去 7 日的文章，**自己按「拍手＋留言」排序**取前 10，每位作者最多 2 篇，tag 作者 | 每週一 HKT 06:00 |
| `snapshot`（每日快照） | 記下當日各頻道置頂（綠色 pin）文章到 `state/channel_pins.json`，累積一個月 | 每日 HKT 07:00 |
| `monthly`（頻道精選） | 列出過去 30 日內**曾被置頂過**的所有文章（讀累積狀態），按頻道分組，tag 作者 | 每月 1 號 HKT 10:00 |

六個精選頻道：生活事、書音影、旅・居、性別／愛、時事・趨勢、身心靈
（週熱門排序另含「創作・小說」以擴大覆蓋；如需增減，改 `bot/digest.py` 的
`CHANNELS` / `WEEKLY_CHANNELS`）。

### 為何週熱門要自己排序？
Matters 官方的 `hottest` feed 偏重「新」而非互動，會漏掉互動高但稍舊的文。
本工具改為合併各頻道、用「拍手＋留言」透明計分，數字你可自行核對。

### 為何頻道精選要每日快照？
Matters 公開 API 只給「目前置頂」狀態，**沒有 pin 歷史**。綠色 pin 一個月會輪換
多次，舊的被換走後就查不到。所以靠每日 `snapshot` 記錄，月報才能列出整個月曾被
pin 過的文。已經換走、且開始累積前的舊 pin 無法追溯。

## 本機試跑

```bash
pip install -r requirements.txt

# 只在終端機印出內容、不開草稿：
python -m bot.digest --type weekly --dry-run
python -m bot.digest --type monthly --dry-run

# 真的開草稿（需要先設定帳戶憑證，見下）：
cp .env.example .env   # 填入新帳戶 email / password
set -a; source .env; set +a
python -m bot.digest --type weekly
```

## 測試環境（matters.icu）：讀正式站、寫測試站

測試期間的需求是：**從正式站（matters.town）抓真實熱門文**，但把草稿**貼到 icu 測試站**，
讓能登入 matters.icu 的團隊一起檢視評估（草稿放在個人草稿箱別人看不到）。

因此本工具的讀／寫端可分開設定：

| 變數 | 作用 | 預設 |
|---|---|---|
| `MATTERS_READ_ENDPOINT` | 抓文章資料的來源 | 正式站 `server.matters.news` |
| `MATTERS_WRITE_ENDPOINT` | 草稿貼去哪、用哪個帳戶登入 | 同 read |
| `MATTERS_SITE` | 文章連結的網址（文章實際所在） | `https://matters.town` |

「讀正式站、寫 icu」只需設一個變數（read/site 留預設，連結才會指向真正的 matters.town 文章）：

```bash
cd ~/Desktop/newsletterbot
# dry-run（讀正式站、只組稿、不登入不發）
MATTERS_WRITE_ENDPOINT=https://server.matters.icu/graphql \
python -m bot.digest --type weekly --dry-run

# 真的把草稿貼到 icu（用 icu 測試帳戶）
MATTERS_WRITE_ENDPOINT=https://server.matters.icu/graphql \
MATTERS_EMAIL=你的icu帳戶 MATTERS_PASSWORD=你的icu密碼 \
python -m bot.digest --type weekly
```

也可用 GitHub Actions 的 **「TEST on icu」** workflow（手動觸發），詳見下節。

注意：
- icu 的帳戶與正式站**不共用**，必須在 matters.icu 另外註冊。
- 草稿內容來自正式站，所以是真實熱門文；連結指向真正的 matters.town 文章。
- **被 tag 的正式站作者不會收到通知**：草稿從不發佈（@提及只在發佈時才通知），
  且 icu 與正式站是獨立系統，無法跨系統通知。
- 內建 **host 白名單**：read/write 只接受 `server.matters.news / .town / .icu`，
  打錯網址會直接中止，避免把帳號憑證送去未知伺服器。

## GitHub Actions（自動排程）

兩個 workflow 在雲端按排程執行，所以憑證要存在 **GitHub repo secrets**，不是本機 `.env`：

1. repo → Settings → Secrets and variables → Actions → New repository secret
2. 新增 `DIGEST_MATTERS_EMAIL`（新帳戶電郵）
3. 新增 `DIGEST_MATTERS_PASSWORD`（新帳戶密碼）

之後可在 Actions 分頁手動 **Run workflow**（dry_run 選 true 可先試）。

## 已知限制

- **頻道精選的 pin 歷史**只能「從開始每日快照後」累積 —— 在啟用 `snapshot` 之前
  就已被換走的舊 pin 無法追溯（Matters 沒有 pin 歷史 API）。約一個月後覆蓋才完整。
- 「兩周內新人歡迎」功能**未實作**：公開 API 沒有「全站所有註冊用戶」查詢，且最新
  文章 feed 充斥 SEO／賭博垃圾帳號，需嚴格過濾才可能做。
