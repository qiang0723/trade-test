#!/bin/bash

# L1 Advisory Layer - Docker停止脚本

echo "=========================================="
echo "L1 Advisory Layer - Docker 停止"
echo "=========================================="

# 停止并移除容器
docker compose -f docker-compose-l1.yml down

if [ $? -eq 0 ]; then
    echo "✅ L1 Advisory Layer 服务已停止"
    echo ""
    echo "💾 数据已保存在:"
    echo "  - ./data/db (数据库)"
    echo "  - ./config (配置文件)"
    echo ""
else
    echo "❌ 停止服务失败"
    exit 1
fi
