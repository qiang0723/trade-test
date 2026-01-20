#!/bin/bash

# L1 Advisory Layer - Docker运行脚本

echo "=========================================="
echo "L1 Advisory Layer - Docker 启动"
echo "=========================================="

# 检查Docker是否运行
if ! docker info > /dev/null 2>&1; then
    echo "❌ Error: Docker未运行，请先启动Docker Desktop"
    exit 1
fi

# 检查镜像是否存在
if ! docker images | grep -q "trade-info-l1"; then
    echo "⚠️  镜像不存在，正在构建..."
    ./docker-l1-build.sh
    if [ $? -ne 0 ]; then
        exit 1
    fi
fi

# 停止旧容器（如果存在）
if docker ps -a | grep -q "l1-advisory-layer"; then
    echo "🛑 停止旧容器..."
    docker compose -f docker-compose-l1.yml down
fi

# 启动服务
echo "🚀 启动L1 Advisory Layer服务..."
docker compose -f docker-compose-l1.yml up -d

# 等待服务启动
echo "⏳ 等待服务启动..."
sleep 5

# 检查容器状态
if docker ps | grep -q "l1-advisory-layer"; then
    echo ""
    echo "=========================================="
    echo "✅ L1 Advisory Layer 服务启动成功！"
    echo "=========================================="
    echo ""
    echo "📊 服务信息："
    echo "  - 容器名称: l1-advisory-layer"
    echo "  - 访问地址: http://localhost:8001"
    echo "  - Web界面: http://localhost:8001/"
    echo "  - API文档: http://localhost:8001/api/l1/advisory/BTC"
    echo ""
    echo "📝 常用命令："
    echo "  查看日志: docker logs -f l1-advisory-layer"
    echo "  停止服务: docker compose -f docker-compose-l1.yml down"
    echo "  重启服务: docker compose -f docker-compose-l1.yml restart"
    echo "  查看状态: docker compose -f docker-compose-l1.yml ps"
    echo ""
    echo "🔧 数据持久化："
    echo "  数据库: ./data/db (已挂载)"
    echo "  配置文件: ./config (已挂载，支持热更新)"
    echo ""
else
    echo ""
    echo "❌ 服务启动失败！"
    echo ""
    echo "查看日志："
    echo "  docker logs l1-advisory-layer"
    echo ""
    exit 1
fi
