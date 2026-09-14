"""SQLite schema for yfq-resume."""

import os
import sqlite3

BASE = os.path.dirname(os.path.abspath(__file__))
# 数据库路径支持环境变量覆盖（Docker 部署时指向挂载卷），默认 ./resume.db
DB = os.environ.get("RESUME_DB", os.path.join(BASE, "resume.db"))

SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS admin (
  id            INTEGER PRIMARY KEY CHECK (id = 1),
  username      TEXT NOT NULL UNIQUE,
  password_hash TEXT NOT NULL,          -- pbkdf2_sha256$iter$salt_hex$hash_hex
  created_at    TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS settings (
  key   TEXT PRIMARY KEY,
  value TEXT NOT NULL DEFAULT ''
  );

CREATE TABLE IF NOT EXISTS basic_info (
  id       INTEGER PRIMARY KEY CHECK (id = 1),
  name     TEXT NOT NULL DEFAULT '',
  role     TEXT NOT NULL DEFAULT '',
  lead     TEXT NOT NULL DEFAULT '',
  intent   TEXT NOT NULL DEFAULT '',    -- 求职意向
  salary   TEXT NOT NULL DEFAULT '',    -- 期望薪资
  location TEXT NOT NULL DEFAULT '',    -- 期望工作地
  email    TEXT NOT NULL DEFAULT '',
  profile  TEXT NOT NULL DEFAULT '',    -- 基本情况（性别/年龄/年限）
  avatar   TEXT NOT NULL DEFAULT ''     -- 个人照片文件名（static/uploads/_avatar/ 下，空=未上传）
);

CREATE TABLE IF NOT EXISTS summary (
  id       INTEGER PRIMARY KEY CHECK (id = 1),
  title    TEXT NOT NULL DEFAULT '',
  subtitle TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS summary_cards (
  id      INTEGER PRIMARY KEY AUTOINCREMENT,
  title   TEXT NOT NULL,
  content TEXT NOT NULL,
  sort    INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS classifications (
  id      INTEGER PRIMARY KEY AUTOINCREMENT,
  name    TEXT NOT NULL,
  sort    INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS categories (
  id                 INTEGER PRIMARY KEY AUTOINCREMENT,
  classification_id  INTEGER NOT NULL DEFAULT 0,  -- 所属一级分类（0=未归位）
  name               TEXT NOT NULL,
  subtitle           TEXT NOT NULL DEFAULT '',
  tags               TEXT NOT NULL DEFAULT '',    -- 逗号分隔的关键词标签（前台 chips）
  sort               INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS sections (
  key       TEXT PRIMARY KEY,     -- basic / summary / projects / experience / skills / system
  nav_label TEXT NOT NULL DEFAULT '',
  eyebrow   TEXT NOT NULL DEFAULT '',
  title     TEXT NOT NULL DEFAULT '',
  subtitle  TEXT NOT NULL DEFAULT '',
  sort      INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS projects (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  category_id INTEGER NOT NULL REFERENCES categories(id) ON DELETE CASCADE,
  title       TEXT NOT NULL,
  desc        TEXT NOT NULL DEFAULT '',      -- 副标题/描述
  detail_html TEXT NOT NULL DEFAULT '',      -- 富文本详情（编辑器）
  sort        INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS images (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id  INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  filename    TEXT NOT NULL,                 -- static/uploads/ 下相对路径
  orientation TEXT NOT NULL CHECK (orientation IN ('h','v')),
  type        TEXT NOT NULL DEFAULT 'image',   -- image / video
  caption     TEXT NOT NULL DEFAULT '',
  sort        INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS experiences (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  position    TEXT NOT NULL,
  org         TEXT NOT NULL DEFAULT '',
  org_desc    TEXT NOT NULL DEFAULT '',      -- 职位一句话描述（前台 org 行）
  years       TEXT NOT NULL DEFAULT '',
  content     TEXT NOT NULL DEFAULT '',      -- 工作内容（每行一条）
  detail_html TEXT NOT NULL DEFAULT '',      -- 工作详情（富文本）
  sort        INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS skills (
  id       INTEGER PRIMARY KEY CHECK (id = 1),
  title    TEXT NOT NULL DEFAULT '',
  subtitle TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS skill_cards (
  id    INTEGER PRIMARY KEY AUTOINCREMENT,
  title TEXT NOT NULL,
  sort  INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS skill_tags (
  id      INTEGER PRIMARY KEY AUTOINCREMENT,
  card_id INTEGER NOT NULL REFERENCES skill_cards(id) ON DELETE CASCADE,
  name    TEXT NOT NULL,
  sort    INTEGER NOT NULL DEFAULT 0
);
"""


def get_db():
    conn = sqlite3.connect(DB, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


def init_db():
    conn = get_db()
    conn.executescript(SCHEMA)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
    except Exception:
        pass
    _drop_legacy_cols(conn)
    for stmt in (
        "ALTER TABLE images ADD COLUMN type TEXT NOT NULL DEFAULT 'image'",
        "ALTER TABLE categories ADD COLUMN classification_id INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE sections ADD COLUMN sort INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE projects ADD COLUMN pub_date TEXT NOT NULL DEFAULT ''",
    ):
        try:
            conn.execute(stmt)
            conn.commit()
        except Exception:
            pass
    conn.close()


if __name__ == "__main__":
    init_db()
    print("db ready:", DB)


def _drop_legacy_cols(conn):
    """v10 迁移：删除已废弃的 classifications.section 与 categories.kind 列（重建表）。
    注意：SQLite ALTER TABLE RENAME 会把其他表的外键引用一并改名，因此采用
    「建新表 → 拷数据 → DROP 旧表 → RENAME」顺序，避免 projects 外键悬空。"""
    conn.execute("PRAGMA foreign_keys = OFF")
    try:
        cols = [r[1] for r in conn.execute("PRAGMA table_info(classifications)")]
        if "section" in cols:
            conn.execute(
                "CREATE TABLE classifications_new (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, sort INTEGER NOT NULL DEFAULT 0)"
            )
            conn.execute(
                "INSERT INTO classifications_new (id, name, sort) SELECT id, name, sort FROM classifications"
            )
            conn.execute("DROP TABLE classifications")
            conn.execute("ALTER TABLE classifications_new RENAME TO classifications")
            conn.commit()
            print("db: dropped classifications.section")
    except Exception as e:
        print("db: classifications migrate skip:", e)
    try:
        cols = [r[1] for r in conn.execute("PRAGMA table_info(categories)")]
        if "kind" in cols:
            conn.execute(
                "CREATE TABLE categories_new (id INTEGER PRIMARY KEY AUTOINCREMENT, classification_id INTEGER NOT NULL DEFAULT 0, name TEXT NOT NULL, subtitle TEXT NOT NULL DEFAULT '', tags TEXT NOT NULL DEFAULT '', sort INTEGER NOT NULL DEFAULT 0)"
            )
            conn.execute(
                "INSERT INTO categories_new (id, classification_id, name, subtitle, tags, sort) SELECT id, classification_id, name, subtitle, tags, sort FROM categories"
            )
            conn.execute("DROP TABLE categories")
            conn.execute("ALTER TABLE categories_new RENAME TO categories")
            conn.commit()
            print("db: dropped categories.kind")
    except Exception as e:
        print("db: categories migrate skip:", e)
    _repair_projects_fk(conn)
    conn.execute("PRAGMA foreign_keys = ON")


def _repair_projects_fk(conn):
    """修复 projects 外键悬空：若 FK 目标不是 categories 则成对重建 projects + images。

    注意：不能单独 RENAME/DROP projects——images.project_id 的外键会被 ALTER RENAME 一并
    改指向 projects_old，DROP projects_old 时触发 ON DELETE CASCADE 清空 images。
    因此两个表成对重建：建新表 → 拷数据 → 删旧表（先 images 后 projects）→ RENAME。"""
    try:
        tables = [
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name IN ('projects','projects_old')"
            ).fetchall()
        ]
        if "projects" not in tables:
            # projects 缺失但 projects_old 存在（被 RENAME 过）：直接改回即可（引用方 FK 会随之更新）
            if "projects_old" in tables:
                conn.execute("ALTER TABLE projects_old RENAME TO projects")
                conn.commit()
                print("db: restored projects table name")
            return
        fks = conn.execute("PRAGMA foreign_key_list(projects)").fetchall()
        bad = any(fk[2] != "categories" for fk in fks)
        if not bad:
            return
        conn.execute(
            "CREATE TABLE projects_new (id INTEGER PRIMARY KEY AUTOINCREMENT, category_id INTEGER NOT NULL REFERENCES categories(id) ON DELETE CASCADE, title TEXT NOT NULL, desc TEXT NOT NULL DEFAULT '', detail_html TEXT NOT NULL DEFAULT '', pub_date TEXT, sort INTEGER NOT NULL DEFAULT 255)"
        )
        conn.execute(
            "CREATE TABLE images_new (id INTEGER PRIMARY KEY AUTOINCREMENT, project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE, filename TEXT NOT NULL, orientation TEXT NOT NULL DEFAULT 'h', caption TEXT NOT NULL DEFAULT '', sort INTEGER NOT NULL DEFAULT 0, type TEXT NOT NULL DEFAULT 'image')"
        )
        conn.execute(
            "INSERT INTO projects_new (id, category_id, title, desc, detail_html, pub_date, sort) SELECT id, category_id, title, desc, detail_html, pub_date, sort FROM projects"
        )
        conn.execute(
            "INSERT INTO images_new (id, project_id, filename, orientation, caption, sort, type) SELECT id, project_id, filename, orientation, caption, sort, type FROM images"
        )
        conn.execute("DROP TABLE images")
        conn.execute("DROP TABLE projects")
        conn.execute("ALTER TABLE projects_new RENAME TO projects")
        conn.execute("ALTER TABLE images_new RENAME TO images")
        conn.commit()
        print("db: repaired projects+images FK -> categories")
    except Exception as e:
        print("db: projects fk repair skip:", e)
