# -*- coding: utf-8 -*-
"""迁移：初始化 classifications + sections，分组归位。幂等。"""
import sqlite3, sys, os
sys.path.insert(0, r"C:\Users\YFQ-1\Desktop\简历\yfq-resume")
import db as dbm
dbm.init_db()  # 确保新表存在（CREATE IF NOT EXISTS + ALTER）

conn = sqlite3.connect(dbm.DB)
conn.row_factory = sqlite3.Row

# 1) 初始化一级分类（幂等：仅当表空时）
n = conn.execute("SELECT COUNT(*) c FROM classifications").fetchone()["c"]
if n == 0:
    conn.execute("INSERT INTO classifications (name, section, sort) VALUES ('精选项目', 'projects', 0)")
    conn.execute("INSERT INTO classifications (name, section, sort) VALUES ('AIGC 经历', 'aigc', 1)")
    print("classifications seeded")
else:
    print("classifications already exist:", n)

# 2) 分组归位：kind=group → 精选项目分类(1)；kind=aigc → AIGC分类(2)
unmapped = conn.execute("SELECT COUNT(*) c FROM categories WHERE classification_id=0").fetchone()["c"]
if unmapped:
    conn.execute("UPDATE categories SET classification_id=1 WHERE classification_id=0 AND kind='group'")
    conn.execute("UPDATE categories SET classification_id=2 WHERE classification_id=0 AND kind='aigc'")
    conn.commit()
    print("groups mapped:", unmapped)
else:
    print("groups already mapped")

# 3) sections 初始值（5 行，幂等）
rows = {r["key"]: r for r in conn.execute("SELECT * FROM sections").fetchall()}
seed = [
    ("summary", "概要", "概要", "", ""),
    ("projects", "精选项目", "精选项目 · 2014 至今",
     "把内容交给现场，把结果交给客户。",
     "按项目类型分组，每一条对应纪要中的一个时间节点，可点击展开项目配图；图片按横图 3 列、竖图 6 列自动分行。"),
    ("aigc", "AIGC", "AIGC", "", ""),
    ("experience", "经历", "工作经历", "电视台、广告公司、新媒体。", ""),
    ("skills", "技能", "技能", "", ""),
]
for key, nav, eb, ti, sub in seed:
    if key not in rows:
        conn.execute("INSERT INTO sections (key, nav_label, eyebrow, title, subtitle) VALUES (?,?,?,?,?)",
                     (key, nav, eb, ti, sub))
        print("section seeded:", key)
conn.commit()

# 4) 从现有数据补充 sections 的 title/subtitle
su = conn.execute("SELECT title, subtitle FROM summary WHERE id=1").fetchone()
if su and su["title"]:
    conn.execute("UPDATE sections SET title=?, subtitle=? WHERE key='summary'", (su["title"], su["subtitle"]))
sk = conn.execute("SELECT title, subtitle FROM skills WHERE id=1").fetchone()
if sk and sk["title"]:
    conn.execute("UPDATE sections SET title=?, subtitle=? WHERE key='skills'", (sk["title"], sk["subtitle"]))
aigc_cat = conn.execute("SELECT name, subtitle FROM categories WHERE kind='aigc' LIMIT 1").fetchone()
if aigc_cat:
    conn.execute("UPDATE sections SET eyebrow=?, title=?, subtitle=? WHERE key='aigc'",
                 (aigc_cat["name"], aigc_cat["subtitle"] or "AIGC", ""))
conn.commit()

# 校验输出
print("\n--- classifications ---")
for r in conn.execute("SELECT * FROM classifications ORDER BY sort").fetchall():
    print(dict(r))
print("--- categories ---")
for r in conn.execute("SELECT id, name, kind, classification_id FROM categories ORDER BY id").fetchall():
    print(dict(r))
print("--- sections ---")
for r in conn.execute("SELECT key, nav_label, eyebrow, title FROM sections ORDER BY key").fetchall():
    print(dict(r))
conn.close()
