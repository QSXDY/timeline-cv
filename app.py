"""yfq-resume: Flask + SQLite 个人简历站（前台 + 后台 /adminc）。

启动：python app.py  →  前台 http://127.0.0.1:5000  后台 /adminc
"""

import datetime
import hashlib
import os
import re
import secrets
import shutil
import sys
import uuid
from functools import wraps

from flask import (
    Flask,
    abort,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from PIL import Image

import db

BASE = os.path.dirname(os.path.abspath(__file__))
UPLOADS = os.path.join(BASE, "static", "uploads")
ALLOWED_EXT = {"jpg", "jpeg", "png", "gif", "webp"}
ALLOWED_VIDEO_EXT = {"mp4", "m4v", "mov", "webm"}
MAX_UPLOAD = 500 * 1024 * 1024

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD


@app.after_request
def add_cache_headers(resp):
    """静态资源缓存策略：uploads（uuid 文件名永不变）长缓存 1 年；css/js 等改为协商缓存（开发期改动即时生效）。"""
    if resp.status_code == 200 and request.path.startswith("/static/"):
        if "/uploads/" in request.path:
            resp.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        else:
            resp.headers["Cache-Control"] = "no-cache"
    return resp


def load_or_create_secret():
    p = os.environ.get("SECRET_KEY_FILE", os.path.join(BASE, "secret.key"))
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            return f.read().strip()
    s = secrets.token_hex(32)
    with open(p, "w", encoding="utf-8") as f:
        f.write(s)
    return s


app.secret_key = load_or_create_secret()


@app.context_processor
def inject_site_name():
    """后台侧边栏副标题「<姓名>简历」：姓名动态读取基础信息表。"""
    name = "杨芳清"
    try:
        conn = db.get_db()
        row = conn.execute("SELECT name FROM basic_info WHERE id=1").fetchone()
        conn.close()
        if row and row["name"]:
            name = row["name"]
    except Exception:
        pass
    return {"site_name": name}


# ---------------------------------------------------------------- 工具
def slug_dir(name):
    """清洗目录名：去文件系统非法字符，空则回退 untitled。"""
    s = re.sub(r'[\\/:*?"<>|]', "-", str(name)).strip()
    return s or "untitled"


def project_dir(cat_name, pid, proj_title):
    """项目目录：uploads/<分组slug>/<项目id>-<标题slug>/（id 前缀解耦标题与文件系统，改标题不迁移目录）"""
    return os.path.join(UPLOADS, slug_dir(cat_name), f"{pid}-{slug_dir(proj_title)}")


def img_url(cat_name, pid, proj_title, filename):
    path = "uploads/{}/{}/{}".format(
        slug_dir(cat_name), f"{pid}-{slug_dir(proj_title)}", filename
    )
    local = url_for("static", filename=path)
    _load_cdn_cfg()
    if _cdn_cfg["enabled"] and _cdn_cfg["base"]:
        return _cdn_cfg["base"] + local
    return local


# CDN（EdgeOne）配置缓存：系统设置里修改后失效重载
_cdn_cfg = {"loaded": False, "enabled": False, "base": ""}


def _load_cdn_cfg():
    if _cdn_cfg["loaded"]:
        return
    try:
        conn = db.get_db()
        rows = conn.execute("SELECT key, value FROM settings").fetchall()
        conn.close()
        kv = {r["key"]: r["value"] for r in rows}
        _cdn_cfg["enabled"] = kv.get("cdn_enabled") == "1"
        _cdn_cfg["base"] = (kv.get("cdn_base") or "").strip().rstrip("/")
    except Exception:
        pass
    _cdn_cfg["loaded"] = True


def hash_password(password, iterations=260000):
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), bytes.fromhex(salt), iterations
    ).hex()
    return f"pbkdf2_sha256${iterations}${salt}${digest}"


def _ensure_first_run():
    """首次启动自举（幂等，可重复调用）：
    - 确保上传目录存在（干净镜像无 static/uploads）
    - 建空库（无 resume.db 时自动建全表）
    - admin 表为空时创建默认管理员 admin/admin（可用 YFQ_ADMIN_USER / YFQ_ADMIN_PASS
      环境变量覆盖），登录后请在系统设置中立即修改密码。已有数据的库不受影响。"""
    os.makedirs(UPLOADS, exist_ok=True)
    db.init_db()
    try:
        conn = db.get_db()
        n = conn.execute("SELECT COUNT(*) FROM admin").fetchone()[0]
        if n == 0:
            user = os.environ.get("YFQ_ADMIN_USER", "admin")
            pw = os.environ.get("YFQ_ADMIN_PASS", "admin")
            conn.execute(
                "INSERT INTO admin (id, username, password_hash) VALUES (1, ?, ?)",
                (user, hash_password(pw)),
            )
            conn.commit()
            print(f"[init] 已创建默认管理员 {user}（默认密码 {pw}，登录后请立即修改）")
        conn.close()
    except Exception as e:
        print("[init] 管理员检查跳过:", e)


_ensure_first_run()


def _save_webp(im, path, quality=100):
    """图片统一转 WEBP 落盘（quality=100，无视觉损失；保留透明通道）。"""
    if im.mode not in ("RGB", "RGBA"):
        im = im.convert("RGBA") if "transparency" in im.info else im.convert("RGB")
    im.save(path, "WEBP", quality=quality, method=6)


def verify_password(password, stored):
    try:
        algo, iters, salt, digest = stored.split("$")
        if algo != "pbkdf2_sha256":
            return False
        calc = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), bytes.fromhex(salt), int(iters)
        ).hex()
        return secrets.compare_digest(calc, digest)
    except Exception:
        return False


def login_required(f):
    @wraps(f)
    def w(*a, **k):
        if not session.get("admin"):
            return redirect(url_for("admin_login"))
        return f(*a, **k)

    return w


