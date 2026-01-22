#!/bin/bash

# PR-DUAL 快速测试脚本
# 用途：快速验证双周期独立结论功能

echo "========================================="
echo "🧪 PR-DUAL 快速测试"
echo "========================================="
echo ""

# 1. 运行单元测试
echo "📋 步骤1: 运行单元测试..."
python3 tests/test_pr_dual_timeframe.py
if [ $? -ne 0 ]; then
    echo "❌ 单元测试失败"
    exit 1
fi
echo "✅ 单元测试通过"
echo ""

# 2. 检查配置文件
echo "📋 步骤2: 检查配置文件..."
if grep -q "dual_timeframe:" config/l1_thresholds.yaml; then
    echo "✅ 配置文件包含 dual_timeframe 配置"
else
    echo "❌ 配置文件缺少 dual_timeframe 配置"
    exit 1
fi
echo ""

# 3. 检查API端点（需要服务运行）
echo "📋 步骤3: 检查API端点..."
if curl -s http://localhost:8001/api/l1/advisory-dual/BTC > /dev/null 2>&1; then
    echo "✅ API端点可访问"
    echo ""
    echo "📊 API响应示例:"
    curl -s http://localhost:8001/api/l1/advisory-dual/BTC | python3 -m json.tool | head -30
else
    echo "⚠️  API端点不可访问（服务可能未启动）"
    echo "   提示: 运行 ./run_l1.sh 或 ./docker-l1-run.sh 启动服务"
fi
echo ""

# 4. 检查Web页面
echo "📋 步骤4: 检查Web页面..."
if [ -f "templates/index_l1_dual.html" ]; then
    echo "✅ 双周期UI页面存在"
    echo "   访问: http://localhost:8001/dual"
else
    echo "❌ 双周期UI页面不存在"
    exit 1
fi
echo ""

# 5. 检查文档
echo "📋 步骤5: 检查文档..."
if [ -f "doc/PR-DUAL_双周期独立结论.md" ]; then
    echo "✅ PR-DUAL文档存在"
else
    echo "⚠️  PR-DUAL文档不存在"
fi
echo ""

echo "========================================="
echo "✅ PR-DUAL 快速测试完成！"
echo "========================================="
echo ""
echo "📚 下一步:"
echo "  1. 启动服务: ./run_l1.sh"
echo "  2. 访问UI: http://localhost:8001/dual"
echo "  3. 测试API: curl http://localhost:8001/api/l1/advisory-dual/BTC"
echo "  4. 查看文档: cat doc/PR-DUAL_双周期独立结论.md"
echo ""
