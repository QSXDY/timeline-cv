# -*- coding: utf-8 -*-
import os
import sqlite3

conn = sqlite3.connect("resume.db")
conn.row_factory = sqlite3.Row
for t in ["admin", "basic_info", "summary", "summary_cards", "categories",
          "projects", "images", "experiences", "skills", "skill_cards", "skill_tags"]:
    n = conn.execute("SELECT COUNT(*) AS c FROM " + t).fetchone()["c"]
    print(t, n)
print("orientation:", dict(conn.execute(
    "SELECT orientation, COUNT(*) AS c FROM images GROUP BY orientation").fetchall()))
up = "static/uploads"
total = sum(len(files) for _, _, files in os.walk(up))
print("uploaded files:", total)
# sample rows
print("first project:", dict(conn.execute(
    "SELECT id, title FROM projects ORDER BY id LIMIT 1").fetchone()))
print("aigc project:", dict(conn.execute(
    "SELECT p.title, c.name FROM projects p JOIN categories c ON p.category_id=c.id "
    "WHERE c.kind='aigc'").fetchone()))