def _cdn_url(u):
    """给静态资源 URL 加 CDN 前缀（未启用则原样返回）。"""
    _load_cdn_cfg()
    if _cdn_cfg["enabled"] and _cdn_cfg["base"] and u.startswith("/"):
        return _cdn_cfg["base"] + u
    return u


def _cdn_html(h):
    """富文本 detail_html 内的 /static/ 路径统一走 CDN（未启用则原样返回）。"""
    _load_cdn_cfg()
    if _cdn_cfg["enabled"] and _cdn_cfg["base"] and h:
        return h.replace("/static/", _cdn_cfg["base"] + "/static/")
    return h


app.jinja_env.filters["slug"] = slug_dir
app.jinja_env.globals["img_url"] = img_url
app.jinja_env.filters["cdn"] = _cdn_url
app.jinja_env.filters["cdn_html"] = _cdn_html


def _clean_editor_orphans(conn, detail_html):
    """项目删除后清理其富文本引用的 _editor 孤儿图片（仍被其他项目引用则保留）。"""
    if not detail_html:
        return
    names = set(re.findall(r"uploads/_editor/([0-9a-f]{12,}\.webp)", detail_html))
    if not names:
        return
    refs = set()
    for row in conn.execute("SELECT detail_html FROM projects").fetchall():
        refs.update(
            re.findall(
                r"uploads/_editor/([0-9a-f]{12,}\.webp)", row["detail_html"] or ""
            )
        )
    for n in names - refs:
        fp = os.path.join(UPLOADS, "_editor", n)
        if os.path.exists(fp):
            try:
                os.remove(fp)
            except OSError:
                pass


def _auto_backup():
    """启动时每日备份一次 SQLite 到 backups/，保留最近 7 份；多进程安全（以日期文件为锁）。"""
    try:
        backup_dir = os.environ.get("RESUME_BACKUP_DIR", os.path.join(BASE, "backups"))
        os.makedirs(backup_dir, exist_ok=True)
        today = datetime.datetime.now().strftime("%Y%m%d")
        marker = os.path.join(backup_dir, "last-" + today)
        if os.path.exists(marker):
            return
        src = os.environ.get("RESUME_DB", os.path.join(BASE, "resume.db"))
        if not os.path.exists(src):
            return
        import shutil as _sh

        dst = os.path.join(backup_dir, f"resume-{today}.db")
        _sh.copy2(src, dst)
        with open(marker, "w", encoding="utf-8") as _f:
            _f.write("1")
        # 清理 7 天前的备份
        import glob

        olds = sorted(glob.glob(os.path.join(backup_dir, "resume-*.db")))[:-7]
        for f in olds:
            try:
                os.remove(f)
            except OSError:
                pass
        print("[backup] ->", dst)
    except Exception as e:
        print("[backup] skip:", e)


_SEC_ANCHOR = {
    "basic": "top",
    "summary": "summary",
    "projects": "projects",
    "experience": "exp",
    "skills": "skill",
}


@app.context_processor
def inject_sections():
    """板块配置全局注入：sections(dict) + nav_items(按 sort 排序，含锚点)。"""
    try:
        conn = db.get_db()
        rows = conn.execute("SELECT * FROM sections ORDER BY sort, key").fetchall()
        conn.close()
        sec = {r["key"]: r for r in rows}
        nav_items = []
        for r in rows:
            item = dict(r)
            item["anchor"] = _SEC_ANCHOR.get(r["key"], "")
            nav_items.append(item)
    except Exception:
        sec, nav_items = {}, []
    return {"sections": sec, "nav_items": nav_items}


_ADMIN_ACTIVE = (
    ("/adminc/basic", "basic"),
    ("/adminc/summary", "summary"),
    ("/adminc/classifications", "classifications"),
    ("/adminc/categories", "categories"),
    ("/adminc/projects", "projects"),
    ("/adminc/experience", "experience"),
    ("/adminc/skills", "skills"),
    ("/adminc/settings", "settings"),
)


@app.context_processor
def inject_admin_active():
    """后台侧边栏高亮：按当前路径自动匹配，含子路径（如项目编辑页归 projects）。"""
    p = request.path
    for prefix, key in _ADMIN_ACTIVE:
        if p == prefix or p.startswith(prefix + "/"):
            return {"active": key}
    return {"active": ""}


# ---------------------------------------------------------------- CSRF
@app.before_request
def csrf_protect():
    if session.get("csrf") is None:
        session["csrf"] = secrets.token_hex(16)
    if request.method == "POST":
        token = session.get("csrf")
        form = request.form.get("_csrf")
        if not token or not form or not secrets.compare_digest(token, form):
            abort(400, description="CSRF 校验失败，请刷新页面重试")


# ---------------------------------------------------------------- 前台
def load_site_data():
    """前台数据：按一级分类聚合分组/项目；groups/aigcs 按 section 拆出（兼容旧模板）。"""
    conn = db.get_db()
    info = conn.execute("SELECT * FROM basic_info WHERE id=1").fetchone()
    summary = conn.execute("SELECT * FROM summary WHERE id=1").fetchone()
    cards = conn.execute("SELECT * FROM summary_cards ORDER BY sort, id").fetchall()
    classifications = []
    for cl in conn.execute(
        "SELECT * FROM classifications ORDER BY sort, id"
    ).fetchall():
        d = dict(cl)
        d["groups"] = []
        for cat in conn.execute(
            "SELECT * FROM categories WHERE classification_id=? ORDER BY sort, id",
            (cl["id"],),
        ).fetchall():
            g = dict(cat)
            g["projects"] = [
                dict(p)
                for p in conn.execute(
                    "SELECT * FROM projects WHERE category_id=? ORDER BY pub_date DESC, sort, id DESC",
                    (cat["id"],),
                ).fetchall()
            ]
            for p in g["projects"]:
                p["images"] = [
                    dict(i)
                    for i in conn.execute(
                        "SELECT * FROM images WHERE project_id=? ORDER BY sort, id",
                        (p["id"],),
                    ).fetchall()
                ]
                p["n"] = len(p["images"])
            d["groups"].append(g)
        classifications.append(d)
    exps = [
        dict(e)
        for e in conn.execute("SELECT * FROM experiences ORDER BY sort, id").fetchall()
    ]
    skills = conn.execute("SELECT * FROM skills WHERE id=1").fetchone()
    skill_cards = [
        dict(c)
        for c in conn.execute("SELECT * FROM skill_cards ORDER BY sort, id").fetchall()
    ]
    for c in skill_cards:
        c["tags"] = [
            dict(t)
            for t in conn.execute(
                "SELECT * FROM skill_tags WHERE card_id=? ORDER BY sort, id", (c["id"],)
            ).fetchall()
        ]
    conn.close()
    return (info, summary, cards, classifications, exps, skills, skill_cards)


