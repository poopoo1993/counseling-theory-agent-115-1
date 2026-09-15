# 研究資料表與欄位說明

Google Sheets 由程式自動建立九張工作表。原始對話與原始模型輸出採新增保存；教師人工評量另表儲存，不覆寫 AI 結果。

## IdentityMap

| 欄位 | 說明 |
| --- | --- |
| participant_id | 由私密 salt 與 Email 產生的匿名代碼 |
| email | 學校登入 Email；教師可據此辨識學生 |
| created_at | 首次建立時間 |
| last_login_at | 最近登入時間 |
| role | student 或 teacher |

正式去識別化研究資料應移除或另存 IdentityMap。

## Sessions

保存 session_id、conversation_thread_id、participant_id、mode、AI 續談角色、起訖時間、使用秒數、case_id、school_id、預選技巧、模型與 prompt 版本、temperature、完成狀態、主題、難度，以及體驗模式結束時的 `research_consent`（`yes`／`no`；實作模式為空）。若學生不同意作為研究素材，該 Session 的 ChatLogs 會被刪除。

## ChatLogs

每一輪一列，包含 turn_index、speaker_role、原始 `content_raw`、括弧非語言訊息、時間、延遲及錯誤狀態。`content_raw` 不可由後續重新評量覆寫。體驗模式若學生不同意作為研究素材，該 Session 的 ChatLogs 會整批刪除。

## Threads

保存跨次續談關係。`continuation_role` 為 `ai_client` 或 `ai_counselor`；另保存同一學派、同一角色設定、最新結構化快照、前次最後六輪原始對話、尚未完成議題及最近 Session。

## Assessments

保存 rubric_version、探索性分數、各向度分數、技巧事件、具體優點、改善點、替代句、下次任務、鼓勵文字、`raw_model_output` 與 `parsed_json`。體驗模式不評學生分數。

## SkillEvents

每一技巧事件一列。狀態可為 `used`、`missed_opportunity`、`no_opportunity` 或 `extension_skill`；並保存出現輪次、品質、原句證據及個案反應。

## TeacherGrades

教師人工分數與評語。每次另新增一列，保留教師 Email 與時間，不會覆寫 Assessments。

## Settings

教師可設定系統開關、開放日期、每人 Session 上限、可用模式、學生是否看回饋及是否看 AI 分數。

## RiskEvents

記錄介面偵測到明確立即安全語言後的停止動作。這是介面分流紀錄，不可當作診斷或完整風險評估資料。

## 分析注意事項

- AI 分數尚未經專家一致性、評分者間信度及效標關聯驗證前，不應直接等同標準化測驗或唯一學期成績。
- `model_name`、`prompt_version`、`rubric_version` 應納入資料版本控制。
- 對話具有同一學生與同一 thread 的巢套性；成長軌跡分析不宜把所有 Session 當成完全獨立觀察值。
- 重新評分應新增 assessment_id 與 rubric_version，保留原始輸出。
