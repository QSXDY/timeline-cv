# yfq-resume — 杨芳清个人简历网站（动态版）

把静态简历页（`简历/杨芳清-简历.html`）改造成 **Flask + SQLite** 的动态网站：前台还原原排版，
后台 `/adminc` 管理全部内容，改完前台即时生效。

---

## 一、已确认需求（用户拍板，勿再改动）

1. **技术栈**：Python Flask + SQLite，**尽量轻量**（用户明确否了 Next.js/TS/pnpm 路线）
2. **后台入口**：`/adminc`；账号 `YFQ`，密码 `yfp5201314` —— **PBKDF2 加盐哈希，不存明文**
3. **HTML 编辑器**：wangEditor **v4 本地版**（已下载 `static/vendor/wangEditor.min.js`，262KB，UMD 单文件，离线可用，`window.wangEditor`）
4. **图片目录（v10 起）**：`static/uploads/<分组名>/<项目id>-<项目标题>/`，**项目 id 前缀解耦**——
   改标题/换分组不再迁移项目子目录（分组改名仅重命名分组顶层目录）；数据库只存纯文件名，
   前台 URL 用变量拼接；非法字符清洗 `\/:*?"<>|` → `-`
5. **数据迁移**：从旧静态页按字段导入（数据源 = 上级目录 `_gen.py` 的 `GROUPS` / `AIGC_PHOTOS`）
6. **后台七个菜单**（导航栏顺序即此）：
   1. 基础信息：姓名 / 标题 / 简介 / 联系方式等
   2. 概要：主标题 + 副标题 + 卡片（3×3 布局：标题 + 内容）
   3. 精选项目：项目分类增改删 + 项目附标题（如“财经 · 演艺 · 音乐 · 文化”）
   4. 项目内容：项目标题 / 副标题(描述) / 图片（**预选横图或竖图**，横图行 3 张、竖图行 6 张，支持上传/删除/改描述）+ 图片描述
   5. 工作经历：增改删经历 / 职位 / 日期 / 工作内容 / **工作详情（HTML 编辑器）**
   6. 技能：标题 + 副标题（预留）+ 卡片（左右分栏）标题 + 技术标签增改删
   7. 系统设置：管理员密码修改 + CDN（EdgeOne）配置
7. **前台排版**：还原现有 `style.css` / `script.js` 的布局 —— 横图行 3 列、竖图行 6 列、单行不混排、图片 `object-fit: cover` 铺满
8. **项目目录名**：`yfq-resume`（英文名）
9. **字体**：全站（前台 + 后台）引用小米 **MiSans**（开源免费商用），CDN `https://cdn.xrbk.cn/fonts/MiSans-{Regular,Medium,Semibold,Bold}/result.css`，`font-family: "MiSans", ...`；正文两端对齐（`text-align: justify; text-justify: inter-ideograph`）
10. **个人照片（可选）**：后台「基础信息 → 个人照片」上传/删除 1:1 头像，存 `static/uploads/_avatar/`（db `basic_info.avatar` 只存文件名）；前台 hero 右侧条件渲染（有头像才显示，无头像零痕迹）
11. **系统设置**（第 7 个后台菜单）：管理员密码修改（当前密码校验 + PBKDF2 重存）+ 腾讯 EdgeOne CDN 配置（开关 + 加速域名前缀，开启后前台图片/视频 URL 全部走 CDN，配置存 `settings` 表，运行时缓存）
12. **全站图片 WEBP**：现有 431 张图 + logo 已批量转 WEBP（quality=100 无视觉损失，保留透明通道）；此后**所有图片上传自动转 WEBP 且只保存 `.webp`**（项目图、头像、富文本插图三条上传链路均已改造）；logo 模板统一引用 `logo.webp`（Docker 挂载 `./data/logo.png` 会自动转）
13. **作品视频支持**：mp4 / m4v / mov / webm，方向横 16:9（行 3 张）/ 竖 9:16（行 6 张）规则与图片完全一致；前台 frame 内 `video` 渲染、点击进 lightbox 白底播放（带 controls）；后台图片卡直接显示视频缩略

