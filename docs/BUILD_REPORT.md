# Theory Agent v1 建置與測試報告

建置日期：2026 年 9 月 13 日

## 本版範圍

本專案依《三套 AI Agent 工程開發規格書 v1.0》中「Agent 3 諮商理論技巧訓練 Agent」建置，並納入後續確認的四項需求：括弧非語言訊息、教師測試白名單、雙向跨次續談，以及學生選配逐字稿下載。另實作學生自備 Gemini API Key、Google Sheets 完整紀錄與可辨識學生 Email 的教師後台。

## 已完成檢查

- Python 全專案語法編譯通過。
- 專案完整性檢查通過。
- 11 學派數量正確。
- 每學派固定 5 項且技巧 ID 不重複。
- 每學派體驗模式固定 3 項技巧且皆屬該學派。
- 10 項自動化測試全部通過。
- Streamlit 首頁元件測試無例外。
- Streamlit 本機伺服器可啟動並回傳 HTTP 200。
- `secrets.toml.example` 可由 TOML 解析器正常讀取。
- 專案內容未出現實際 Gemini API Key 或已填入的 private key。

## 上線後仍須做的整合驗收

因本建置環境沒有你的 Gmail SMTP 應用程式密碼、Google 服務帳戶與學生 Gemini API Key，以下項目必須在 Streamlit Secrets 完成後以真實帳號驗收：

1. Gmail OTP 實際收信。
2. Google Sheets 九張工作表自動建立、寫入與教師讀取。
3. 學生 Gemini API Key 的真實模型呼叫、案例生成、對話、評量與續談摘要。
4. Streamlit Community Cloud 中的公開網址、重新部署及權限狀態。

完整操作順序見 `DEPLOYMENT_GUIDE.md` 與 `ACCEPTANCE_CHECKLIST.md`。
