#!/bin/bash

# L1 Advisory Layer - Docker构建脚本

echo "=========================================="
echo "L1 Advisory Layer - Docker 构建"
echo "=========================================="

# 检查Docker是否运行
if ! docker info > /dev/null 2>&1; then
    echo "❌ Error: Docker未运行，请先启动Docker Desktop"
    exit 1
fi

# 构建镜像
echo "📦 正在构建Docker镜像..."
docker compose -f docker-compose-l1.yml build

if [ $? -eq 0 ]; then
    echo "✅ Docker镜像构建成功！"
    echo ""
    echo "下一步："
    echo "  启动服务: ./docker-l1-run.sh"
    echo "  或使用: docker compose -f docker-compose-l1.yml up -d"
else
    echo "❌ Docker镜像构建失败"
    exit 1
fi