---

## 二、目录结构

```
yfq-resume/
├── README.md                ← 本文件（项目文档 + 进度快照）
├── app.py                   ← Flask 主应用（登录/CSRF/六分类CRUD/图片上传/前台渲染）✅
├── db.py                    ← SQLite 表结构 + 连接 ✅
├── migrate.py               ← 数据迁移脚本（v2 两级目录方案，幂等重建）✅
├── requirements.txt         ← 依赖（flask + pillow；均已装于 D:\Python）
├── resume.db                ← SQLite 数据库（6/69/430，已迁移）
├── static/
│   ├── css/style.css        ← 前台样式（已复制，渲染复用）
│   ├── css/admin.css        ← 后台样式 ✅
│   ├── js/script.js         ← 前台横竖分行逻辑（已复制）
│   ├── js/admin.js          ← 后台交互（wangEditor 初始化等）✅
│   ├── uploads/             ← 上传素材 431 个（分类/项目 两级子目录，全部 .webp；视频原样）
│   ├── logo.webp            ← 全站 LOGO（前台/后台/登录页三处引用）
│   └── vendor/wangEditor.min.js  ← wangEditor v4（已下载）
└── templates/
    ├── index.html           ← 前台首页 ✅
    └── admin/
        ├── login.html       ← 登录页 ✅
        ├── base.html        ← 后台骨架：侧边栏六分类导航 + 退出 ✅
        ├── basic.html       ← 基础信息 ✅
        ├── summary.html     ← 概要 + 卡片 ✅
        ├── categories.html  ← 项目分类 ✅
        ├── projects.html    ← 项目列表/新建 ✅
        ├── project_edit.html← 项目编辑 + 图片管理（横3竖6网格/上传/改描述/删除）✅
        ├── experience.html  ← 工作经历（wangEditor 详情）✅
        ├── skills.html      ← 技能（标题副标题/卡片/标签）✅
        └── settings.html    ← 系统设置（改密码 / CDN）✅
```

---

## 三、数据库表结构（db.py，已实现）

```sql
admin          (id=1, username UNIQUE, password_hash)             -- pbkdf2_sha256$iter$salt$hash
basic_info     (id=1, name, role, lead, intent, salary, location, email, profile, avatar)
summary        (id=1, title, subtitle)
summary_cards  (id, title, content, sort)
categories     (id, classification_id FK, name, subtitle, tags, sort)  -- 分组（kind 已废弃删除）
projects       (id, category_id FK CASCADE, title, desc, detail_html, pub_date, sort)
images         (id, project_id FK CASCADE, filename, orientation h/v, type image/video, caption, sort)
settings       (key PK, value)                                   -- cdn_enabled / cdn_base 等键值配置
experiences    (id, position, org, years, content(每行一条), detail_html, sort)
skills         (id=1, title, subtitle)
skill_cards    (id, title, sort)
skill_tags     (id, card_id FK CASCADE, name, sort)
```

**图片路径约定（关键）**：`images.filename` 只存**纯文件名**（如图片 `001_01.webp`、视频 `xxxx.mp4`），
不存路径。前台 URL = `/static/uploads/<分组名>/<项目id>-<项目标题>/<filename>`，用变量拼接
（`img_url` / `project_dir` 统一构造，含 id 前缀）。改标题/换分组时数据库素材记录与磁盘目录**均不动**；
分组改名会整体重命名分组顶层目录（项目子目录随之移动）。
启用 CDN 后 `img_url`、`cdn`/`cdn_html` 过滤器自动给 URL 加加速域名前缀（读 `settings` 缓存），
**作品图、富文本 detail_html 内图片、logo、头像、favicon 全部覆盖**。

---

## 四、环境与运行

