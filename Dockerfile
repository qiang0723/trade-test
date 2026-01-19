# 使用Python 3.12官方镜像作为基础镜像
FROM python:3.12-slim

# 设置工作目录
WORKDIR /app

# 设置环境变量
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# 安装系统依赖
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# 复制requirements.txt并安装Python依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制项目文件
COPY btc_web_app_multi.py .
COPY btc_market_simple.py .
COPY btc_market_data.py .
COPY btc_market_export.py .
COPY btc_market_multi_symbols.py .
COPY btc_web_app.py .
COPY database.py .
COPY static/ ./static/
COPY templates/ ./templates/

# 创建数据目录
RUN mkdir -p btc_market_data

# 暴露端口
EXPOSE 5001

# 设置健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:5001/api/markets', timeout=5)"

# 启动应用
CMD ["python", "btc_web_app_multi.py"]
