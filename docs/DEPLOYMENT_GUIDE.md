# GitHub 與 Streamlit 部署操作手冊

本手冊適用於第一次以 GitHub 網頁介面部署本專案。請先完成 Google Sheets 與 Gmail OTP 設定，再把 Secrets 貼到 Streamlit；任何密碼、私鑰或 API Key 都不可上傳 GitHub。

## 一 部署前準備

你需要：

1. GitHub 帳號。
2. Streamlit Community Cloud 帳號，並授權讀取要部署的 GitHub repository。
3. 一份空白 Google 試算表。
4. 已建立金鑰的 Google Cloud 服務帳戶，且試算表已分享給該服務帳戶 Email。
5. 可透過 SMTP 寄信的 Gmail 及 Gmail 應用程式密碼。
6. 完整的 `.streamlit/secrets.toml` 內容。可從專案的 `secrets.toml.example` 複製後填寫。

Streamlit 官方明確建議 Secrets 不要放在 Git repository，而應在部署時貼入 Advanced settings 的 Secrets 欄位。[官方說明](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/secrets-management)

## 二 建立 GitHub repository

1. 登入 [GitHub](https://github.com)。
2. 右上角按 `＋`，選 `New repository`。
3. Repository name 建議填：`counseling-theory-agent-115-1`。
4. Description 可填：`115-1 諮商理論技巧訓練 Agent`。
5. 測試期可選 `Private`；若日後希望公開程式碼，再另外修改 visibility。
6. 不要勾選自動新增 README、`.gitignore` 或 License，因為壓縮檔內已經有 README 與 `.gitignore`。
7. 按 `Create repository`。

GitHub 官方指出，匯入既有專案時不要先建立 README 等檔案，以免產生合併衝突。[官方說明](https://docs.github.com/en/repositories/creating-and-managing-repositories/creating-a-new-repository)

## 三 解壓縮並上傳所有檔案

1. 在 Windows 對下載的 ZIP 按右鍵，選「解壓縮全部」。
2. 打開解壓後的 `theory-agent-v1` 資料夾。
3. 回到新建的 GitHub repository 頁面。
4. 按 `uploading an existing file`；若已進入一般檔案頁，按 `Add file` → `Upload files`。
5. 將 `theory-agent-v1` 資料夾內的所有檔案與子資料夾一起拖入上傳區。
6. 確認 GitHub 最上層直接看得到 `app.py`、`requirements.txt`、`src`、`docs`、`.streamlit`；不要多包一層資料夾。
7. Commit message 填：`Initial Theory Agent v1`。
8. 按 `Commit changes`。

請確認 GitHub 上沒有 `.streamlit/secrets.toml`，只可以有 `.streamlit/secrets.toml.example`。GitHub 官方也警告不要 commit 或 push 密碼與 API Key。[官方說明](https://docs.github.com/en/repositories/working-with-files/managing-files/adding-a-file-to-a-repository)

## 四 建立 Streamlit App

1. 開啟 [Streamlit Community Cloud](https://share.streamlit.io/)。
2. 使用與 GitHub 連結的帳號登入。
3. 按右上角 `Create app`。
4. 選 `Yup, I have an app` 或相當的「從現有 repository 部署」選項。
5. Repository 選剛建立的 `counseling-theory-agent-115-1`。
6. Branch 選 `main`。
7. Main file path 填：`app.py`。
8. App URL 可自訂，例如 `counseling-theory-agent-115-1`。
9. 尚未按 Deploy，先進入 `Advanced settings`。

Streamlit 官方目前的流程是從 workspace 按 `Create app`，填入 repository 與入口檔後部署。[官方說明](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app)

## 五 貼入 Secrets

1. 在本機開啟 `.streamlit/secrets.toml.example`。
2. 複製內容到一個不會上傳 GitHub 的暫存文字檔。
3. 逐項替換：
   - `participant_salt`：至少 32 字元的隨機字串。
   - `sender_email`：寄送 OTP 的 Gmail。
   - `app_password`：該 Gmail 的應用程式密碼，不是一般登入密碼。
   - `spreadsheet_id`：Google 試算表網址中 `/d/` 與 `/edit` 之間的字串。
   - `[google_sheets.service_account]`：服務帳戶 JSON 中對應欄位。
4. `login_allowlist` 與 `teacher_emails` 保留 `ryanhsiao89@gmail.com`。
5. 將填好的完整 TOML 貼到 Streamlit `Advanced settings` → `Secrets`。
6. 按 `Save`，再按 `Deploy`。

私鑰必須保留 BEGIN／END 行與完整內容；不要刪除三引號。部署後如需修改，可由 App settings 更新 Secrets。[Streamlit Secrets 官方說明](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/secrets-management)

## 六 第一次啟動檢查

第一次啟動時，程式會在試算表中自動建立：

- IdentityMap
- Sessions
- ChatLogs
- Threads
- Assessments
- SkillEvents
- TeacherGrades
- Settings
- RiskEvents

若畫面顯示「本機暫存模式」，代表 Google Sheets 連線失敗。最常見原因是：

1. spreadsheet_id 貼錯。
2. 服務帳戶 private_key 換行格式破損。
3. 尚未把試算表分享給服務帳戶 `client_email`。
4. Google Sheets API 或 Google Drive API 尚未啟用。

## 七 正式驗收順序

1. 用 `ryanhsiao89@gmail.com` 收 OTP 並登入。
2. 切到學生模擬端，貼入你自己的 Gemini API Key 並測試。
3. 跑一次「學派體驗」，確認結束後無學生分數、只有 AI 技巧解析。
4. 跑一次「學派實作」，選恰好 3 技巧，確認形成性分數、具體優點、替代句及逐字稿下載。
5. 回首頁選「續談上次歷程」，分別確認 AI 個案及 AI 諮商師能接續。
6. 切到教師後台，確認能以 Email 找到 Session、逐字稿、AI 回饋與人工評量欄位。
7. 打開 Google Sheets，確認原始逐輪 `content_raw`、時間、學派、技巧、prompt_version 與 model_name 都有保存。

## 八 之後更新程式

修改 GitHub `main` 分支後，Streamlit 通常會自動重新部署。若更新涉及 Secrets，請到 Streamlit App settings 修改，不要把 Secrets 放進 GitHub。
