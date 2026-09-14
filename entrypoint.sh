#!/bin/sh
# 纯净部署：镜像不含用户数据，启动前只做目录准备，建库/默认管理员由 app.py 自举完成。
# 挂载约定（见 docker-compose.yml）：
#   ./data         -> /app/data        （resume.db + secret.key 放这里，首次启动由 app 建空库）
#   ./data/uploads -> /app/static/uploads（上传图片）
set -e

# 1) 确保数据卷目录存在（app.py 会幂等建库）
mkdir -p /app/data /app/static/uploads

# 2) LOGO：优先用挂载卷 ./data/logo.png 或 ./data/logo.webp 覆盖内置默认 logo
if [ -f /app/data/logo.webp ]; then
  cp -f /app/data/logo.webp /app/static/logo.webp
elif [ -f /app/data/logo.png ]; then
  python -c "from PIL import Image; im=Image.open('/app/data/logo.png').convert('RGBA'); im.save('/app/static/logo.webp','WEBP',quality=100)"
fi

# 3) 启动生产服务
exec gunicorn -w 2 -b 0.0.0.0:5000 app:app
