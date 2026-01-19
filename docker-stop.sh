#!/bin/bash

# Docker容器停止脚本

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

CONTAINER_NAME="trade-info-app"

echo -e "${BLUE}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║                                                            ║${NC}"
echo -e "${BLUE}║         ${YELLOW}🛑 加密货币行情分析系统 - Docker停止${BLUE}            ║${NC}"
echo -e "${BLUE}║                                                            ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════════╝${NC}"
echo ""

# 检查容器是否在运行
if docker ps | grep -q ${CONTAINER_NAME}; then
    echo -e "${YELLOW}正在停止容器...${NC}"
    docker stop ${CONTAINER_NAME}
    
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✅ 容器已停止${NC}"
        
        # 询问是否删除容器
        echo ""
        echo -e "${YELLOW}是否删除容器? (y/n)${NC}"
        read -r delete_choice
        
        if [[ "$delete_choice" == "y" || "$delete_choice" == "Y" ]]; then
            docker rm ${CONTAINER_NAME}
            echo -e "${GREEN}✅ 容器已删除${NC}"
        else
            echo -e "${BLUE}💡 容器已停止但未删除，可以使用以下命令重新启动:${NC}"
            echo -e "   ${YELLOW}docker start ${CONTAINER_NAME}${NC}"
        fi
    else
        echo -e "${RED}❌ 停止容器失败${NC}"
    fi
else
    echo -e "${YELLOW}⚠️  容器未运行${NC}"
fi
