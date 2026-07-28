# Project Intake Checklist — Matters Newsletter Bot（周報／月報）

> 依 `thematters/matters-release-evaluation-agent` 的 Project Intake Checklist 填寫。
> 評估對象：dw-wq/matters-newsletter-bot。日期：2026-06-14。
>
> ⚠️ **本檔為 2026-06-14 當時快照**，之後 bot 有多次變更（雙週報移除「置頂精選」欄與每日快照、
> 啟用自動發佈、改週三出刊等）。**最新狀態以 `CLAUDE.md` 與 `docs/自動化運維手冊.md` 為準**；
> 本歷史評估報告刻意保留原貌、不逐項回填。

## 1. Identify Scope

| Question | Answer |
| --- | --- |
| What feature is being evaluated? | 自動編製 Matters 周報／月報「草稿」的小工具（Python CLI） |
| Which repos are involved? | `dw-wq/matters-newsletter-bot`（獨立，不碰 matters-web / matters-server） |
| Which PRs or commits are included? | main 現行版本（讀寫端分離 + host 白名單已上線） |
| Is this web-only, server-only, or cross-system? | 都不是；是外部獨立工具，只打 Matters 公開 GraphQL API |
| Does it touch public domains, payments, moderation, federation, email, notifications, or account state? | 只可能觸及 notifications（@提及），且僅在「發佈」時；其餘皆否 |

## 2. Identify Environments

| Environment | URL / Value | Notes |
| --- | --- | --- |
| Preview web | N/A | 此工具是 CLI，無 Vercel 預覽 |
| Staging web | `https://matters.icu` | 草稿/發佈目的地（團隊檢視） |
| Staging GraphQL | `https://server.matters.icu/graphql` | `MATTERS_WRITE_ENDPOINT` 指這裡 |
| Production web | `https://matters.town` | 文章連結指向處；非寫入目標 |
| Production GraphQL | `https://server.matters.news/graphql` | **只匿名唯讀**抓熱門/置頂文（`MATTERS_READ_ENDPOINT`） |

## 3. Identify Test Accounts And Permissions

| Role | Needed? | Account / Owner | Notes |
| --- | --- | --- | --- |
| Logged-out visitor | Yes | 無需登入 | 讀正式站全程匿名 |
| Normal user | Yes | icu 測試帳戶（你持有） | 用來在 icu 開草稿/發佈 |
| Feature-flagged user | No | — | — |
| Admin / staff | No | — | — |
| Payment-capable test user | No | — | — |
| External platform account | No | — | — |

> 不在報告或 commit 內貼任何密碼／token。

## 4. Classify Risk

| Risk Area | Yes / No | Required Boundary |
| --- | --- | --- |
| Creates or edits user content | **Yes** | 目前只在 icu staging 開草稿；正式站發佈需人類批准 |
| Changes account state or permissions | No | — |
| Touches moderation or safety state | No | — |
| Touches payments or wallets | No | — |
| Sends external delivery | **部分** | @提及僅在「發佈」觸發；icu 發佈只會通知 icu 帳戶，正式站作者不受影響 |
| Changes public domain routing | No | — |
| Runs migrations or data repair | No | 僅 commit 自身 repo 的 `state/channel_pins.json`，與 Matters DB 無關 |

## 5. Choose Evaluation Profile

| Profile | 適用 | Production Allowed |
| --- | --- | --- |
| `mutation`（選定） | 在 icu staging 建立內容（草稿／發佈） | No by default（正式站發佈不在本次範圍） |

## 6. Required Evidence（本次收集狀態）

- Target web URL：`https://matters.icu`（待跑）
- Target API URL：`https://server.matters.icu/graphql`（待跑）
- Repo/commit under test：matters-newsletter-bot @ main ✓
- Commands run：weekly dry-run 已跑（見報告）✓
- Browser evidence：icu 草稿/發佈截圖（待跑）
- API evidence：讀正式站 346 篇、top10 已驗證 ✓
- IDs/URLs for staging test data：icu 文章 URL/ID（待跑）
- Blocker classification：見報告 Blockers
- Human approvals still needed：團隊對「用 AI agent 製作 + 在 icu 發佈」之同意

## 7. Final Gate（本次建議）

`Ready for staging acceptance` — 讀取側已驗證；待用 icu 測試帳戶實跑寫入側以補齊證據。
