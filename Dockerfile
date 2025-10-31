# 使用一個標準的 Python 官方映像作為基礎
FROM python:3.11-slim

# 【第一步：安裝我們的系統工具！】
# 在這裡，我們一次性地、強制地把 Opus 和 FFmpeg 安裝到最終的環境中
RUN apt-get update && apt-get install -y libopus0 ffmpeg

# 設定工作目錄
WORKDIR /app

# 複製我們的「函式庫清單」
COPY requirements.txt .

# 【第二步：安裝我們的 Python 函式庫】
RUN pip install --no-cache-dir -r requirements.txt

# 【第三步：複製我們所有的程式碼】
COPY . .

# 【第四步：設定最終的啟動指令】
CMD ["python", "main.py"]