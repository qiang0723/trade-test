#!/bin/bash
# AWS服务器快速连接脚本

# 获取当前脚本所在目录
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
KEY_FILE="$SCRIPT_DIR/../john-test.pem"
SERVER="ubuntu@43.212.176.169"

# 颜色定义
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${BLUE}===========================================${NC}"
echo -e "${GREEN}  AWS Trade-Info L1 服务器连接${NC}"
echo -e "${BLUE}===========================================${NC}"
echo ""
echo -e "服务器: ${YELLOW}43.212.176.169${NC}"
echo -e "用户: ${YELLOW}ubuntu${NC}"
echo -e "工作目录: ${YELLOW}/home/ubuntu/trade-info-l1${NC}"
echo ""

# 检查密钥文件
if [ ! -f "$KEY_FILE" ]; then
    echo -e "${YELLOW}⚠️  密钥文件不存在: $KEY_FILE${NC}"
    exit 1
fi

# 根据参数执行不同操作
case "${1:-shell}" in
    shell|ssh)
        echo -e "${GREEN}🔗 正在连接到服务器...${NC}"
        ssh -i "$KEY_FILE" "$SERVER"
        ;;
    
    logs)
        echo -e "${GREEN}📜 查看服务日志...${NC}"
        ssh -i "$KEY_FILE" "$SERVER" "docker logs -f l1-advisory-layer"
        ;;
    
    status)
        echo -e "${GREEN}📊 检查服务状态...${NC}"
        ssh -i "$KEY_FILE" "$SERVER" "
        echo '=== Docker容器状态 ==='
        docker ps | grep l1-advisory || echo '服务未运行'
        echo ''
        echo '=== 服务健康检查 ==='
        curl -s http://localhost:8001/health | python3 -m json.tool 2>/dev/null || echo '服务未响应'
        "
        ;;
    
    restart)
        echo -e "${GREEN}🔄 重启服务...${NC}"
        ssh -i "$KEY_FILE" "$SERVER" "
        cd ~/trade-info-l1
        ./docker-l1-stop.sh
        ./docker-l1-run.sh
        "
        ;;
    
    test)
        echo -e "${GREEN}🧪 运行测试...${NC}"
        ssh -i "$KEY_FILE" "$SERVER" "
        cd ~/trade-info-l1
        echo '第一批测试: PR-001/002/003'
        docker run --rm -v \$(pwd):/app trade-info-l1:latest python tests/test_pr_batch1_standalone.py 2>&1 | tail -5
        echo ''
        echo '第二批测试: PR-004/005/006'
        docker run --rm -v \$(pwd):/app trade-info-l1:latest python tests/test_pr_batch2_standalone.py 2>&1 | tail -5
        echo ''
        echo '第三批测试: PR-007/008/009/010'
        docker run --rm -v \$(pwd):/app trade-info-l1:latest python tests/test_pr_batch3_standalone.py 2>&1 | tail -5
        "
        ;;
    
    upload)
        echo -e "${GREEN}📤 上传代码到服务器...${NC}"
        cd "$SCRIPT_DIR"
        rsync -avz --progress \
          -e "ssh -i $KEY_FILE" \
          --exclude='.git' \
          --exclude='__pycache__' \
          --exclude='*.pyc' \
          --exclude='data/db/*.db' \
          --exclude='venv' \
          --exclude='node_modules' \
          ./ "$SERVER:~/trade-info-l1/"
        echo -e "${GREEN}✅ 代码上传完成${NC}"
        ;;
    
    deploy)
        echo -e "${GREEN}🚀 完整部署（上传+重新构建+启动）...${NC}"
        
        # 上传代码
        echo -e "${BLUE}步骤1: 上传代码${NC}"
        cd "$SCRIPT_DIR"
        rsync -avz -e "ssh -i $KEY_FILE" \
          --exclude='.git' \
          --exclude='__pycache__' \
          --exclude='*.pyc' \
          --exclude='data/db/*.db' \
          --exclude='venv' \
          ./ "$SERVER:~/trade-info-l1/" > /dev/null 2>&1
        
        # 重新构建并启动
        echo -e "${BLUE}步骤2: 重新构建镜像${NC}"
        ssh -i "$KEY_FILE" "$SERVER" "
        cd ~/trade-info-l1
        ./docker-l1-stop.sh > /dev/null 2>&1
        ./docker-l1-build.sh
        ./docker-l1-run.sh
        "
        
        echo -e "${GREEN}✅ 部署完成！${NC}"
        ;;
    
    help|*)
        echo -e "${YELLOW}用法: ./aws-connect.sh [命令]${NC}"
        echo ""
        echo "可用命令:"
        echo "  shell/ssh    - 连接到服务器（默认）"
        echo "  logs         - 查看服务日志"
        echo "  status       - 检查服务状态"
        echo "  restart      - 重启服务"
        echo "  test         - 运行测试套件"
        echo "  upload       - 上传代码到服务器"
        echo "  deploy       - 完整部署（上传+构建+启动）"
        echo "  help         - 显示此帮助信息"
        echo ""
        echo "示例:"
        echo "  ./aws-connect.sh          # 连接到服务器"
        echo "  ./aws-connect.sh logs     # 查看日志"
        echo "  ./aws-connect.sh deploy   # 完整部署"
        ;;
esac
