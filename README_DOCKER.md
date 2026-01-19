# 🐳 Docker快速部署指南

## 🚀 三步部署

### 1️⃣ 构建镜像

```bash
./docker-build.sh
```

### 2️⃣ 运行容器

```bash
./docker-run.sh
```

### 3️⃣ 访问应用

打开浏览器访问：**http://localhost:5001**

---

## 📦 项目文件

```
trade-info/
├── Dockerfile                    # Docker镜像定义
├── .dockerignore                 # 构建忽略文件
├── docker-compose.yml            # Docker Compose配置
├── docker-build.sh               # 构建脚本 ⭐
├── docker-run.sh                 # 运行脚本 ⭐
├── docker-stop.sh                # 停止脚本 ⭐
├── Docker使用说明.md              # 详细文档
└── README_DOCKER.md              # 本文件
```

---

## 🔧 常用命令

### 构建与运行

```bash
# 构建镜像
./docker-build.sh

# 运行容器
./docker-run.sh

# 停止容器
./docker-stop.sh
```

### 使用Docker Compose

```bash
# 启动
docker-compose up -d

# 停止
docker-compose down

# 查看日志
docker-compose logs -f
```

### 手动操作

```bash
# 构建镜像
docker build -t trade-info:latest .

# 运行容器
docker run -d -p 5001:5001 --name trade-info-app trade-info:latest

# 查看日志
docker logs -f trade-info-app

# 停止容器
docker stop trade-info-app
```

---

## 💾 保存镜像到本地

### 构建时自动保存

运行 `./docker-build.sh` 时，脚本会询问是否保存镜像到tar文件：

```
💾 是否要将镜像保存为tar文件? (y/n)
```

选择 `y`，会自动保存为 `trade-info_latest.tar`

### 手动保存

```bash
# 保存镜像
docker save -o trade-info_latest.tar trade-info:latest

# 压缩（可选）
gzip trade-info_latest.tar

# 查看文件大小
ls -lh trade-info_latest.tar*
```

---

## 📤 在其他机器上使用

### 1. 复制镜像文件

```bash
# 将tar文件复制到目标机器
scp trade-info_latest.tar user@target-host:/path/to/
```

### 2. 加载镜像

```bash
# 在目标机器上
docker load -i trade-info_latest.tar

# 如果是压缩文件
docker load -i trade-info_latest.tar.gz
```

### 3. 运行容器

```bash
docker run -d -p 5001:5001 --name trade-info-app trade-info:latest
```

---

## 🔍 查看信息

### 镜像信息

```bash
# 查看所有镜像
docker images

# 查看特定镜像
docker images trade-info

# 查看镜像详细信息
docker inspect trade-info:latest
```

### 容器信息

```bash
# 查看运行中的容器
docker ps

# 查看所有容器
docker ps -a

# 查看容器详细信息
docker inspect trade-info-app
```

---

## 📊 镜像信息

- **基础镜像**: python:3.12-slim
- **预估大小**: ~150-200MB
- **端口**: 5001
- **数据卷**: ./btc_market_data

---

## 🎯 功能特点

### ✅ 已实现功能

- 📊 实时行情数据
- 📈 K线图表（4种时间间隔）
- 💹 最近成交统计（4个时间维度）
- 🐋 大单分析（7个时间 × 3个金额）
- 📖 订单深度
- 🌐 多币种支持（BTC, ETH, AT等）

### ✅ Docker特性

- 🐳 一键构建和部署
- 💾 镜像可保存和迁移
- 🔄 自动重启
- 📊 健康检查
- 📁 数据持久化

---

## ⚠️ 注意事项

### 端口冲突

如果5001端口被占用，可以修改 `docker-run.sh` 中的 `PORT` 变量，或使用：

```bash
docker run -d -p 8080:5001 --name trade-info-app trade-info:latest
```

### 网络访问

确保能够访问币安API：
- api.binance.com
- fapi.binance.com

如需代理，请在Dockerfile中配置：

```dockerfile
ENV HTTP_PROXY="http://proxy:port"
ENV HTTPS_PROXY="http://proxy:port"
```

---

## 🛠️ 故障排查

### 构建失败

```bash
# 检查Docker是否运行
docker info

# 清理Docker缓存
docker system prune -a

# 重新构建
./docker-build.sh
```

### 容器无法启动

```bash
# 查看日志
docker logs trade-info-app

# 交互式运行
docker run -it --rm trade-info:latest /bin/bash
```

### 无法访问应用

```bash
# 检查容器状态
docker ps

# 检查端口映射
docker port trade-info-app

# 测试连接
curl http://localhost:5001/api/markets
```

---

## 📚 更多信息

详细文档请查看：**Docker使用说明.md**

---

## 🎉 快速示例

### 完整部署流程

```bash
# 1. 进入项目目录
cd /Users/wangqiang/learning/trade-info

# 2. 构建镜像
./docker-build.sh
# 选择 y 保存镜像到tar文件

# 3. 运行容器
./docker-run.sh

# 4. 查看日志（可选）
docker logs -f trade-info-app

# 5. 访问应用
open http://localhost:5001

# 6. 停止应用
./docker-stop.sh
```

---

## 📞 技术支持

如遇到问题：

1. 查看 **Docker使用说明.md**
2. 检查容器日志：`docker logs trade-info-app`
3. 验证Docker版本：`docker --version`

---

**祝您使用愉快！** 🚀

**更新日期：** 2026-01-17  
**Docker版本：** 20.10+  
**镜像版本：** trade-info:latest
