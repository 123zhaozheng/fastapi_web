# 使用官方 Python 镜像作为基础镜像
FROM python:3.9-slim

# 设置工作目录
WORKDIR /app

# 将依赖文件复制到工作目录
COPY requirements.txt .

# 安装项目依赖
RUN pip install --no-cache-dir -r requirements.txt

# 将项目所有文件复制到工作目录
COPY . .

# 暴露应用监听的端口
EXPOSE 5000

# 设置容器启动命令
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "5000"]