# 使用一個標準的 Python 官方映像作為基礎
FROM python:3.11-slim

# 【第一步：安裝系統工具】
# 增加 ca-certificates 確保 HTTPS 連線正常
RUN apt-get update && apt-get install -y \
    libopus0 \
    ffmpeg \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# 設定工作目錄
WORKDIR /app

# 複製「函式庫清單」
COPY requirements.txt .

# 【第二步：依 requirements 安裝 Python 函式庫】
# requirements 會一併安裝 Discord DAVE 與 yt-dlp 的 Deno/EJS 支援。
RUN pip install --no-cache-dir -r requirements.txt

# 【第三步：複製所有程式碼】
COPY . .

# 【第四步：啟動指令】
CMD ["python", "main.py"]
