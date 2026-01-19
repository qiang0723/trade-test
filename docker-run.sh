#!/bin/bash

# Docker容器运行脚本

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 容器信息
CONTAINER_NAME="trade-info-app"
IMAGE_NAME="trade-info:latest"
PORT="5001"

echo -e "${BLUE}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║                                                            ║${NC}"
echo -e "${BLUE}║         ${GREEN}🚀 加密货币行情分析系统 - Docker运行${BLUE}            ║${NC}"
echo -e "${BLUE}║                                                            ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════════╝${NC}"
echo ""

# 检查镜像是否存在
if ! docker images ${IMAGE_NAME} | grep -q trade-info; then
    echo -e "${RED}❌ 镜像不存在，请先构建镜像${NC}"
    echo -e "${YELLOW}运行: ./docker-build.sh${NC}"
    exit 1
fi

# 检查容器是否已经运行
if docker ps | grep -q ${CONTAINER_NAME}; then
    echo -e "${YELLOW}⚠️  容器已在运行中${NC}"
    echo -e "${YELLOW}是否要重启容器? (y/n)${NC}"
    read -r restart_choice
    
    if [[ "$restart_choice" == "y" || "$restart_choice" == "Y" ]]; then
        echo -e "${YELLOW}正在停止容器...${NC}"
        docker stop ${CONTAINER_NAME}
        echo -e "${YELLOW}正在删除容器...${NC}"
        docker rm ${CONTAINER_NAME}
    else
        echo -e "${GREEN}✅ 容器继续运行${NC}"
        echo -e "${YELLOW}📡 访问地址: ${GREEN}http://localhost:${PORT}${NC}"
        exit 0
    fi
fi

# 检查是否有停止的容器
if docker ps -a | grep -q ${CONTAINER_NAME}; then
    echo -e "${YELLOW}正在删除旧容器...${NC}"
    docker rm ${CONTAINER_NAME}
fi

# 运行容器
echo -e "${YELLOW}🚀 正在启动容器...${NC}"
echo ""

docker run -d \
    --name ${CONTAINER_NAME} \
    -p ${PORT}:${PORT} \
    -v "$(pwd)/btc_market_data:/app/btc_market_data" \
    -e TZ=Asia/Shanghai \
    --restart unless-stopped \
    ${IMAGE_NAME}

# 检查是否启动成功
if [ $? -eq 0 ]; then
    echo ""
    echo -e "${GREEN}✅ 容器启动成功！${NC}"
    echo ""
    
    # 等待容器完全启动
    echo -e "${YELLOW}等待服务启动...${NC}"
    sleep 5
    
    # 显示容器状态
    echo -e "${YELLOW}📊 容器状态:${NC}"
    docker ps | grep ${CONTAINER_NAME}
    echo ""
    
    # 显示容器日志（最后10行）
    echo -e "${YELLOW}📝 容器日志:${NC}"
    docker logs --tail 10 ${CONTAINER_NAME}
    echo ""
    
    echo -e "${GREEN}════════════════════════════════════════════════════════════${NC}"
    echo -e "${GREEN}✅ 服务已启动！${NC}"
    echo -e "${GREEN}════════════════════════════════════════════════════════════${NC}"
    echo ""
    echo -e "${YELLOW}📡 访问地址:${NC}"
    echo -e "   ${GREEN}http://localhost:${PORT}${NC}"
    echo -e "   ${GREEN}http://127.0.0.1:${PORT}${NC}"
    echo ""
    echo -e "${YELLOW}🔧 常用命令:${NC}"
    echo -e "   查看日志: ${BLUE}docker logs -f ${CONTAINER_NAME}${NC}"
    echo -e "   停止容器: ${BLUE}docker stop ${CONTAINER_NAME}${NC}"
    echo -e "   启动容器: ${BLUE}docker start ${CONTAINER_NAME}${NC}"
    echo -e "   重启容器: ${BLUE}docker restart ${CONTAINER_NAME}${NC}"
    echo -e "   删除容器: ${BLUE}docker rm -f ${CONTAINER_NAME}${NC}"
    echo ""
else
    echo ""
    echo -e "${RED}❌ 容器启动失败！${NC}"
    exit 1
fi
