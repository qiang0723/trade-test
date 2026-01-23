#!/bin/bash

echo "=========================================="
echo "🧹 开始清理临时文档..."
echo "=========================================="

BACKUP_DIR="backup_temp_docs_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$BACKUP_DIR"

FILES=(
    "ARCHITECTURE_OPTIMIZATION_SUMMARY.md"
    "OPTIMIZATION_COMPLETED.md"
    "PROJECT_STATUS.md"
    "PROJECT_STRUCTURE.txt"
    "QUICK_START_MODULAR.md"
    "README_ARCHITECTURE.md"
    "REFACTORING_REPORT.md"
    "今日完成清单.md"
    "今日成果总览.txt"
    "优化完成总结.md"
    "架构优化成果展示.md"
)

deleted=0
for file in "${FILES[@]}"; do
    if [ -f "$file" ]; then
        cp "$file" "$BACKUP_DIR/" && rm "$file"
        echo "✅ 已删除: $file"
        ((deleted++))
    fi
done

echo ""
echo "=========================================="
echo "✅ 清理完成！"
echo "=========================================="
echo "📦 备份目录: $BACKUP_DIR"
echo "📊 已删除: $deleted 个临时文档"
echo ""
echo "⚠️  保留的文件："
echo "  ✅ 所有代码文件（Docker正在使用）"
echo "  ✅ 核心规范文档"
echo "  ✅ P0改进文档"
echo ""

