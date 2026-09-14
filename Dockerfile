# yfq-resume 简历站 · 生产镜像
FROM python:3.11-slim

WORKDIR /app

# 依赖（gunicorn 生产运行 + flask + pillow 头像校验）
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 应用代码
COPY . .

# 制作“首次启动种子”：uploads 图片、数据库、会话密钥、LOGO
# （挂载卷为空/缺失时由 entrypoint 恢复，保证部署零操作）
RUN mkdir -p /app/data_seed/uploads \
    && cp -r /app/static/uploads/. /app/data_seed/uploads/ \
    && cp /app/resume.db /app/data_seed/resume.db \
    && cp /app/secret.key /app/data_seed/secret.key \
    && cp /app/static/logo.webp /app/data_seed/logo.webp

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 5000
ENTRYPOINT ["/entrypoint.sh"]