- 环境：Windows；Python 3.13.6 位于 `D:\Python\python.exe`；**Flask 3.1.1 已装、Pillow 已装**（无需 pip install）
- 数据库初始化 + 迁移：`cd yfq-resume && python migrate.py`
  （会删旧 db、清空 uploads、从上级 `_gen.py` 重新导入；产出 6 分类 / 69 项目 / 430 图 / admin YFQ）
- 启动（完成后）：`cd yfq-resume && python app.py` → 前台 `http://127.0.0.1:5000`，后台 `http://127.0.0.1:5000/adminc`
- ⚠️ **改了 `templates/` 后必须重启服务**（非 debug 模式下 Jinja 模板有编译缓存，不重启不生效；
  `static/` 静态文件无此问题，刷新即可）

---

## 四·B、Docker 部署（1Panel / 服务器）

**生产（推荐，拉 Docker Hub 镜像，已打通自动构建）：**

```bash
cd yfq-resume
cp .env.example .env        # 可选：想固定版本就改 RESUME_IMAGE=cnqsxdy/timeline-cv:1.0.0
docker compose pull
docker compose up -d
```

**开发（本地构建）：**

```bash
RESUME_IMAGE=yfq-resume:local docker compose up -d --build
```

- **镜像**：`cnqsxdy/timeline-cv:latest`（Docker Hub，amd64 + arm64 双架构；
  **打 tag 发版时自动构建**，见「四·D」）；不设 `RESUME_IMAGE` 默认即拉此镜像

- **纯净镜像（不含任何用户数据）**：`.dockerignore` 已排除 `resume.db`、`secret.key`、
  `static/uploads/`、`backups/`、`logo`；**把镜像分享给别人 = 全新空站**
  （别人拉镜像、`docker compose up` 后首次启动自动建空库 + 默认管理员 **admin / admin**，
  登录后请在系统设置中改密码；也可用环境变量 `YFQ_ADMIN_USER` / `YFQ_ADMIN_PASS` 覆盖默认值）
- **忘记管理员密码**（shell 特权操作，仅服务器管理员可执行；前台无重置入口）：
  - 本地：`python app.py --reset-admin`（重置为 admin/admin）或 `python app.py --reset-admin 新密码`
  - Docker：`docker exec -it yfq-resume python app.py --reset-admin 新密码`（只改密码哈希，数据不动）
- 你自己的部署：`./data/` 挂载卷里有 `resume.db` 就直接用（不会被覆盖），没有则自动建空库
- 数据持久化在宿主机 `./data/` 目录：`resume.db` + `secret.key` 在 `./data/`，
  上传图片在 `./data/uploads/`（与镜像分离，1Panel 文件管理可直接看到/备份）
- **全站 LOGO**：前台顶栏 / 后台侧边栏 / 登录页共用 `static/logo.webp`（镜像内置中性默认占位 logo）；
  把新 LOGO 放到 `./data/logo.png` 或 `./data/logo.webp`（`./data` 已整体挂载），
  放 png 会自动转 webp，`docker restart yfq-resume` 即生效。
  ⚠️ 不要单独 bind mount 单文件（Docker 会把不存在的宿主文件建成目录导致启动失败）
- 数据库路径由环境变量覆盖（`RESUME_DB=/app/data/resume.db`、`SECRET_KEY_FILE=/app/data/secret.key`），
  **不要**直接 bind mount 单文件（Docker 会把不存在的宿主文件建成目录导致启动失败）
- 网络使用 `1panel-network`（external），配合 1Panel 网站 → 反向代理 → 容器 `127.0.0.1:5000`
- 更新：生产 = `docker compose pull && docker compose up -d`（升级改 `.env` 版本号重拉即可）；
  开发 = `docker compose up -d --build`；数据都不受影响
- 端口如需直连可保留 `ports: "5000:5000"`，纯走反代可删掉该段

---

## 四·C、代码体检（部署前必跑）

