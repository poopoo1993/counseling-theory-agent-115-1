# Google Sheets 後台設定

本系統以一份 Google 試算表保存教學與研究資料。程式第一次連線時會自動建立各工作表，因此你只需要先建立空白試算表、服務帳戶及金鑰，並完成分享權限。

## 一 建立空白試算表

1. 以你的 Google 帳號建立一份空白 Google 試算表。
2. 建議命名為 `115-1_諮商理論Agent_研究資料`。
3. 從網址複製 Spreadsheet ID。格式為：

   `https://docs.google.com/spreadsheets/d/這一段就是ID/edit`

4. 不需要手動建立工作表標籤，也不要自行修改程式建立的第一列欄名。

## 二 建立服務帳戶及 JSON 金鑰

1. 進入 [Google Cloud Console](https://console.cloud.google.com/)。
2. 選擇或建立專案。
3. 啟用 Google Sheets API 與 Google Drive API。
4. 到 IAM 與管理 → 服務帳戶，建立服務帳戶。
5. 進入該服務帳戶 → Keys → Add key → Create new key → JSON。
6. 下載 JSON 檔並妥善保管，不可上傳 GitHub、寄給學生或貼在公開對話中。

可參考 [Google Cloud 建立服務帳戶](https://cloud.google.com/iam/docs/service-accounts-create) 與 [建立服務帳戶金鑰](https://cloud.google.com/iam/docs/keys-create-delete)。

## 三 把試算表分享給服務帳戶

1. 打開下載的 JSON，找到 `client_email`，格式通常像 `名稱@專案.iam.gserviceaccount.com`。
2. 回到 Google 試算表，按右上角「共用」。
3. 貼上這個 `client_email`。
4. 權限設為「編輯者」。
5. 完成共用。

如果沒有分享，程式即使拿到正確 JSON 金鑰也無法開啟試算表。gspread 的服務帳戶驗證文件也要求將目標試算表分享給服務帳戶 Email。[官方文件](https://docs.gspread.org/en/latest/oauth2.html)

## 四 填入 Streamlit Secrets

將完整服務帳戶 JSON 原封不動放入 `GOOGLE_SERVICE_ACCOUNT_JSON`，並將試算表 ID 放在 Secrets 最上方：

```toml
SPREADSHEET_ID = "你的Spreadsheet ID"
REQUIRE_SHEETS = true
GOOGLE_SERVICE_ACCOUNT_JSON = '''
{
  "type": "service_account",
  "project_id": "原始JSON內容",
  "private_key_id": "原始JSON內容",
  "private_key": "-----BEGIN PRIVATE KEY-----\\n原始完整內容\\n-----END PRIVATE KEY-----\\n",
  "client_email": "原始JSON內容",
  "client_id": "原始JSON內容",
  "auth_uri": "https://accounts.google.com/o/oauth2/auth",
  "token_uri": "https://oauth2.googleapis.com/token",
  "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
  "client_x509_cert_url": "原始JSON內容",
  "universe_domain": "googleapis.com"
}
'''
```

三個設定必須放在任何 `[app]`、`[email]` 等 section 之前。JSON 內容不可保留範例文字，也不可提交至 GitHub。

## 五 權限與研究資料建議

- 試算表只分享給授課教師與必要研究人員。
- IdentityMap 含學校 Email，應與匿名研究表分離管理；研究匯出後可移除 IdentityMap。
- 不要手動覆寫 ChatLogs 的 `content_raw` 或 Assessments 的 `raw_model_output`。
- 若需重新評分，應新增新的 assessment 版本，而不是改掉原始結果。
- 定期下載備份，並依研究倫理核准內容設定保存期限與刪除程序。
