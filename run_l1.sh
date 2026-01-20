#!/bin/bash

# L1 Advisory Layer - 快速启动脚本

echo "========================================"
echo "L1 Advisory Layer - Starting"
echo "========================================"
echo ""

# 检查虚拟环境
if [ ! -d "venv" ]; then
    echo "❌ Virtual environment not found!"
    echo "Please run: python3 -m venv venv"
    exit 1
fi

# 激活虚拟环境
echo "📦 Activating virtual environment..."
source venv/bin/activate

# 检查依赖
echo "🔍 Checking dependencies..."
pip install -q flask flask-cors pyyaml 2>/dev/null

# 创建必要的目录
echo "📁 Creating directories..."
mkdir -p data/db
mkdir -p config
mkdir -p tests

# 检查配置文件
if [ ! -f "config/l1_thresholds.yaml" ]; then
    echo "⚠️  Config file not found, will use default thresholds"
fi

# 启动Flask应用
echo ""
echo "========================================"
echo "🚀 Starting L1 Advisory Service"
echo "========================================"
echo "Service URL: http://localhost:5001"
echo "Web UI: http://localhost:5001/"
echo "API Doc: http://localhost:5001/api/l1/advisory/BTC"
echo ""
echo "Press Ctrl+C to stop"
echo "========================================"
echo ""

# 运行
python btc_web_app_l1.py