项目根目录依次执行（Windows 下用 `D:\Python\python.exe`）：

```bash
# 1. 代码规范 + 可疑代码（ruff，风格类问题）
python -m ruff check app.py db.py migrate.py
python -m ruff format --check app.py db.py migrate.py

# 2. 安全漏洞扫描（bandit：SQL 注入/路径穿越/硬编码密码等）
python -m bandit -r app.py db.py migrate.py

# 3. 依赖漏洞审计（pip-audit：查询已知 CVE）
python -m pip_audit -r requirements.txt

# 4. 功能冒烟（Flask test client，应输出 200 / 200）
python -c "import app; c = app.app.test_client(); print('首页:', c.get('/').status_code, '| 登录页:', c.get('/adminc/login').status_code)"
```

- 工具安装：`python -m pip install ruff bandit pip-audit`
- ⚠️ **本机 Python 的 `--user` site 不在 sys.path**，pip-audit 等纯 Python 工具须装到系统目录（不带 `--user`），否则 `ModuleNotFoundError`
- **体检基线（2026-09-15）**：ruff check **0 项**（All checks passed）、ruff format 3 文件已统一格式化；
  豁免规则见 `ruff.toml`（BLE001/S110 防御性宽异常、DTZ005 本地单机无时区——均为有意设计，非遗留问题）；
  bandit **0 高危 0 中危**（4 项低危 try-except-pass 防御代码）；pip-audit **No known vulnerabilities**；冒烟 200/200
- 已修复项：`migrate.py` 明文密码 → 读 `YFQ_ADMIN_PASS` 环境变量（缺失自动生成随机密码并打印）；
  `app.py` 备份文件 `open()` 泄漏 → `with` 上下文；全量 `%` 格式化 → f-string、import 排序、
  dict 推导等 15 项自动修复 + 3 文件统一格式化

- **CI/CD 自动构建（GitHub Actions → Docker Hub）✅ 已验证（2026-09-15）**：**打 `v*` 标签才构建**（日常 push 不构建），
  发版自动推送 `:latest` + `:v1.0.0` + `:v1.0`（amd64 + arm64 双架构）。首次配置一次（见「四·D」），之后发版只需打 tag
- **两种部署模式**（docker-compose.yml 双模式）：
  - 生产（默认）：直接 `docker compose pull && docker compose up -d` —— 镜像默认
    `cnqsxdy/timeline-cv:latest`；升级 = 改 `.env` 版本号重拉
  - 开发（本地构建）：`RESUME_IMAGE=yfq-resume:local docker compose up -d --build`

---

## 四·D、首次配置：GitHub Actions → Docker Hub 自动构建（一次性，约 5 分钟）

> ✅ **本项目已完成此配置并验证通过（2026-09-15）**，以下为复刻/换账号时的步骤。

1. **Docker Hub**（hub.docker.com）：
   - 右上角确认你的**用户名**（本项目为 `cnqsxdy`）；
   - 仓库 `timeline-cv` 为**自动创建（Public）**；想改 Private 去仓库 Settings 切换（部署方需先 `docker login`）
2. **生成 Access Token**：Docker Hub → Account Settings → Security → New Access Token，
   权限勾 Read/Write/Delete → 复制生成的 token（只显示一次）；
3. **GitHub 仓库**（Settings → Secrets and variables → Actions → New repository secret）：
   - `DOCKERHUB_USERNAME` = 你的 Docker Hub 用户名
   - `DOCKERHUB_TOKEN` = 上一步的 token
4. **触发验证**：打 tag `git tag v1.0.0 && git push --tags`（或 Actions 页手动 Run workflow），
   构建成功后 Docker Hub 仓库即出现 `latest` + `v1.0.0` 镜像；
5. **发布版本**：`git tag v1.0.0 && git push --tags` → 自动构建 `:v1.0.0` 与 `:v1.0`。

