#!/bin/bash

# Docker镜像构建脚本

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 镜像信息
IMAGE_NAME="trade-info"
IMAGE_TAG="latest"
IMAGE_FULL="${IMAGE_NAME}:${IMAGE_TAG}"

echo -e "${BLUE}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║                                                            ║${NC}"
echo -e "${BLUE}║         ${GREEN}🐳 加密货币行情分析系统 - Docker构建${BLUE}            ║${NC}"
echo -e "${BLUE}║                                                            ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════════╝${NC}"
echo ""

# 检查Docker是否安装
if ! command -v docker &> /dev/null; then
    echo -e "${RED}❌ Docker未安装，请先安装Docker${NC}"
    echo "访问: https://www.docker.com/get-started"
    exit 1
fi

echo -e "${GREEN}✅ Docker已安装${NC}"
echo ""

# 显示当前Docker版本
echo -e "${YELLOW}📦 Docker版本信息:${NC}"
docker --version
echo ""

# 开始构建
echo -e "${YELLOW}🔨 开始构建Docker镜像...${NC}"
echo -e "${BLUE}镜像名称: ${IMAGE_FULL}${NC}"
echo ""

# 构建镜像
if docker build -t ${IMAGE_FULL} .; then
    echo ""
    echo -e "${GREEN}✅ Docker镜像构建成功！${NC}"
    echo ""
    
    # 显示镜像信息
    echo -e "${YELLOW}📊 镜像信息:${NC}"
    docker images ${IMAGE_NAME}
    echo ""
    
    # 获取镜像大小
    IMAGE_SIZE=$(docker images ${IMAGE_FULL} --format "{{.Size}}")
    echo -e "${GREEN}📦 镜像大小: ${IMAGE_SIZE}${NC}"
    echo ""
    
    # 保存镜像到文件
    echo -e "${YELLOW}💾 是否要将镜像保存为tar文件? (y/n)${NC}"
    read -r save_choice
    
    if [[ "$save_choice" == "y" || "$save_choice" == "Y" ]]; then
        TAR_FILE="${IMAGE_NAME}_${IMAGE_TAG}.tar"
        echo -e "${YELLOW}正在保存镜像到 ${TAR_FILE}...${NC}"
        
        if docker save -o ${TAR_FILE} ${IMAGE_FULL}; then
            echo -e "${GREEN}✅ 镜像已保存到: ${TAR_FILE}${NC}"
            ls -lh ${TAR_FILE}
            echo ""
            echo -e "${BLUE}💡 可以使用以下命令在其他机器上加载镜像:${NC}"
            echo -e "${YELLOW}   docker load -i ${TAR_FILE}${NC}"
        else
            echo -e "${RED}❌ 保存镜像失败${NC}"
        fi
    fi
    
    echo ""
    echo -e "${GREEN}════════════════════════════════════════════════════════════${NC}"
    echo -e "${GREEN}✅ 构建完成！${NC}"
    echo -e "${GREEN}════════════════════════════════════════════════════════════${NC}"
    echo ""
    echo -e "${YELLOW}🚀 运行容器的方法:${NC}"
    echo ""
    echo -e "${BLUE}方法1: 使用docker run${NC}"
    echo -e "  docker run -d -p 5001:5001 --name trade-info ${IMAGE_FULL}"
    echo ""
    echo -e "${BLUE}方法2: 使用docker-compose${NC}"
    echo -e "  docker-compose up -d"
    echo ""
    echo -e "${BLUE}方法3: 使用运行脚本${NC}"
    echo -e "  ./docker-run.sh"
    echo ""
    echo -e "${YELLOW}📡 访问地址: ${GREEN}http://localhost:5001${NC}"
    echo ""
    
else
    echo ""
    echo -e "${RED}❌ Docker镜像构建失败！${NC}"
    exit 1
fi
