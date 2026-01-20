# 🐳 Docker部署使用说明

## 📋 目录

- [系统要求](#系统要求)
- [快速开始](#快速开始)
- [详细步骤](#详细步骤)
- [使用方法](#使用方法)
- [常用命令](#常用命令)
- [高级配置](#高级配置)
- [故障排查](#故障排查)

---

## 🔧 系统要求

### 必需软件

- **Docker**: 20.10+
- **Docker Compose**: 2.0+ (可选)
- **操作系统**: 
  - macOS 10.15+
  - Windows 10/11 (WSL2)
  - Linux (任何支持Docker的发行版)

### 硬件要求

- **CPU**: 2核以上
- **内存**: 2GB以上
- **磁盘**: 1GB可用空间

---

## 🚀 快速开始

### 三步部署

```bash
# 1. 构建镜像
./docker-build.sh

# 2. 运行容器
./docker-run.sh

# 3. 访问应用
# 打开浏览器访问: http://localhost:5001
```

就这么简单！🎉

---

## 📝 详细步骤

### 步骤1: 安装Docker

#### macOS

```bash
# 使用Homebrew安装
brew install --cask docker

# 或从官网下载
# https://www.docker.com/products/docker-desktop/
```

#### Windows

```
1. 下载Docker Desktop: https://www.docker.com/products/docker-desktop/
2. 启用WSL2
3. 安装并启动Docker Desktop
```

#### Linux (Ubuntu/Debian)

```bash
# 安装Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# 启动Docker服务
sudo systemctl start docker
sudo systemctl enable docker

# 添加当前用户到docker组
sudo usermod -aG docker $USER
```

---

### 步骤2: 构建Docker镜像

#### 方法1: 使用构建脚本（推荐）

```bash
cd /Users/wangqiang/learning/trade-info
chmod +x docker-build.sh
./docker-build.sh
```

**脚本会自动：**
- ✅ 检查Docker是否安装
- ✅ 构建Docker镜像
- ✅ 显示镜像信息
- ✅ 询问是否保存为tar文件

#### 方法2: 手动构建

```bash
# 构建镜像
docker build -t trade-info:latest .

# 查看镜像
docker images trade-info
```

#### 保存镜像到文件

```bash
# 保存镜像
docker save -o trade-info_latest.tar trade-info:latest

# 在其他机器上加载
docker load -i trade-info_latest.tar
```

---

### 步骤3: 运行容器

#### 方法1: 使用运行脚本（推荐）

```bash
chmod +x docker-run.sh
./docker-run.sh
```

#### 方法2: 使用docker-compose

```bash
# 启动
docker-compose up -d

# 停止
docker-compose down
```

#### 方法3: 手动运行

```bash
docker run -d \
    --name trade-info-app \
    -p 5001:5001 \
    -v "$(pwd)/btc_market_data:/app/btc_market_data" \
    -e TZ=Asia/Shanghai \
    --restart unless-stopped \
    trade-info:latest
```

---

## 💡 使用方法

### 访问应用

构建并运行容器后，在浏览器中访问：

```
http://localhost:5001
```

或

```
http://127.0.0.1:5001
```

### 功能说明

应用包含以下功能：

- 📊 **实时行情**：BTC/ETH等多币种价格
- 📈 **K线图表**：多时间周期K线
- 💹 **成交分析**：买卖力量实时统计
- 🐋 **大单追踪**：大额交易监控
- 📖 **订单深度**：买卖盘实时数据

---

## 🔧 常用命令

### 容器管理

```bash
# 查看运行中的容器
docker ps

# 查看所有容器（包括停止的）
docker ps -a

# 启动容器
docker start trade-info-app

# 停止容器
docker stop trade-info-app

# 重启容器
docker restart trade-info-app

# 删除容器
docker rm -f trade-info-app
```

### 日志查看

```bash
# 查看实时日志
docker logs -f trade-info-app

# 查看最近100行日志
docker logs --tail 100 trade-info-app

# 查看带时间戳的日志
docker logs -t trade-info-app
```

### 进入容器

```bash
# 进入容器shell
docker exec -it trade-info-app /bin/bash

# 执行单个命令
docker exec trade-info-app ls -la
```

### 镜像管理

```bash
# 查看镜像
docker images

# 删除镜像
docker rmi trade-info:latest

# 清理未使用的镜像
docker image prune

# 查看镜像详细信息
docker inspect trade-info:latest
```

---

## ⚙️ 高级配置

### 修改端口

#### 方法1: 修改docker-run.sh

```bash
# 编辑docker-run.sh，修改PORT变量
PORT="8080"
```

#### 方法2: 手动指定

```bash
docker run -d \
    --name trade-info-app \
    -p 8080:5001 \
    trade-info:latest
```

### 数据持久化

默认配置已经挂载了数据目录：

```bash
-v "$(pwd)/btc_market_data:/app/btc_market_data"
```

这样导出的数据会保存在主机的 `btc_market_data` 目录中。

### 环境变量配置

```bash
docker run -d \
    --name trade-info-app \
    -p 5001:5001 \
    -e TZ=Asia/Shanghai \
    -e FLASK_ENV=production \
    trade-info:latest
```

### 资源限制

```bash
docker run -d \
    --name trade-info-app \
    -p 5001:5001 \
    --memory="512m" \
    --cpus="1.0" \
    trade-info:latest
```

---

## 🐛 故障排查

### 问题1: 端口已被占用

**错误信息：**
```
Error: bind: address already in use
```

**解决方法：**
```bash
# 查看占用端口的进程
lsof -i :5001

# 停止占用端口的进程
kill -9 <PID>

# 或使用不同端口
docker run -p 8080:5001 trade-info:latest
```

---

### 问题2: 容器无法启动

**排查步骤：**

```bash
# 1. 查看容器日志
docker logs trade-info-app

# 2. 查看容器状态
docker ps -a

# 3. 检查镜像是否存在
docker images | grep trade-info

# 4. 尝试交互式运行
docker run -it --rm trade-info:latest /bin/bash
```

---

### 问题3: 无法访问应用

**检查清单：**

```bash
# 1. 确认容器正在运行
docker ps | grep trade-info

# 2. 检查端口映射
docker port trade-info-app

# 3. 检查防火墙设置
# macOS
sudo pfctl -d

# Linux
sudo ufw status

# 4. 测试网络连接
curl http://localhost:5001/api/markets
```

---

### 问题4: Docker镜像构建失败

**常见原因：**

1. **网络问题**
```bash
# 使用国内镜像源
# 编辑 /etc/docker/daemon.json
{
  "registry-mirrors": [
    "https://docker.mirrors.ustc.edu.cn",
    "https://hub-mirror.c.163.com"
  ]
}

# 重启Docker
sudo systemctl restart docker
```

2. **磁盘空间不足**
```bash
# 清理Docker缓存
docker system prune -a

# 查看磁盘使用
docker system df
```

---

### 问题5: 数据未持久化

**检查挂载：**

```bash
# 查看容器挂载点
docker inspect trade-info-app | grep Mounts -A 20

# 确保目录存在
mkdir -p btc_market_data

# 检查目录权限
ls -la btc_market_data
```

---

## 📊 性能优化

### 1. 多阶段构建（已实现）

Dockerfile使用了轻量级的 `python:3.12-slim` 镜像，减小镜像体积。

### 2. 健康检查

已配置健康检查，Docker会自动监控容器状态：

```yaml
healthcheck:
  test: ["CMD", "python", "-c", "import requests; requests.get('http://localhost:5001/api/markets', timeout=5)"]
  interval: 30s
  timeout: 10s
  retries: 3
```

### 3. 自动重启

配置了 `--restart unless-stopped`，容器会在失败时自动重启。

---

## 🔐 安全建议

### 1. 不要以root运行

```dockerfile
# 在Dockerfile中添加
RUN useradd -m -u 1000 appuser
USER appuser
```

### 2. 限制资源使用

```bash
docker run -d \
    --memory="512m" \
    --cpus="1.0" \
    --pids-limit=100 \
    trade-info:latest
```

### 3. 使用只读文件系统

```bash
docker run -d \
    --read-only \
    --tmpfs /tmp \
    trade-info:latest
```

---

## 📦 镜像分发

### 导出镜像

```bash
# 保存为tar文件
docker save -o trade-info.tar trade-info:latest

# 压缩（可选）
gzip trade-info.tar
```

### 导入镜像

```bash
# 在目标机器上
docker load -i trade-info.tar

# 或从压缩文件
docker load -i trade-info.tar.gz
```

### 推送到私有仓库（可选）

```bash
# 标记镜像
docker tag trade-info:latest your-registry.com/trade-info:latest

# 登录
docker login your-registry.com

# 推送
docker push your-registry.com/trade-info:latest
```

---

## 🔄 更新应用

### 方法1: 重新构建

```bash
# 停止并删除旧容器
./docker-stop.sh

# 重新构建镜像
./docker-build.sh

# 启动新容器
./docker-run.sh
```

### 方法2: 使用docker-compose

```bash
# 重新构建并启动
docker-compose up -d --build
```

---

## 📋 完整示例

### 从零开始部署

```bash
# 1. 克隆或获取项目
cd /Users/wangqiang/learning/trade-info

# 2. 给脚本添加执行权限
chmod +x docker-build.sh docker-run.sh docker-stop.sh

# 3. 构建镜像
./docker-build.sh

# 4. 运行容器
./docker-run.sh

# 5. 查看日志
docker logs -f trade-info-app

# 6. 访问应用
open http://localhost:5001

# 7. 停止应用
./docker-stop.sh
```

---

## 🎯 最佳实践

### 1. 使用脚本管理

- ✅ 使用 `docker-build.sh` 构建
- ✅ 使用 `docker-run.sh` 运行
- ✅ 使用 `docker-stop.sh` 停止

### 2. 定期备份数据

```bash
# 备份数据目录
tar -czf btc_market_data_backup_$(date +%Y%m%d).tar.gz btc_market_data/
```

### 3. 监控日志

```bash
# 实时查看日志
docker logs -f --tail 100 trade-info-app
```

### 4. 定期更新

```bash
# 定期重新构建镜像以获取最新依赖
./docker-build.sh
```

---

## 📞 技术支持

如遇到问题，请检查：

1. ✅ Docker是否正常运行
2. ✅ 端口是否被占用
3. ✅ 网络连接是否正常
4. ✅ 日志中的错误信息

---

## 📄 文件清单

项目中的Docker相关文件：

- `Dockerfile` - Docker镜像定义文件
- `.dockerignore` - Docker构建忽略文件
- `docker-compose.yml` - Docker Compose配置
- `docker-build.sh` - 镜像构建脚本
- `docker-run.sh` - 容器运行脚本
- `docker-stop.sh` - 容器停止脚本
- `Docker使用说明.md` - 本文件

---

## 🎉 总结

Docker化部署的优势：

- ✅ **环境一致**：开发和生产环境完全一致
- ✅ **快速部署**：一键构建和运行
- ✅ **易于迁移**：镜像可以在任何支持Docker的机器上运行
- ✅ **资源隔离**：不影响主机环境
- ✅ **便于管理**：统一的容器管理命令

**立即体验Docker化部署！** 🚀

---

**更新日期：** 2026-01-17  
**版本：** v1.0.0  
**Docker镜像：** trade-info:latest