> 别人部署你的镜像：`RESUME_IMAGE=<你的用户名>/timeline-cv:版本` + `docker compose pull && up -d`。
> 若镜像为 Private，部署方需先 `docker login` 一次。

---

## 五、当前进度（快照：2026-09-13 · 全部完成）

- [x] 目录结构创建
- [x] 静态资源：style.css / script.js 复制、wangEditor v4 下载
- [x] `db.py` 表结构
- [x] `migrate.py` v2 两级目录方案跑通：`uploads/<清洗后分类名>/<清洗后项目名>/NNN_原名.jpg`，
      `images.filename` 只存纯文件名；产出 **6 分类 / 69 项目 / 430 图 / 3 经历 / 2 技能卡 / 22 标签**；
      幂等（先删 db + uploads 再重建）；同名覆盖坑已修（全局三字节序号前缀 `001_`）
- [x] `app.py` 后端：登录（PBKDF2 校验）/ 登出 / CSRF（session token + before_request）/ 六分类 CRUD /
      图片上传（白名单 + PIL 校验 + 20MB + uuid 文件名 + orientation）/ 图片描述/方向更新 / 图片删除（连物理文件）/
      wangEditor 上传端点 `/adminc/upload` / 前台 `/` 一次性加载渲染；改名/换分类自动移动物理目录
- [x] 前台模板 `index.html` + `base.html`：完全复用 style.css 类名，横图行 3 列 / 竖图行 6 列 / 单行不混排，
      AIGC 专区 / 经历 detail_html / 技能 subtitle 条件渲染
- [x] 后台模板 8 个 + `admin.css` + `admin.js`
- [x] **端到端实测通过**（浏览器自动化验证，全部通过后已还原数据）：
  - 前台：hero / 3 概要卡 / 5 组 60 条目 + AIGC / 3 经历 / 2 技能卡全渲染；
    **430/430 图片加载、0 错误**；横 53 行 / 竖 28 行 / 0 混排
  - 登录：错误密码报错、正确凭据 302 → `/adminc/basic`
  - CRUD 写链路（逐一实测并还原）：
    基础信息保存（前台即时联动）✅ 图片上传（入库+落盘+前台显示）✅
    项目改名 → 物理目录跟随 + 前台图片自动改路径 ✅ 分类改名 → 整组目录移动（17 子目录）✅
    图片删除（含物理文件）✅ 经历新增/删除（含 wangEditor detail_html）✅
    技能标签增删 ✅ 概要卡片增删（前台 3↔4 联动）✅
  - 清理：所有测试数据/文件已还原（db 6/69/430、uploads 430 文件与库一致）
- [x] README 最终版
- [x] **第二轮功能（2026-09-14，全部实测通过）**：
  - 后台侧边栏：纯白背景 + 整体下移（padding-top 54px）+ 导航文字水平垂直居中（flex）
  - 系统设置页（/adminc/settings）：改密码（当前密码校验、错误拒绝、PBKDF2 重存）+ CDN（EdgeOne 域名前缀开关，
    实测开启后前台 img src 变 `https://cdn.example.com/static/uploads/...`，关闭即还原）
  - 全站 WEBP：431 张 jpg → webp（quality=100）、logo.png → logo.webp、db filename 同步更新（0 缺失）；
    上传自动转实测：jpg 上传 → 落盘 .webp（仅存 webp）
  - 视频支持：mp4 上传（type=video、原样保存）→ 前台竖图 6 列渲染（9:16）+ lightbox 白底播放（controls）实测通过；
    测试数据已清理，密码已还原 yfp5201314
- [x] README 同步第二轮功能