@app.get("/")
def index():
    data = load_site_data()
    return render_template(
        "index.html",
        info=data[0],
        summary=data[1],
        cards=data[2],
        classifications=data[3],
        exps=data[4],
        skills=data[5],
        skill_cards=data[6],
    )


# ---------------------------------------------------------------- 登录
@app.route("/adminc/login", methods=["GET", "POST"])
def admin_login():
    if session.get("admin"):
        return redirect(url_for("admin_basic"))
    if request.method == "POST":
        # 轻量限速：5 次失败锁定 15 分钟（基于 session）
        import time as _t

        now = _t.time()
        if session.get("lock_until") and now < session.get("lock_until", 0):
            flash("尝试次数过多，请 15 分钟后再试")
            return render_template("admin/login.html")
        u = request.form.get("username", "").strip()
        p = request.form.get("password", "")
        conn = db.get_db()
        row = conn.execute("SELECT * FROM admin WHERE username=?", (u,)).fetchone()
        conn.close()
        if row and verify_password(p, row["password_hash"]):
            session.pop("fail", None)
            session.pop("lock_until", None)
            session["admin"] = row["username"]
            session.pop("csrf", None)
            return redirect(url_for("admin_basic"))
        session["fail"] = session.get("fail", 0) + 1
        if session.get("fail", 0) >= 5:
            session["lock_until"] = now + 900
            session["fail"] = 0
            flash("连续失败 5 次，账号锁定 15 分钟")
        else:
            flash("账号或密码错误")
    return render_template("admin/login.html")


@app.post("/adminc/logout")
def admin_logout():
    session.clear()
    return redirect(url_for("admin_login"))


@app.get("/adminc")
@login_required
def admin_home():
    return redirect(url_for("admin_basic"))


# ---------------------------------------------------------------- 基础信息
@app.route("/adminc/basic", methods=["GET", "POST"])
@login_required
def admin_basic():
    conn = db.get_db()
    if request.method == "POST":
        action = request.form.get("action", "")
        if action == "upload_avatar":
            f = request.files.get("avatar")
            if not (f and f.filename):
                conn.close()
                flash("未选择文件")
                return redirect(url_for("admin_basic"))
            ext = f.filename.rsplit(".", 1)[-1].lower() if "." in f.filename else ""
            if ext not in ALLOWED_EXT:
                conn.close()
                flash("头像格式不支持（jpg/png/gif/webp）")
                return redirect(url_for("admin_basic"))
            f.stream.seek(0)
            try:
                img = Image.open(f.stream)
                img.load()
            except Exception:
                conn.close()
                flash("头像文件损坏，请换一张")
                return redirect(url_for("admin_basic"))
            av_dir = os.path.join(UPLOADS, "_avatar")
            os.makedirs(av_dir, exist_ok=True)
            row = conn.execute("SELECT avatar FROM basic_info WHERE id=1").fetchone()
            if row and row["avatar"]:
                old_p = os.path.join(av_dir, row["avatar"])
                if os.path.isfile(old_p):
                    os.remove(old_p)
            filename = uuid.uuid4().hex[:12] + ".webp"
            _save_webp(img, os.path.join(av_dir, filename))
            conn.execute("UPDATE basic_info SET avatar=? WHERE id=1", (filename,))
            conn.commit()
            flash("头像已更新")
            conn.close()
            return redirect(url_for("admin_basic"))
        fields = [
            "name",
            "role",
            "lead",
            "intent",
            "salary",
            "location",
            "email",
            "profile",
        ]
        vals = {k: request.form.get(k, "").strip() for k in fields}
        conn.execute(
            """UPDATE basic_info SET name=?, role=?, lead=?, intent=?,
                        salary=?, location=?, email=?, profile=? WHERE id=1""",
            tuple(vals[k] for k in fields),
        )
        f = request.files.get("avatar")
        if f and f.filename:
            ext = f.filename.rsplit(".", 1)[-1].lower() if "." in f.filename else ""
            if ext not in ALLOWED_EXT:
                conn.close()
                flash("头像格式不支持（jpg/png/gif/webp）")
                return redirect(url_for("admin_basic"))
            f.stream.seek(0)
            try:
                img = Image.open(f.stream)
                img.load()
            except Exception:
                conn.close()
                flash("头像文件损坏，请换一张")
                return redirect(url_for("admin_basic"))
            av_dir = os.path.join(UPLOADS, "_avatar")
            os.makedirs(av_dir, exist_ok=True)
            row = conn.execute("SELECT avatar FROM basic_info WHERE id=1").fetchone()
            if row and row["avatar"]:
                old_p = os.path.join(av_dir, row["avatar"])
                if os.path.isfile(old_p):
                    os.remove(old_p)
            filename = uuid.uuid4().hex[:12] + ".webp"
            _save_webp(img, os.path.join(av_dir, filename))
            conn.execute("UPDATE basic_info SET avatar=? WHERE id=1", (filename,))
            flash("基础信息已保存，头像已更新")
        elif request.form.get("delete_avatar"):
            row = conn.execute("SELECT avatar FROM basic_info WHERE id=1").fetchone()
            if row and row["avatar"]:
                p = os.path.join(UPLOADS, "_avatar", row["avatar"])
                if os.path.isfile(p):
                    os.remove(p)
                conn.execute("UPDATE basic_info SET avatar='' WHERE id=1")
            flash("基础信息已保存，头像已删除")
        else:
            flash("基础信息已保存")
        conn.commit()
        return redirect(url_for("admin_basic"))
    info = conn.execute("SELECT * FROM basic_info WHERE id=1").fetchone()
    conn.close()
    return render_template("admin/basic.html", info=info)


