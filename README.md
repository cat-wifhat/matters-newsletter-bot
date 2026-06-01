# Matters Newsletter Bot（周報 / 月報）

自動為 Matters 編製「周報」「月報」草稿的小工具。**與 repost-bot 是兩個獨立專案，互不相干。**

它只讀取 Matters 自己的公開 GraphQL API，把多篇文章整理成**一張草稿**（內含 @作者
提及與文章連結），放進指定帳戶的草稿箱。**只整草稿、不會自動發佈** —— 由你檢查後手動發佈。

## 兩種周報

| 類型 | 內容 | 排程 |
|------|------|------|
| `weekly`（一周熱門） | 全站過去 7 日最熱門文章，取前 10（已按拍手／留言／閱讀時長排序），tag 作者 | 每週一 HKT 06:00 |
| `monthly`（頻道精選） | 六個頻道目前置頂（綠色 pin = 精選）的文章，tag 作者 | 每月 1 號 HKT 10:00 |

六個頻道：生活事、書音影、旅・居、性別／愛、時事・趨勢、身心靈
（「創作・小說」未納入；如需增減，改 `bot/digest.py` 的 `CHANNELS`）。

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

## GitHub Actions（自動排程）

兩個 workflow 在雲端按排程執行，所以憑證要存在 **GitHub repo secrets**，不是本機 `.env`：

1. repo → Settings → Secrets and variables → Actions → New repository secret
2. 新增 `DIGEST_MATTERS_EMAIL`（新帳戶電郵）
3. 新增 `DIGEST_MATTERS_PASSWORD`（新帳戶密碼）

之後可在 Actions 分頁手動 **Run workflow**（dry_run 選 true 可先試）。

## 已知限制

- **頻道精選**只能拿到「目前置頂」的文章 —— Matters 公開 API 沒有 pin 歷史，
  抓不到「本月曾置頂、現已撤下」的文。頻道 pin 會輪換，故「目前置頂」≈ 最近精選。
- 「兩周內新人歡迎」功能**未實作**：公開 API 沒有「全站所有註冊用戶」查詢，且最新
  文章 feed 充斥 SEO／賭博垃圾帳號，需嚴格過濾才可能做。