- [x] **v10 全面加固（2026-09-14，全部修复）**：
  - **图片懒加载**：前台作品图/视频改 `data-src`，`details` 条目**展开时才真正请求**（折叠条目 0 请求），
    配合 `.frame` 浅灰占位；lightbox 点击放大逻辑不变
  - **死字段清理**：`classifications.section`、`categories.kind` 列删除（`db._drop_legacy_cols` 重建表迁移），
    `load_site_data` 移除 groups/aigcs 死分支
  - **标题与目录解耦**：项目目录改 `uploads/<分组>/<id>-<标题>/`，69 项目目录已批量加 id 前缀（60 个有图目录 + 无图项目），
    改标题/换分组不再迁移项目目录；后台编辑页 hint 同步
  - **删除语义统一**：删分类 → 级联删其下全部分组/项目/图片记录 + 磁盘目录（confirm 文案已更新）；
    删分组 → 删磁盘目录 + 级联删项目；删项目 → 删目录 + 记录；三处均顺带清理富文本 `_editor/` 孤儿图片
  - **CDN 全覆盖**：`cdn`/`cdn_html` Jinja 过滤器注册，富文本 detail_html 图片、logo、头像、favicon 均走 CDN；
    原 `img_url` 覆盖作品图/视频不变
  - **SQLite 加固**：`WAL` 日志模式 + `busy_timeout=5000`（gunicorn 多进程安全）
  - **自动备份**：启动时每日备份一次 `resume.db` 到 `backups/`（保留 7 份，日期标记防多进程重复），
    Docker 下 `RESUME_BACKUP_DIR=/app/data/backups` 落入挂载卷
  - **登录限速**：连续失败 5 次锁定 15 分钟（session 级）
  - **杂项**：后台不再禁右键（仅前台禁）；favicon 指向 logo.webp（前后台）；富文本 label 文案改「显示在图片下方」

**测试中发现并确认的已知行为（非 bug）**：
- 后台各页第一个 `<form>` 是侧边栏**退出登录**表单，自动化脚本选中它会把保存当成登出（人工点保存不受影响）
- 删除类按钮（图片/卡片/标签/经历/分类）带 `onsubmit=confirm()` 二次确认，自动化需绕过 confirm 才会真删（人工操作正常弹窗）

---

## 六、开发中必须遵守的约定

1. **登录安全**：PBKDF2-HMAC-SHA256，260000 次迭代，随机 16 字节盐，格式 `pbkdf2_sha256$260000$盐hex$哈希hex`（migrate.py 已实现 `hash_password` / 校验逻辑需在 app.py 实现 `verify_password`）
2. **CSRF**：session 存 token，后台所有 POST 校验（轻量实现）
3. **目录名清洗**：`re.sub(r'[\\/:*?"<>|]', '-', name)`，去首尾空白，空则回退 `untitled`
4. **图片上传**：白名单 jpg/jpeg/png/gif/webp；PIL 校验可读；**保存前统一转 WEBP（quality=100）只存 `.webp`**；文件名 `uuid4().hex[:12] + .webp`；orientation 由用户预选（h/v）；上传上限 500MB
5. **视频上传**：mp4/m4v/mov/webm；不转码原样保存；`images.type = 'video'`；方向规则同图片（横 3 列 / 竖 6 列）
5. **删除项目/分类**：级联删除数据库记录 + **删除对应物理图片目录**
6. **前台还原**：hero / summary(3卡片) / 精选项目组(分类→项目details→igrid) / AIGC 专区(kind='aigc'，详情富文本在上) / 工作经历 / 技能，全部用现有 style.css 类名
7. **AIGC 专区映射**：分类 kind='aigc'，name 即 eyebrow（迁移值 `AIGC 经历 · 2023 至今`），subtitle 即 h2（迁移值 `把模型能力，变成团队和客户用得上的东西。`），其项目 detail_html 是 `<ul class="ai-list">` 4 条
8. **精选项目区标题副标题**（“把内容交给现场… / 按项目类型分组…”）暂硬编码模板，后台未做字段（用户未要求，技能区已预留 title/subtitle）
9. **CDN 缓存**：`img_url` 读 `settings`（模块级缓存，系统设置保存后失效重载）；CDN 开启时 `https://加速域名/static/uploads/**` 由 EdgeOne 回源本服务