# ---------------------------------------------------------------- 概要
@app.route("/adminc/summary", methods=["GET", "POST"])
@login_required
def admin_summary():
    conn = db.get_db()
    if request.method == "POST":
        action = request.form.get("action")
        if action == "save":
            ti = request.form.get("title", "").strip()
            sub = request.form.get("subtitle", "").strip()
            conn.execute("UPDATE summary SET title=?, subtitle=? WHERE id=1", (ti, sub))
            conn.execute(
                "UPDATE sections SET title=?, subtitle=? WHERE key='summary'", (ti, sub)
            )
            conn.commit()
            flash("概要已保存")
        elif action == "add_card":
            t = request.form.get("title", "").strip()
            c = request.form.get("content", "").strip()
            if t and c:
                m = conn.execute(
                    "SELECT COALESCE(MAX(sort), -1) m FROM summary_cards"
                ).fetchone()["m"]
                conn.execute(
                    "INSERT INTO summary_cards (title, content, sort) VALUES (?, ?, ?)",
                    (t, c, m + 1),
                )
                conn.commit()
                flash("卡片已添加")
            else:
                flash("卡片标题和内容不能为空")
        return redirect(url_for("admin_summary"))
    summary = conn.execute("SELECT * FROM summary WHERE id=1").fetchone()
    cards = conn.execute("SELECT * FROM summary_cards ORDER BY sort, id").fetchall()
    conn.close()
    return render_template("admin/summary.html", summary=summary, cards=cards)


@app.post("/adminc/summary/cards/<int:cid>/delete")
@login_required
def delete_summary_card(cid):
    conn = db.get_db()
    conn.execute("DELETE FROM summary_cards WHERE id=?", (cid,))
    conn.commit()
    conn.close()
    flash("卡片已删除")
    return redirect(url_for("admin_summary"))


# ---------------------------------------------------------------- 3.1 项目分类（一级）
@app.route("/adminc/classifications", methods=["GET", "POST"])
@login_required
def admin_classifications():
    conn = db.get_db()
    if request.method == "POST":
        action = request.form.get("action")
        if action in ("add", "edit"):
            cid = request.form.get("id", type=int)
            name = request.form.get("name", "").strip()
            sort = request.form.get("sort", type=int) or 0
            if not name:
                flash("分类名不能为空")
            else:
                others = conn.execute(
                    "SELECT id, name FROM classifications WHERE id != ?", (cid or 0,)
                ).fetchall()
                if any(o["name"] == name for o in others):
                    flash("分类名已存在，请换一个")
                elif cid:
                    conn.execute(
                        "UPDATE classifications SET name=?, sort=? WHERE id=?",
                        (name, sort, cid),
                    )
                    flash("分类已保存")
                else:
                    conn.execute(
                        "INSERT INTO classifications (name, sort) VALUES (?, ?)",
                        (name, sort),
                    )
                    flash("分类已添加")
            conn.commit()
        elif action == "delete":
            cid = request.form.get("id", type=int)
            # 级联删除：先删该分类下每个分组的磁盘目录，再删分组（外键级联项目/图片），最后删分类
            for cat in conn.execute(
                "SELECT * FROM categories WHERE classification_id=?", (cid,)
            ).fetchall():
                for p in conn.execute(
                    "SELECT id, title, detail_html FROM projects WHERE category_id=?",
                    (cat["id"],),
                ).fetchall():
                    _clean_editor_orphans(conn, p["detail_html"])
                    d = project_dir(cat["name"], p["id"], p["title"])
                    if os.path.isdir(d):
                        shutil.rmtree(d)
                conn.execute("DELETE FROM categories WHERE id=?", (cat["id"],))
            conn.execute("DELETE FROM classifications WHERE id=?", (cid,))
            conn.commit()
            flash("分类已删除（含其下全部分组、项目与图片）")
        elif action == "section_title":
            ti = request.form.get("title", "").strip()
            sub = request.form.get("subtitle", "").strip()
            conn.execute(
                "UPDATE sections SET title=?, subtitle=? WHERE key='projects'",
                (ti, sub),
            )
            conn.commit()
            flash("精选项目区标题已保存")
        for i, r in enumerate(
            conn.execute("SELECT id FROM classifications ORDER BY sort, id").fetchall(),
            1,
        ):
            conn.execute("UPDATE classifications SET sort=? WHERE id=?", (i, r["id"]))
        conn.commit()
        return redirect(url_for("admin_classifications"))
    cls = [
        dict(c)
        for c in conn.execute(
            "SELECT * FROM classifications ORDER BY sort, id"
        ).fetchall()
    ]
    for c in cls:
        c["n"] = conn.execute(
            "SELECT COUNT(*) n FROM categories WHERE classification_id=?", (c["id"],)
        ).fetchone()["n"]
    psec = conn.execute("SELECT * FROM sections WHERE key='projects'").fetchone()
    conn.close()
    return render_template("admin/classifications.html", cls=cls, psec=psec)


