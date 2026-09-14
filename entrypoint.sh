#!/bin/sh
# 首次启动时，若挂载卷为空/缺失，从镜像内种子恢复，之后由宿主机卷持久化
# 挂载约定（见 docker-compose.yml）：
#   ./data         -> /app/data        （resume.db + secret.key 放这里）
#   ./data/uploads -> /app/static/uploads（上传图片）
set -e

# 1) 数据库
if [ ! -f /app/data/resume.db ]; then
  cp /app/data_seed/resume.db /app/data/resume.db
fi

# 2) 会话密钥
if [ ! -f /app/data/secret.key ]; then
  cp /app/data_seed/secret.key /app/data/secret.key
fi

# 3) 上传目录（图片）
if [ ! -d /app/static/uploads ] || [ -z "$(ls -A /app/static/uploads 2>/dev/null)" ]; then
  mkdir -p /app/static/uploads
  cp -r /app/data_seed/uploads/. /app/static/uploads/
fi

# 4) LOGO：优先挂载卷 ./data/logo.webp 或 ./data/logo.png（png 自动转 webp），否则用镜像种子
if [ -f /app/data/logo.webp ]; then
  cp -f /app/data/logo.webp /app/static/logo.webp
elif [ -f /app/data/logo.png ]; then
  python -c "from PIL import Image; im=Image.open('/app/data/logo.png').convert('RGBA'); im.save('/app/static/logo.webp','WEBP',quality=100)"
elif [ ! -f /app/static/logo.webp ]; then
  cp /app/data_seed/logo.webp /app/static/logo.webp
fi

# 5) 启动生产服务
exec gunicorn -w 2 -b 0.0.0.0:5000 app:app
