# -*- coding: utf-8 -*-
"""修复：磁盘目录名与 DB 标题同步（v9 迁移只改了 DB，磁盘目录还是旧标题带日期 → 全站图片 404）。"""
import io, os, re, sqlite3

ROOT = r"C:\Users\YFQ-1\Desktop\简历\yfq-resume"
dbp = os.path.join(ROOT, "resume.db")
bak = os.path.join(ROOT, "resume.db.bak_v9")
up = os.path.join(ROOT, "static", "uploads")

def q(conn, sql, *a):
    return conn.execute(sql, a).fetchall()

conn = sqlite3.connect(dbp)
conn.row_factory = sqlite3.Row
connbak = sqlite3.connect(bak)
connbak.row_factory = sqlite3.Row

# 1) 重名标题加年份（避免 rename 冲突）
fix = {36: "五百里音乐节 2016", 37: "五百里音乐节 2017",
       39: "草莓音乐节 2016", 41: "草莓音乐节 2019", 42: "草莓音乐节 2024"}
for pid, t in fix.items():
    conn.execute("UPDATE projects SET title=? WHERE id=?", (t, pid))
conn.commit()
print("重名标题已加年份:", fix)

# 2) 磁盘目录名 ↔ 旧标题（bak_v9）→ 新标题（当前 DB）
new_title = {r["id"]: r["title"] for r in q(conn, "SELECT id, title FROM projects")}
old_title = {r["id"]: r["title"] for r in q(connbak, "SELECT id, title FROM projects")}
# 磁盘二级目录索引：目录名 -> (分组, 绝对路径)
dirs = {}
for g in os.listdir(up):
    gp = os.path.join(up, g)
    if not os.path.isdir(gp):
        continue
    for d in os.listdir(gp):
        dp = os.path.join(gp, d)
        if os.path.isdir(dp):
            dirs.setdefault(d, []).append((g, dp))

renamed, missing, skipped, conflicts = 0, [], 0, []
for pid, old in old_title.items():
    new = new_title.get(pid)
    if not new or new == old:
        continue
    if old in dirs:
        for g, dp in dirs[old]:
            np_ = os.path.join(os.path.dirname(dp), new)
            if os.path.exists(np_):
                conflicts.append((old, new, g))
                continue
            os.rename(dp, np_)
            renamed += 1
            print("  rename:", repr(old), "->", repr(new), "@", g)
    else:
        missing.append((pid, old, new))
print()
print("renamed:", renamed, "| conflicts:", conflicts, "| skipped:", skipped)
print("missing(磁盘无此目录):")
for pid, old, new in missing:
    print("   id", pid, repr(old), "->", repr(new))
conn.close(); connbak.close()
