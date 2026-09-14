# timeline-cv 简历站 · 生产镜像（纯净版：不含任何用户数据）
# 数据（resume.db / uploads / secret.key / logo / backups）由挂载卷提供，
# 首次启动 app.py 自动建空库 + 默认管理员，拉镜像即全新网站。
FROM python:3.11-slim

WORKDIR /app

# 依赖（gunicorn 生产运行 + flask + pillow 头像校验）
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 应用代码（.dockerignore 已排除 resume.db / uploads / secret.key / backups / logo）
COPY . .

# 内置中性默认 LOGO（非用户品牌；部署方可通过 ./data/logo.png 覆盖）
RUN python -c "from PIL import Image, ImageDraw; im=Image.new('RGBA',(256,256),(0,0,0,0)); d=ImageDraw.Draw(im); d.rounded_rectangle([8,8,248,248], radius=56, fill=(20,126,251)); im.save('/app/static/logo.webp','WEBP',quality=100)"

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 5000
ENTRYPOINT ["/entrypoint.sh"]
