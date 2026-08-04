# 月影狼蹤 Activity Frontend

獨立的 Discord 視覺化狼人殺前端，只包含狼人殺遊戲，不會載入原專案的音樂、AI 或傳統 Bot 功能。

## 本機開發

1. 啟動 `activity_backend`（預設 `http://127.0.0.1:8000`）。
2. 將 `.dev.vars.example` 複製為 `.dev.vars`。
3. 執行 `npm install`，再執行 `npm run dev`。
4. 在 Discord Developer Portal 將 Activity URL Mapping 指向本機 tunnel。

## 驗證

```text
npm run lint
npm test
```

正式環境由 Sites Worker 將同源的 `/api/*` 與 `/ws/*` 請求轉送到獨立的 Python 後端；`API_ORIGIN` 只存於部署環境，不寫入原始碼。