# ---------------------------------------------------------------- 3.2 项目分组
@app.route("/adminc/categories", methods=["GET", "POST"])
@login_required
def admin_categories():
    conn = db.get_db()
    if request.method == "POST":
        action = request.form.get("action")
        if action in ("add", "edit"):
            cid = request.form.get("id", type=int)
            name = request.form.get("name", "").strip()
            subtitle = request.form.get("subtitle", "").strip()
            tags = request.form.get("tags", "").strip()
            classification_id = request.form.get("classification_id", type=int) or 0
            sort = request.form.get("sort", type=int) or 0
            if not name:
                flash("分组名不能为空")
            elif (
                classification_id
                and not conn.execute(
                    "SELECT id FROM classifications WHERE id=?", (classification_id,)
                ).fetchone()
            ):
                flash("所属分类不存在")
            else:
                others = conn.execute(
                    "SELECT id, name FROM categories WHERE id != ?", (cid or 0,)
                ).fetchall()
                if any(slug_dir(o["name"]) == slug_dir(name) for o in others):
                    flash("分组名与已有分组冲突，请换一个")
                elif cid:
                    old = conn.execute(
                        "SELECT * FROM categories WHERE id=?", (cid,)
                    ).fetchone()
                    if old and old["name"] != name:
                        o = os.path.join(UPLOADS, slug_dir(old["name"]))
                        n = os.path.join(UPLOADS, slug_dir(name))
                        if os.path.exists(o):
                            if o != n and os.path.exists(n):
                                flash("目标目录已存在，无法改名")
                                conn.close()
                                return redirect(url_for("admin_categories"))
                            if o != n:
                                os.rename(o, n)
                    conn.execute(
                        """UPDATE categories SET name=?, subtitle=?, tags=?,
                                    classification_id=?, sort=? WHERE id=?""",
                        (name, subtitle, tags, classification_id, sort, cid),
                    )
                    flash("分组已保存")
                else:
                    conn.execute(
                        """INSERT INTO categories (name, subtitle, tags, classification_id, sort)
                                    VALUES (?, ?, ?, ?, ?)""",
                        (name, subtitle, tags, classification_id, sort),
                    )
                    flash("分组已添加")
            conn.commit()
            for i, r in enumerate(
                conn.execute("SELECT id FROM categories ORDER BY sort, id").fetchall(),
                1,
            ):
                conn.execute("UPDATE categories SET sort=? WHERE id=?", (i, r["id"]))
            conn.commit()
        elif action == "delete":
            cid = request.form.get("id", type=int)
            cat = conn.execute("SELECT * FROM categories WHERE id=?", (cid,)).fetchone()
            if cat:
                for p in conn.execute(
                    "SELECT id, title, detail_html FROM projects WHERE category_id=?",
                    (cid,),
                ).fetchall():
                    _clean_editor_orphans(conn, p["detail_html"])
                    d = project_dir(cat["name"], p["id"], p["title"])
                    if os.path.isdir(d):
                        shutil.rmtree(d)
                conn.execute("DELETE FROM categories WHERE id=?", (cid,))
                conn.commit()
                flash("分类已删除（含全部项目与图片）")
        return redirect(url_for("admin_categories"))
    cats = [
        dict(c)
        for c in conn.execute("SELECT * FROM categories ORDER BY sort, id").fetchall()
    ]
    clmap = {
        r["id"]: r["name"]
        for r in conn.execute("SELECT id, name FROM classifications").fetchall()
    }
    for c in cats:
        c["n"] = conn.execute(
            "SELECT COUNT(*) n FROM projects WHERE category_id=?", (c["id"],)
        ).fetchone()["n"]
        c["cl_name"] = clmap.get(c["classification_id"], "未归属")
    cls = [
        dict(r)
        for r in conn.execute(
            "SELECT * FROM classifications ORDER BY sort, id"
        ).fetchall()
    ]
    conn.close()
    return render_template("admin/categories.html", cats=cats, cls=cls)


# ---------------------------------------------------------------- 项目
@app.route("/adminc/projects", methods=["GET", "POST"])
@login_required
def admin_projects():
    conn = db.get_db()
    if request.method == "POST":
        cid = request.form.get("category_id", type=int)
        title = request.form.get("title", "").strip()
        if cid and title:
            cat = conn.execute("SELECT * FROM categories WHERE id=?", (cid,)).fetchone()
            if not cat:
                flash("分类不存在")
            else:
                today = datetime.datetime.now().strftime("%Y-%m-%d 12:00")
                conn.execute(
                    "INSERT INTO projects (category_id, title, desc, detail_html, pub_date, sort) VALUES (?, ?, '', '', ?, 255)",
                    (cid, title, today),
                )
                conn.commit()
                pid = conn.execute("SELECT last_insert_rowid() id").fetchone()["id"]
                conn.close()
                return redirect(url_for("admin_project_edit", pid=pid))
        flash("请选择分类并填写项目标题")
        return redirect(url_for("admin_projects"))
    cls = [
        dict(r)
        for r in conn.execute(
            "SELECT * FROM classifications ORDER BY sort, id"
        ).fetchall()
    ]
    for cl in cls:
        cl["groups"] = [
            dict(r)
            for r in conn.execute(
                "SELECT * FROM categories WHERE classification_id=? ORDER BY sort, id",
                (cl["id"],),
            ).fetchall()
        ]
    clid = request.args.get("classification_id", type=int)
    cid = request.args.get("category_id", type=int)
    projs = []
    if cid:
        projs = [
            dict(p)
            for p in conn.execute(
                "SELECT p.*, (SELECT COUNT(*) FROM images i WHERE i.project_id=p.id) n "
                "FROM projects p WHERE category_id=? ORDER BY p.pub_date DESC, p.sort, p.id DESC",
                (cid,),
            ).fetchall()
        ]
    conn.close()
    return render_template(
        "admin/projects.html", cls=cls, clid=clid, cid=cid, projs=projs
    )


