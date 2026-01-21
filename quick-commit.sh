#!/bin/bash

# 快速Git提交脚本 - 避免权限卡顿
# 直接在终端运行，无需通过AI助手

set -e

echo "=================================="
echo "Git 快速提交"
echo "=================================="
echo ""

# 检查是否在Git仓库
if [ ! -d ".git" ]; then
    echo "❌ 不是Git仓库"
    exit 1
fi

# 显示当前状态
echo "📋 当前修改:"
git status --short

echo ""
read -p "是否继续提交? [y/N]: " confirm

if [[ ! $confirm =~ ^[Yy]$ ]]; then
    echo "❌ 已取消"
    exit 0
fi

# 输入提交信息
echo ""
read -p "提交信息 (默认: 'update'): " message
message=${message:-"update"}

# 执行提交
echo ""
echo "🔄 提交中..."
git add .
git commit -m "$message"

echo ""
read -p "是否推送到远程? [y/N]: " push_confirm

if [[ $push_confirm =~ ^[Yy]$ ]]; then
    echo "🚀 推送中..."
    git push
    echo "✅ 推送成功！"
else
    echo "✅ 已提交到本地"
    echo "手动推送: git push"
fi
