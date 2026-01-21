#!/bin/bash

# 快速启动脚本 - 避免权限卡顿
# 直接在终端运行，无需通过AI助手

set -e

echo "=================================="
echo "L1 Advisory Layer - 快速启动"
echo "=================================="
echo ""

# 检查Python
if ! command -v python3 &> /dev/null; then
    echo "❌ Python3 未安装"
    exit 1
fi

# 检查依赖
echo "1️⃣  检查Python依赖..."
python3 -c "import flask, yaml, binance" 2>/dev/null || {
    echo "⚠️  缺少依赖，正在安装..."
    pip3 install -r requirements.txt
}

# 检查配置文件
echo "2️⃣  检查配置文件..."
if [ ! -f "config/monitored_symbols.yaml" ]; then
    echo "❌ 配置文件缺失: config/monitored_symbols.yaml"
    exit 1
fi

# 创建必要目录
echo "3️⃣  准备数据目录..."
mkdir -p data/db logs

# 选择启动方式
echo ""
echo "请选择启动方式："
echo "  1) 直接启动 (前台运行，可看日志)"
echo "  2) Docker启动 (容器运行)"
echo ""
read -p "选择 [1/2]: " choice

case $choice in
    1)
        echo ""
        echo "🚀 启动L1 Web服务..."
        echo "访问地址: http://localhost:5001"
        echo "按 Ctrl+C 停止服务"
        echo ""
        python3 btc_web_app_l1.py
        ;;
    2)
        echo ""
        echo "🐳 使用Docker启动..."
        
        # 检查Docker
        if ! docker info > /dev/null 2>&1; then
            echo "❌ Docker未运行，请先启动Docker Desktop"
            exit 1
        fi
        
        # 停止旧容器
        docker compose -f docker-compose-l1.yml down 2>/dev/null || true
        
        # 构建并启动
        docker compose -f docker-compose-l1.yml up -d --build
        
        echo ""
        echo "✅ Docker服务启动成功！"
        echo "访问地址: http://localhost:8001"
        echo ""
        echo "常用命令:"
        echo "  查看日志: docker logs -f l1-advisory-layer"
        echo "  停止服务: docker compose -f docker-compose-l1.yml down"
        ;;
    *)
        echo "❌ 无效选择"
        exit 1
        ;;
esac