---

## 七、旧数据源（迁移用，勿删）

- `简历/_gen.py`：数据结构唯一来源（`GROUPS` = 5 组分类+条目+chips；`AIGC_PHOTOS` = 9 图；`folder_files(prefix)` / `portrait()` 工具；已加 `if __name__ == "__main__":` 保护）
- `简历/朋友圈备份/figure/`：原始图片库（749 文件夹 / 3653 图）
- `简历/style.css` / `script.js`：前台样式脚本原件（已复制到本项目）


---

## 五、三级结构与 5 大板块（2026-09 重构）

### 后台三级结构（精选项目大板块）
```
3 精选项目（大板块）
  3.1 项目分类（一级：名称 + 显示区，普通分类/独立专区可自由新建，如「短视频作品」）
      └ 3.2 项目分组（二级：现有 categories，挂 classification_id）
          └ 3.3 项目内容（三级：现有 projects，两级选择后管理）
```
- 物理目录保持 `uploads/<分组>/<项目id>-<标题>/` 两级**不动**（分类是纯逻辑层，改名不迁移磁盘）
- 新增分类直接归属精选项目大板块（独立专区只是分类名，如「短视频作品」）
- **删除语义（v10 统一）**：删分类 → 级联删其下全部分组/项目/图片记录 + 磁盘目录；删分组 → 删磁盘目录 + 级联删项目；删项目 → 删目录 + 记录；三处均顺带清理富文本 `_editor/` 孤儿图片（仍被其他项目引用则保留）
- 分类/分组/项目改名不再迁移项目子目录（id 前缀解耦）；分组改名仅重命名分组顶层目录

### 5 大板块（sections 表）
| key | 板块名（默认） | 主标题/副标题配置入口 |
|---|---|---|
| basic | 基础信息 | 基础信息页（hero 无标题） |
| summary | 个人概要 | 个人概要页 |
| projects | 精选项目 | 3.1 项目分类页顶部「板块标题」块 |
| experience | 工作经历 | 工作经历页顶部「板块标题」块 |
| skills | 专业技能 | 专业技能页 |

- **板块名 + 序号**在系统设置「板块名称」面板统一配置（3×3 网格），一处生效三处：前台顶部导航、内容页大板块名称与顺序、后台左侧导航顺序（`sections.sort` 字段，前台隐藏 system）
- 前台无独立 AIGC 区：独立专区分类（如「AIGC 经历」）作为精选项目大板块下的分类显示，分类名作小节标题；项目富文本详情统一渲染在图片**下方**
- 前台字号阶梯变量化（--fs-*，:root 统一管理）：导航 14 / 眉题 12.5 / 区题 30 / 分类名 24 / 分组 20 / 条目 16.5 / 图注 12.5 / 卡片正文 15.5 / 页脚 13；正文 16 / 行高 1.75，段落与区间距同步收紧（section 88px、条目 15/13、卡片 30×28）

### 迁移
`db.init_db()` 自动建 `classifications`/`sections` 表并给 `categories` 加 `classification_id`；
初始数据：2 个一级分类（精选项目=projects / AIGC 经历=aigc），6 分组按 kind 自动归位。


### PBOOT 式内容排序（v9）
- **内容排序**：`ORDER BY pub_date DESC, sort ASC, id DESC`——日期（可精确到分钟，前台显示到日）为主，同日期按序号升序（默认 255，254 在 255 前），同日同号按 id 倒序（新添加在前）
- `projects` 新增 `pub_date`（YYYY-MM-DD HH:MM）；新建项目自动填当天 12:00 + 序号 255
- 历史 69 条标题中的日期已迁移到 `pub_date`（默认 12:00），标题去掉日期、保留括号内地点等剩余文字（如「日本旅游局宣传片（九州）」）；5 条无日期信息留空排最后
- 分类/分组排序保存时自动归一为连续 1-N（同 sections）