@app.route("/adminc/projects/<int:pid>/edit", methods=["GET", "POST"])
@login_required
def admin_project_edit(pid):
    conn = db.get_db()
    proj = conn.execute("SELECT * FROM projects WHERE id=?", (pid,)).fetchone()
    if not proj:
        abort(404)
    cat = conn.execute(
        "SELECT * FROM categories WHERE id=?", (proj["category_id"],)
    ).fetchone()
    if request.method == "POST":
        action = request.form.get("action", "save")
        if action == "save":
            title = request.form.get("title", "").strip()
            desc = request.form.get("desc", "").strip()
            detail = request.form.get("detail_html", "")
            pub = request.form.get("pub_date", "").strip().replace("T", " ")
            sort = request.form.get("sort", type=int)
            if sort is None:
                sort = 255
            cid = request.form.get("category_id", type=int)
            new_cat = conn.execute(
                "SELECT * FROM categories WHERE id=?", (cid,)
            ).fetchone()
            if not title or not new_cat:
                flash("标题和分类不能为空")
            else:
                others = conn.execute(
                    "SELECT id, title FROM projects WHERE category_id=? AND id != ?",
                    (new_cat["id"], pid),
                ).fetchall()
                if any(slug_dir(o["title"]) == slug_dir(title) for o in others):
                    flash("同一分类下已有同名项目，请换一个")
                else:
                    try:
                        # 目录与标题解耦（id 前缀），改标题/分组不再迁移磁盘目录
                        conn.execute(
                            """UPDATE projects SET category_id=?, title=?, desc=?, detail_html=?, pub_date=?, sort=?
                                        WHERE id=?""",
                            (new_cat["id"], title, desc, detail, pub, sort, pid),
                        )
                        conn.commit()
                        flash("项目已保存")
                        return redirect(url_for("admin_project_edit", pid=pid))
                    except ValueError as e:
                        flash(str(e))
        elif action == "delete":
            _clean_editor_orphans(conn, proj["detail_html"])
            d = project_dir(cat["name"], pid, proj["title"])
            if os.path.isdir(d):
                shutil.rmtree(d)
            conn.execute("DELETE FROM projects WHERE id=?", (pid,))
            conn.commit()
            conn.close()
            flash("项目已删除（含其图片）")
            return redirect(url_for("admin_projects"))
    # GET: 重新加载（保存后可能换了分类）
    proj = conn.execute("SELECT * FROM projects WHERE id=?", (pid,)).fetchone()
    cat = conn.execute(
        "SELECT * FROM categories WHERE id=?", (proj["category_id"],)
    ).fetchone()
    images = [
        dict(i)
        for i in conn.execute(
            "SELECT * FROM images WHERE project_id=? ORDER BY sort, id", (pid,)
        ).fetchall()
    ]
    cls = [
        dict(r)
        for r in conn.execute(
            "SELECT * FROM classifications ORDER BY sort, id"
        ).fetchall()
    ]
    for cl in cls:
        cl["groups"] = [
            dict(r)
            for r in conn.execute(
                "SELECT * FROM categories WHERE classification_id=? ORDER BY sort, id",
                (cl["id"],),
            ).fetchall()
        ]
    conn.close()
    land = [i for i in images if i["orientation"] == "h"]
    port = [i for i in images if i["orientation"] == "v"]
    return render_template(
        "admin/project_edit.html",
        proj=proj,
        cat=cat,
        cls=cls,
        cl_id=cat["classification_id"] if cat else 0,
        land=land,
        port=port,
    )


@app.post("/adminc/projects/<int:pid>/images")
@login_required
def upload_image(pid):
    conn = db.get_db()
    proj = conn.execute("SELECT * FROM projects WHERE id=?", (pid,)).fetchone()
    if not proj:
        conn.close()
        abort(404)
    cat = conn.execute(
        "SELECT * FROM categories WHERE id=?", (proj["category_id"],)
    ).fetchone()
    f = request.files.get("file")
    orientation = request.form.get("orientation", "h")
    caption = request.form.get("caption", "").strip()
    if orientation not in ("h", "v"):
        orientation = "h"
    if not f or not f.filename:
        flash("请选择图片文件")
        return redirect(url_for("admin_project_edit", pid=pid))
    ext = f.filename.rsplit(".", 1)[-1].lower() if "." in f.filename else ""
    is_video = ext in ALLOWED_VIDEO_EXT
    if ext not in ALLOWED_EXT and not is_video:
        flash("仅支持图片 jpg/png/gif/webp 或视频 mp4/m4v/mov/webm")
        return redirect(url_for("admin_project_edit", pid=pid))
    if is_video:
        # 视频不转码，直接落盘
        name = uuid.uuid4().hex[:12] + "." + ext
        d = project_dir(cat["name"], pid, proj["title"])
        os.makedirs(d, exist_ok=True)
        f.save(os.path.join(d, name))
        mtype = "video"
        flash("视频已上传")
    else:
        try:
            f.stream.seek(0)
            im = Image.open(f.stream)
            im.load()
        except Exception:
            flash("文件不是有效图片")
            return redirect(url_for("admin_project_edit", pid=pid))
        name = uuid.uuid4().hex[:12] + ".webp"
        d = project_dir(cat["name"], pid, proj["title"])
        os.makedirs(d, exist_ok=True)
        _save_webp(im, os.path.join(d, name))
        mtype = "image"
        flash("图片已上传")
    m = conn.execute(
        "SELECT COALESCE(MAX(sort), -1) m FROM images WHERE project_id=?", (pid,)
    ).fetchone()["m"]
    conn.execute(
        "INSERT INTO images (project_id, filename, orientation, type, caption, sort) VALUES (?, ?, ?, ?, ?, ?)",
        (pid, name, orientation, mtype, caption, m + 1),
    )
    conn.commit()
    conn.close()
    return redirect(url_for("admin_project_edit", pid=pid))


