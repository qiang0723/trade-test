#!/bin/bash

# 快速测试脚本
# 直接在终端运行，无需通过AI助手

set -e

echo "=================================="
echo "L1 测试套件"
echo "=================================="
echo ""

# 检查Python
if ! command -v python3 &> /dev/null; then
    echo "❌ Python3 未安装"
    exit 1
fi

# 选择测试范围
echo "请选择测试范围："
echo "  1) 所有测试"
echo "  2) P0 Bug修复测试"
echo "  3) 数据验证测试"
echo "  4) 单个测试文件"
echo ""
read -p "选择 [1-4]: " choice

case $choice in
    1)
        echo ""
        echo "🧪 运行所有测试..."
        python3 tests/run_all_tests.py
        ;;
    2)
        echo ""
        echo "🧪 运行P0测试..."
        python3 -m pytest tests/test_p0_*.py -v
        ;;
    3)
        echo ""
        echo "🧪 运行数据验证测试..."
        python3 -m pytest tests/test_data_validation_*.py -v
        ;;
    4)
        echo ""
        echo "可用测试文件:"
        ls -1 tests/test_*.py | nl
        echo ""
        read -p "输入文件编号: " num
        file=$(ls -1 tests/test_*.py | sed -n "${num}p")
        if [ -n "$file" ]; then
            echo ""
            echo "🧪 运行 $file..."
            python3 -m pytest "$file" -v
        else
            echo "❌ 无效编号"
            exit 1
        fi
        ;;
    *)
        echo "❌ 无效选择"
        exit 1
        ;;
esac
