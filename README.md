# 諮商理論技巧訓練 Agent v1

這是一套可部署於 Streamlit Community Cloud 的教學模擬系統。第一版專注於 11 個諮商學派的體驗與實作，並將登入、逐輪對話、續談、形成性回饋及教師研究後台整合在同一個應用程式中。

## 已實作功能

- 11 個固定學派，每學派固定 5 項技巧。
- 學派體驗模式：學生當個案，AI 當同一學派的示範諮商師；結束後才揭露技巧解析，不評分學生的個案表現。
- 學派實作模式：學生從 5 項技巧中選恰好 3 項；系統依技巧可用條件建立相容個案，學生當諮商師。
- 每次模擬先由內部「諮商計畫」引擎依學派方法擬定計畫與待蒐集資訊；對話中由「對話分析」引擎更新隱藏／未說完資訊；只有「聊天」引擎對學生說話。計畫與分析學生不可見。
- 對話與形成性評量分開呼叫 Gemini，晤談中不教答案、不說技巧名稱。
- 雙向續談：可延續同一位 AI 個案，也可延續同一位 AI 諮商師；續談會載入計畫與分析。
- 括弧非語言訊息，例如「（視線移開）」；原始文字完整保留。
- 白名單 Email + OTP 登入；教師可在後台新增或停用帳號。
- 學生自行輸入 Gemini API Key；Key 僅存於瀏覽器工作階段，不寫入 SQLite、逐字稿或研究資料。
- SQLite 後台：whitelist、身分對照、Sessions、ChatLogs、Threads（含 counseling_plan／chat_analysis）、Assessments、SkillEvents、TeacherGrades、Settings、RiskEvents。
- 教師可依學校 Email 查看學生次數、時間、學派、逐字稿、AI 回饋及另存人工成績。
- 學生可選擇下載當次 UTF-8 TXT 逐字稿。
- 教師可匯出全部後台資料為多份 CSV 的 ZIP。

## 專案結構

```text
theory-agent-v1/
├─ app.py
├─ requirements.txt
├─ README.md
├─ .gitignore
├─ .github/workflows/tests.yml
├─ .streamlit/
│  ├─ config.toml
│  └─ secrets.toml.example
├─ src/
│  ├─ auth.py
│  ├─ config.py
│  ├─ data_store.py
│  ├─ gemini_client.py
│  ├─ llm_pipeline.py
│  ├─ prompts.py
│  ├─ safety.py
│  ├─ session_service.py
│  ├─ theory_library.py
│  └─ transcript.py
├─ scripts/
│  ├─ check_project.py
│  ├─ seed_local_whitelist.py
│  └─ start_local.sh
├─ tests/
└─ docs/
   ├─ DEPLOYMENT_GUIDE.md
   ├─ GOOGLE_SHEETS_SETUP.md
   ├─ STUDENT_GUIDE.md
   ├─ RESEARCH_DATA_DICTIONARY.md
   ├─ ACCEPTANCE_CHECKLIST.md
   └─ BUILD_REPORT.md
```

## 本機測試

需要 Python 3.11 以上。最快本機啟動：

```bash
chmod +x scripts/start_local.sh
./scripts/start_local.sh
```

腳本會建立 `.venv`（若尚未有）、安裝套件、把 `poopoo1993@gmail.com` 寫入 SQLite 白名單（教師角色），並以 `local_demo_mode` 啟動；驗證碼會直接顯示在畫面上。

也可手動複製 `.streamlit/secrets.toml.example` 為 `.streamlit/secrets.toml` 後自行 `streamlit run app.py`。`secrets.toml` 已由 `.gitignore` 排除，禁止上傳 GitHub。

## 正式部署前必讀

1. 複製 `.streamlit/secrets.toml.example` 為 `.streamlit/secrets.toml`，填入 SMTP、教師 Email、白名單與 `participant_salt`。登入名單之後也可在教師後台維護。
2. 依 [部署操作手冊](docs/DEPLOYMENT_GUIDE.md) 上傳 GitHub 並設定 Streamlit Secrets（SQLite 路徑預設 `data/app.sqlite`）。
3. 依 [驗收清單](docs/ACCEPTANCE_CHECKLIST.md) 先用教師測試帳號跑完體驗、實作及續談。
4. 正式研究前先確認研究倫理、知情同意、資料保存期限、教師評分用途與學生退出機制。

## 安全界線

此系統是教學模擬器，不是心理治療或危機服務。關鍵字分流只能當介面安全防線，不能取代專業風險評估。AI 形成性分數也不是經過標準化驗證的測驗分數；教師人工評量另表保存，且不會覆寫 AI 原始輸出。

## 參考官方文件

- [Streamlit Community Cloud 部署](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app)
- [Streamlit Secrets 管理](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/secrets-management)
- [Gemini API Key 官方說明](https://ai.google.dev/gemini-api/docs/api-key)
- [GitHub 建立 repository](https://docs.github.com/en/repositories/creating-and-managing-repositories/creating-a-new-repository)
- [gspread 服務帳戶驗證](https://docs.gspread.org/en/latest/oauth2.html)
