# ---------- 阶段一：构建前端 ----------
FROM node:20-alpine AS frontend
WORKDIR /build
COPY frontend/package*.json ./
RUN npm install --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# ---------- 阶段二：后端运行时 ----------
FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1
WORKDIR /app

COPY backend/requirements.txt ./requirements.txt
COPY backend/ ./
COPY samples/ ./samples
COPY --from=frontend /build/dist ./static

EXPOSE 8000

# 依赖随容器启动安装（利用挂载的 pip 缓存卷，重启几乎无开销），随后启动服务
CMD ["sh", "-c", "pip install -r requirements.txt && exec uvicorn app.main:app --host 0.0.0.0 --port 8000"]
