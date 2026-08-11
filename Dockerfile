# 使用一個標準的 Python 官方映像作為基礎
FROM python:3.11-slim

ARG DENO_VERSION=2.9.4
ARG BGUTIL_VERSION=1.3.1
ARG TARGETARCH
ENV DENO_NO_UPDATE_CHECK=1 \
    DENO_NO_PROMPT=1 \
    PATH="/usr/local/bin:${PATH}"

# 【第一步：安裝系統工具】
# 直接在最終映像安裝 Deno，避免 Railway 多階段映像中找不到執行檔。
RUN apt-get update && apt-get install -y \
    libopus0 \
    ffmpeg \
    ca-certificates \
    curl \
    unzip \
    && case "${TARGETARCH:-$(uname -m)}" in \
        amd64|x86_64) deno_arch=x86_64 ;; \
        arm64|aarch64) deno_arch=aarch64 ;; \
        *) echo "Unsupported architecture: ${TARGETARCH:-$(uname -m)}" >&2; exit 1 ;; \
    esac \
    && deno_asset="deno-${deno_arch}-unknown-linux-gnu.zip" \
    && curl -fsSL \
        "https://github.com/denoland/deno/releases/download/v${DENO_VERSION}/${deno_asset}" \
        -o "/tmp/${deno_asset}" \
    && curl -fsSL \
        "https://github.com/denoland/deno/releases/download/v${DENO_VERSION}/${deno_asset}.sha256sum" \
        -o "/tmp/${deno_asset}.sha256sum" \
    && cd /tmp \
    && sha256sum -c "${deno_asset}.sha256sum" \
    && unzip -q "${deno_asset}" -d /usr/local/bin \
    && chmod 0755 /usr/local/bin/deno \
    && /usr/local/bin/deno --version \
    && rm -f "/tmp/${deno_asset}" "/tmp/${deno_asset}.sha256sum" \
    && rm -rf /var/lib/apt/lists/*

# Install the yt-dlp PO-token generator used for YouTube requests from
# datacenter IPs. The matching Python plugin is pinned in requirements.txt.
RUN mkdir -p /opt/bgutil-ytdlp-pot-provider \
    && curl -fsSL \
        "https://github.com/Brainicism/bgutil-ytdlp-pot-provider/archive/refs/tags/${BGUTIL_VERSION}.tar.gz" \
        -o /tmp/bgutil-ytdlp-pot-provider.tar.gz \
    && tar -xzf /tmp/bgutil-ytdlp-pot-provider.tar.gz \
        --strip-components=1 \
        -C /opt/bgutil-ytdlp-pot-provider \
    && cd /opt/bgutil-ytdlp-pot-provider/server \
    && deno install --allow-scripts=npm:canvas --frozen \
    && rm -f /tmp/bgutil-ytdlp-pot-provider.tar.gz

# 設定工作目錄
WORKDIR /app

# 複製「函式庫清單」
COPY requirements.txt .

# 【第二步：依 requirements 安裝 Python 函式庫】
# requirements 會一併安裝 Discord DAVE 與 yt-dlp 的 Deno/EJS 支援。
RUN pip install --no-cache-dir -r requirements.txt
RUN python -c "import importlib, yt_dlp, yt_dlp_ejs; importlib.import_module('yt_dlp_plugins.extractor.getpot_bgutil_script'); print(yt_dlp.version.__version__)" \
    && deno --version

# 【第三步：複製所有程式碼】
COPY . .

# 【第四步：啟動指令】
CMD ["python", "main.py"]
