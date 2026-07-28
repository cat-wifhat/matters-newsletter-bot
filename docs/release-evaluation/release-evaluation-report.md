# Release Evaluation Report — Matters Newsletter Bot

> 依 `thematters/matters-release-evaluation-agent` 的 release-evaluation-report 範本填寫。
> 讀取側證據為實跑結果；寫入側（icu）標記為 PENDING，待用 icu 測試帳戶補齊。
>
> ⚠️ **本報告為 2026-06-14 當時快照**，之後 bot 有多次變更（雙週報移除「置頂精選」欄與每日快照、
> 啟用自動發佈、改週三出刊等）。**最新狀態以 `CLAUDE.md` 與 `docs/自動化運維手冊.md` 為準**；
> 本歷史報告刻意保留原貌、不逐項回填。

## Summary

| Field | Value |
| --- | --- |
| Feature | Matters 周報／月報自動草稿工具（newsletter bot） |
| Date | 2026-06-14 |
| Evaluator | Release Evaluation Agent（Claude）＋ 人類維護者 |
| Recommendation | **Staging accepted（草稿路徑）** — 讀取＋icu 寫入已實測通過；待團隊決定是否在 icu 發佈 |
| Production approval | Not requested（正式站發佈不在本次範圍） |

## Scope

| Repo / PR | Commit / Branch | Status |
| --- | --- | --- |
| dw-wq/matters-newsletter-bot | main（讀寫端分離 + host 白名單） | 已上線、三個排程跑正式站（只開草稿） |

## Environment Matrix

| Environment | Web URL | GraphQL URL | Test profile | Mutation allowed | Result |
| --- | --- | --- | --- | --- | --- |
| Preview | N/A（CLI 工具，無預覽） | — | — | No | N/A |
| Staging | `https://matters.icu` | `https://server.matters.icu/graphql` | `mutation` | Yes, staging only | **PASS**（2026-06-14 登入成功、建立草稿 `Draft:70028`） |
| Production | `https://matters.town` | `https://server.matters.news/graphql` | 唯讀資料來源 | No（僅匿名讀取） | Read OK ✓ |

> 注意：本工具的「production」只作**匿名唯讀資料來源**，從不對正式站寫入。符合 SOP「production 預設唯讀」。

## Commands

| Command | Working Directory | Result | Notes |
| --- | --- | --- | --- |
| `python -m bot.digest --type weekly --dry-run` | newsletterbot | PASS | 讀正式站、組稿、不寫入 |
| `MATTERS_WRITE_ENDPOINT=…icu… python -m bot.digest --type weekly` | newsletterbot | PASS | 讀正式站→在 icu 建立草稿 `Draft:70028`（未發佈） |

## Automated Test Results

| Suite | Target | Result | Evidence |
| --- | --- | --- | --- |
| Unit | — | N/A | 專案無單元測試（極簡工具，依賴僅 requests） |
| Build | — | N/A | 純 Python，無建置步驟 |
| Read smoke（dry-run） | server.matters.news | PASS | 見下方 API Evidence |
| Staging mutation（建立草稿） | server.matters.icu | PASS | 登入成功 + `putDraft` 建立 `Draft:70028` |

## Browser Evidence

| Check | URL | Expected | Result | Evidence |
| --- | --- | --- | --- | --- |
| icu 草稿/發佈可見 | https://matters.icu | 團隊登入 icu 看得到成果 | PENDING | 待截圖 |

## API Evidence

| Check | Endpoint | Expected | Result | Evidence |
| --- | --- | --- | --- | --- |
| 匿名讀正式站熱門文 | server.matters.news | 抓到多頻道近 7 日文章 | PASS | `weekly: pooled 346 articles in 7d, picked top 10 (≤2/author)` |
| 組稿格式正確 | — | 含作者 @提及與 matters.town 連結 | PASS | 產出 2705 字 HTML，連結為 `https://matters.town/a/<hash>` |
| host 白名單擋未知 host | — | 非 .news/.town/.icu 直接中止 | PASS（先前驗證） | `validate_endpoints()` 會 SystemExit |
| icu 登入 + 開草稿 | server.matters.icu | 測試帳戶登入並 putDraft 成功 | PASS | `Logged in (type=Login)` + `created draft RHJhZnQ6NzAwMjg` |

## Feature Acceptance

| Gate | Expected | Result | Evidence |
| --- | --- | --- | --- |
| Permission: allowed user | icu 測試帳戶可建立內容 | PENDING | 待跑 |
| Permission: disallowed user | N/A（無角色分流） | N/A | — |
| Happy path | 讀正式站→在 icu 產出周報 | PASS（草稿） | 讀 346 篇→top10→icu 草稿 `Draft:70028` |
| Negative path | 打錯 host 立即中止 | PASS | host 白名單 |
| User-visible state | icu 上可見成果 | PENDING | 待截圖 |
| Data consistency | 連結/作者對應正確 | PASS（dry-run 核對） | 見 API Evidence |
| Rollback or cleanup | icu 為可丟棄測試資料；草稿/測試文可刪 | OK | icu 獨立沙盒 |

## Blockers

| Severity | Blocker | Owner | Required Action |
| --- | --- | --- | --- |
| 中 | bot 目前**只開草稿、不發佈**；但團隊要在 icu「看得到」需發佈 | 你 + 團隊 | 決定是否加「在 icu 發佈」一步（SOP 允許 staging mutation） |
| 低 | icu 寫入側證據未補 | 你 | 用 icu 測試帳戶實跑 weekly/monthly |
| 低 | 雲端跑需 secret + 切帳戶 | 你 | 加 `ICU_MATTERS_EMAIL/PASSWORD`，先 `gh auth switch -u dw-wq` |

## Human Approvals Needed

| Approval | Needed For | Status | Owner |
| --- | --- | --- | --- |
| 團隊同意 | 用 AI agent 製作的工具接入 icu、在 icu 發佈彙整內容 | Pending | 技術團隊 |
| Production mutation | 正式站（matters.town）發佈 | **不在本次範圍**；日後需明確批准 | 老闆/團隊 |
| Credentials / test account | icu 測試帳戶（你已持有） | Ready | 你 |
| Cloudflare / AWS / GitHub permission | 無 | N/A | — |

## Final Recommendation

**`Staging accepted, not production-approved`**（草稿路徑）

讀取側（匿名讀正式站、計分、組稿、host 白名單）與 icu 寫入側（登入、建立草稿 `Draft:70028`）皆已於 2026-06-14 實測通過。剩餘僅瀏覽器截圖證據（登入 matters.icu 草稿箱檢視）。正式站發佈刻意排除在本次評估之外，日後另需人類明確批准。

待團隊決定的下一步：是否要在 icu「發佈」（而非僅草稿），讓各自登入的成員都看得到——依 SOP 屬允許的 staging mutation。若團隊共用同一 icu 帳戶，草稿箱即可共見，連發佈都不需要。

Notes:

- 主要待決策：**草稿 vs 在 icu 發佈**。團隊要「看得到」需在 icu 發佈；依 SOP，用 icu 測試帳戶在 staging 發佈測試資料屬「明確允許」，不需 production 批准。
- 本工具與 matters-web 的 Playwright/E2E 流程無關，故 SOP 中 Preview/Playwright 段落不適用。