@app.post("/adminc/projects/<int:pid>/images/<int:iid>/update")
@login_required
def update_image(iid, pid):
    conn = db.get_db()
    img = conn.execute(
        "SELECT * FROM images WHERE id=? AND project_id=?", (iid, pid)
    ).fetchone()
    if not img:
        conn.close()
        abort(404)
    caption = request.form.get("caption", "").strip()
    orientation = request.form.get("orientation", img["orientation"])
    if orientation not in ("h", "v"):
        orientation = img["orientation"]
    conn.execute(
        "UPDATE images SET caption=?, orientation=? WHERE id=?",
        (caption, orientation, iid),
    )
    conn.commit()
    conn.close()
    flash("图片描述已更新")
    return redirect(url_for("admin_project_edit", pid=pid))


@app.post("/adminc/projects/<int:pid>/images/<int:iid>/delete")
@login_required
def delete_image(iid, pid):
    conn = db.get_db()
    img = conn.execute(
        "SELECT * FROM images WHERE id=? AND project_id=?", (iid, pid)
    ).fetchone()
    if img:
        proj = conn.execute("SELECT * FROM projects WHERE id=?", (pid,)).fetchone()
        cat = conn.execute(
            "SELECT * FROM categories WHERE id=?", (proj["category_id"],)
        ).fetchone()
        p = os.path.join(project_dir(cat["name"], pid, proj["title"]), img["filename"])
        if os.path.isfile(p):
            os.remove(p)
        conn.execute("DELETE FROM images WHERE id=?", (iid,))
        conn.commit()
        flash("图片已删除")
    conn.close()
    return redirect(url_for("admin_project_edit", pid=pid))


# wangEditor 图片上传
@app.post("/adminc/upload")
@login_required
def editor_upload():
    f = request.files.get("file")
    if not f or not f.filename:
        return {"errno": 1, "message": "未收到文件"}
    ext = f.filename.rsplit(".", 1)[-1].lower() if "." in f.filename else ""
    if ext not in ALLOWED_EXT:
        return {"errno": 1, "message": "不支持的格式"}
    try:
        f.stream.seek(0)
        im = Image.open(f.stream)
        im.load()
    except Exception:
        return {"errno": 1, "message": "不是有效图片"}
    name = uuid.uuid4().hex[:12] + ".webp"
    d = os.path.join(UPLOADS, "_editor")
    os.makedirs(d, exist_ok=True)
    _save_webp(im, os.path.join(d, name))
    return {"errno": 0, "data": [url_for("static", filename="uploads/_editor/" + name)]}


