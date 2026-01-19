#!/bin/bash

# BTC行情数据获取工具 - 快速启动脚本

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 项目目录
PROJECT_DIR="/Users/wangqiang/learning/trade-info"

# 切换到项目目录
cd "$PROJECT_DIR" || exit 1

# 检查虚拟环境是否存在
if [ ! -d "venv" ]; then
    echo -e "${RED}❌ 虚拟环境不存在！${NC}"
    echo -e "${YELLOW}正在创建虚拟环境...${NC}"
    python3 -m venv venv
    echo -e "${GREEN}✅ 虚拟环境创建成功${NC}"
fi

# 激活虚拟环境
source venv/bin/activate

# 检查依赖是否安装
if ! python3 -c "import binance" 2>/dev/null; then
    echo -e "${RED}❌ 依赖包未安装！${NC}"
    echo -e "${YELLOW}正在安装依赖包...${NC}"
    pip install -r requirements.txt
    echo -e "${GREEN}✅ 依赖包安装完成${NC}"
fi

# 显示菜单
clear
echo -e "${BLUE}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║                                                            ║${NC}"
echo -e "${BLUE}║         ${GREEN}🌟 BTC行情数据获取工具 🌟${BLUE}                     ║${NC}"
echo -e "${BLUE}║                                                            ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${YELLOW}请选择要运行的脚本：${NC}"
echo ""
echo -e "  ${GREEN}1${NC}. 快速查看行情 (btc_market_simple.py)"
echo -e "     ${BLUE}→${NC} 在终端直接显示BTC行情数据"
echo ""
echo -e "  ${GREEN}2${NC}. 导出数据文件 (btc_market_export.py)"
echo -e "     ${BLUE}→${NC} 保存为JSON和CSV文件，可用Excel打开"
echo ""
echo -e "  ${GREEN}3${NC}. 多币种对比 (btc_market_multi_symbols.py)"
echo -e "     ${BLUE}→${NC} 同时查看15个币种的行情和涨跌幅"
echo ""
echo -e "  ${GREEN}4${NC}. 交互式查询 (btc_market_data.py)"
echo -e "     ${BLUE}→${NC} 菜单式选择，可自定义参数"
echo ""
echo -e "  ${GREEN}5${NC}. 启动Web应用 (btc_web_app.py) ⭐"
echo -e "     ${BLUE}→${NC} 在浏览器中查看实时行情（推荐）"
echo ""
echo -e "  ${GREEN}0${NC}. 退出"
echo ""
echo -ne "${YELLOW}请输入选项 (0-5): ${NC}"
read -r choice

case $choice in
    1)
        echo -e "\n${GREEN}正在运行: btc_market_simple.py${NC}\n"
        python3 btc_market_simple.py
        ;;
    2)
        echo -e "\n${GREEN}正在运行: btc_market_export.py${NC}\n"
        python3 btc_market_export.py
        ;;
    3)
        echo -e "\n${GREEN}正在运行: btc_market_multi_symbols.py${NC}\n"
        python3 btc_market_multi_symbols.py
        ;;
    4)
        echo -e "\n${GREEN}正在运行: btc_market_data.py${NC}\n"
        python3 btc_market_data.py
        ;;
    5)
        echo -e "\n${GREEN}正在启动Web应用...${NC}\n"
        echo -e "${YELLOW}服务启动后，请在浏览器中访问:${NC}"
        echo -e "${BLUE}http://localhost:5000${NC}"
        echo ""
        echo -e "${YELLOW}按 Ctrl+C 停止服务${NC}\n"
        python3 btc_web_app.py
        ;;
    0)
        echo -e "\n${BLUE}再见！👋${NC}\n"
        exit 0
        ;;
    *)
        echo -e "\n${RED}❌ 无效选项！${NC}\n"
        exit 1
        ;;
esac

echo ""
echo -e "${GREEN}✅ 程序执行完成${NC}"
echo ""