# ---------------------------------------------------------------- 工作经历
@app.route("/adminc/experience", methods=["GET", "POST"])
@login_required
def admin_experience():
    conn = db.get_db()
    if request.method == "POST":
        action = request.form.get("action")
        eid = request.form.get("id", type=int)
        if action in ("add", "edit"):
            position = request.form.get("position", "").strip()
            org = request.form.get("org", "").strip()
            org_desc = request.form.get("org_desc", "").strip()
            years = request.form.get("years", "").strip()
            content = request.form.get("content", "").strip()
            detail = request.form.get("detail_html", "")
            if not position:
                flash("职位不能为空")
            elif eid:
                conn.execute(
                    """UPDATE experiences SET position=?, org=?, org_desc=?, years=?, content=?, detail_html=?
                                WHERE id=?""",
                    (position, org, org_desc, years, content, detail, eid),
                )
                flash("经历已保存")
            else:
                m = conn.execute(
                    "SELECT COALESCE(MAX(sort), -1) m FROM experiences"
                ).fetchone()["m"]
                conn.execute(
                    """INSERT INTO experiences (position, org, org_desc, years, content, detail_html, sort)
                                VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (position, org, org_desc, years, content, detail, m + 1),
                )
                flash("经历已添加")
            conn.commit()
        elif action == "delete":
            eid = request.form.get("id", type=int)
            conn.execute("DELETE FROM experiences WHERE id=?", (eid,))
            conn.commit()
            flash("经历已删除")
        elif action == "section_title":
            ti = request.form.get("title", "").strip()
            conn.execute("UPDATE sections SET title=? WHERE key='experience'", (ti,))
            conn.commit()
            flash("板块标题已保存")
        return redirect(url_for("admin_experience"))
    exps = [
        dict(e)
        for e in conn.execute("SELECT * FROM experiences ORDER BY sort, id").fetchall()
    ]
    edit = None
    edit_id = request.args.get("edit", type=int)
    if edit_id:
        edit = conn.execute(
            "SELECT * FROM experiences WHERE id=?", (edit_id,)
        ).fetchone()
    exp_sec = conn.execute("SELECT * FROM sections WHERE key='experience'").fetchone()
    conn.close()
    return render_template(
        "admin/experience.html", exps=exps, edit=edit, exp_sec=exp_sec
    )


# ---------------------------------------------------------------- 技能
@app.route("/adminc/skills", methods=["GET", "POST"])
@login_required
def admin_skills():
    conn = db.get_db()
    if request.method == "POST":
        action = request.form.get("action")
        if action == "save":
            conn.execute(
                "UPDATE skills SET title=?, subtitle=? WHERE id=1",
                (
                    request.form.get("title", "").strip(),
                    request.form.get("subtitle", "").strip(),
                ),
            )
            conn.execute(
                "UPDATE sections SET title=?, subtitle=? WHERE key='skills'",
                (
                    request.form.get("title", "").strip(),
                    request.form.get("subtitle", "").strip(),
                ),
            )
            conn.commit()
            flash("技能区已保存")
        elif action == "add_card":
            t = request.form.get("title", "").strip()
            if t:
                m = conn.execute(
                    "SELECT COALESCE(MAX(sort), -1) m FROM skill_cards"
                ).fetchone()["m"]
                conn.execute(
                    "INSERT INTO skill_cards (title, sort) VALUES (?, ?)", (t, m + 1)
                )
                conn.commit()
                flash("卡片已添加")
        elif action == "delete_card":
            cid = request.form.get("id", type=int)
            conn.execute("DELETE FROM skill_cards WHERE id=?", (cid,))
            conn.commit()
            flash("卡片已删除")
        elif action == "add_tag":
            cid = request.form.get("card_id", type=int)
            name = request.form.get("name", "").strip()
            if cid and name:
                m = conn.execute(
                    "SELECT COALESCE(MAX(sort), -1) m FROM skill_tags WHERE card_id=?",
                    (cid,),
                ).fetchone()["m"]
                conn.execute(
                    "INSERT INTO skill_tags (card_id, name, sort) VALUES (?, ?, ?)",
                    (cid, name, m + 1),
                )
                conn.commit()
                flash("技术标签已添加")
        elif action == "delete_tag":
            tid = request.form.get("id", type=int)
            conn.execute("DELETE FROM skill_tags WHERE id=?", (tid,))
            conn.commit()
            flash("技术标签已删除")
        return redirect(url_for("admin_skills"))
    skills = conn.execute("SELECT * FROM skills WHERE id=1").fetchone()
    cards = [
        dict(c)
        for c in conn.execute("SELECT * FROM skill_cards ORDER BY sort, id").fetchall()
    ]
    for c in cards:
        c["tags"] = [
            dict(t)
            for t in conn.execute(
                "SELECT * FROM skill_tags WHERE card_id=? ORDER BY sort, id", (c["id"],)
            ).fetchall()
        ]
    conn.close()
    return render_template("admin/skills.html", skills=skills, cards=cards)


@app.route("/adminc/settings", methods=["GET", "POST"])
@login_required
def admin_settings():
    conn = db.get_db()
    if request.method == "POST":
        action = request.form.get("action", "")
        if action == "password":
            cur = request.form.get("current", "")
            new = request.form.get("new", "")
            confirm = request.form.get("confirm", "")
            row = conn.execute("SELECT password_hash FROM admin WHERE id=1").fetchone()
            if not row or not verify_password(cur, row["password_hash"]):
                flash("当前密码不正确")
            elif len(new) < 6:
                flash("新密码至少 6 位")
            elif new != confirm:
                flash("两次输入的新密码不一致")
            else:
                conn.execute(
                    "UPDATE admin SET password_hash=? WHERE id=1", (hash_password(new),)
                )
                conn.commit()
                flash("密码已更新")
        elif action == "cdn":
            enabled = "1" if request.form.get("cdn_enabled") == "on" else "0"
            base = (request.form.get("cdn_base") or "").strip().rstrip("/")
            conn.execute(
                "INSERT INTO settings (key, value) VALUES ('cdn_enabled', ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (enabled,),
            )
            conn.execute(
                "INSERT INTO settings (key, value) VALUES ('cdn_base', ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (base,),
            )
            conn.commit()
            _cdn_cfg["loaded"] = False
            flash("CDN 设置已保存")
        elif action == "sections":
            keys = ("basic", "summary", "projects", "experience", "skills", "system")
            items = []
            for k in keys:
                nav = request.form.get("nav_" + k, "").strip()
                sort = request.form.get("sort_" + k, type=int) or 0
                items.append((k, nav, sort))
            items.sort(key=lambda x: (x[2], x[0]))
            for i, (k, nav, _sort) in enumerate(items, 1):
                conn.execute(
                    "UPDATE sections SET nav_label=?, sort=? WHERE key=?", (nav, i, k)
                )
            conn.commit()
            flash(f"板块名称与顺序已保存（序号已自动归一为连续 1-{len(items)}）")
        return redirect(url_for("admin_settings"))
    kv = {
        r["key"]: r["value"]
        for r in conn.execute("SELECT key, value FROM settings").fetchall()
    }
    _SEC_LABELS = {
        "basic": ("基础信息", ""),
        "summary": ("个人概要", ""),
        "projects": ("精选项目", ""),
        "experience": ("工作经历", ""),
        "skills": ("专业技能", ""),
        "system": ("系统设置", "仅控制后台"),
    }
    sec_rows = conn.execute("SELECT * FROM sections ORDER BY sort, key").fetchall()
    secs = {r["key"]: r for r in sec_rows}
    sec_list = []
    for r in sec_rows:
        label, note = _SEC_LABELS.get(r["key"], (r["key"], ""))
        sec_list.append(
            {
                "key": r["key"],
                "label": label,
                "note": note,
                "nav_label": r["nav_label"],
                "sort": r["sort"],
            }
        )
    conn.close()
    return render_template(
        "admin/settings.html",
        cdn_enabled=kv.get("cdn_enabled") == "1",
        cdn_base=kv.get("cdn_base", ""),
        secs=secs,
        sec_list=sec_list,
    )


# 启动时每日自动备份（模块导入即执行，覆盖 gunicorn 生产模式）
_auto_backup()

if __name__ == "__main__":
    if "--reset-admin" in sys.argv:
        # 管理员密码重置（服务器管理员特权操作，仅 shell 可触发）：
        #   python app.py --reset-admin            -> 重置为 admin/admin
        #   python app.py --reset-admin 新密码     -> 重置为指定密码
        pw = "admin"
        i = sys.argv.index("--reset-admin")
        if i + 1 < len(sys.argv) and not sys.argv[i + 1].startswith("--"):
            pw = sys.argv[i + 1]
        conn = db.get_db()
        conn.execute(
            "UPDATE admin SET password_hash=? WHERE id=1",
            (hash_password(pw),),
        )
        conn.commit()
        conn.close()
        print(f"[reset] 管理员密码已重置（用户名 admin，新密码：{pw}，登录后请立即修改）")
    else:
        app.run(host="127.0.0.1", port=5000, debug=False)
