"""一键迁移：把静态简历的数据导入 timeline-cv 的 SQLite。

从上一级目录的 _gen.py 读取数据结构（单一数据源），把 430 张图复制到
static/uploads/，并按字段写入 resume.db。运行：
    cd timeline-cv
    python migrate.py
"""

import hashlib
import os
import re
import secrets
import shutil
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
OLD = os.path.dirname(BASE)  # 简历/（_gen.py 所在目录）
sys.path.insert(0, OLD)

from _gen import AIGC_PHOTOS, FIG, GROUPS, folder_files, portrait  # noqa: E402

from db import DB, get_db, init_db  # noqa: E402

UPLOADS = os.path.join(BASE, "static", "uploads")

ADMIN_USER = os.environ.get("TIMELINE_ADMIN_USER", "admin")
ADMIN_PASS = os.environ.get("TIMELINE_ADMIN_PASS", "")
if not ADMIN_PASS:
    ADMIN_PASS = secrets.token_urlsafe(16)
    print(
        f"[migrate] 未设置 TIMELINE_ADMIN_PASS 环境变量，已生成随机密码：{ADMIN_PASS}（登录后请立即修改）"
    )


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    iterations = 260000
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), bytes.fromhex(salt), iterations
    ).hex()
    return f"pbkdf2_sha256${iterations}${salt}${digest}"


_img_seq = [0]


def slug_dir(name: str) -> str:
    """清洗目录名：去掉文件系统非法字符，空则回退 untitled。"""
    s = re.sub(r'[\\/:*?"<>|]', "-", name).strip()
    return s or "untitled"


def copy_photo(cat_name: str, proj_title: str, rel: str) -> str:
    """Copy a photo into uploads/<分类>/<项目>/; images 表只存纯文件名。

    文件名加全局序号前缀，避免同一项目内不同文件夹的同名文件互相覆盖。
    """
    src = os.path.join(FIG, rel)
    _img_seq[0] += 1
    name = f"{_img_seq[0]:03d}_{os.path.basename(rel)}"
    d = os.path.join(UPLOADS, slug_dir(cat_name), slug_dir(proj_title))
    os.makedirs(d, exist_ok=True)
    shutil.copy2(src, os.path.join(d, name))
    return name


def main():
    if os.path.exists(DB):
        os.remove(DB)
    if os.path.exists(UPLOADS):
        shutil.rmtree(UPLOADS)
    os.makedirs(UPLOADS, exist_ok=True)
    init_db()
    conn = get_db()
    cur = conn.cursor()

    # 1. admin
    cur.execute(
        "INSERT INTO admin (id, username, password_hash) VALUES (1, ?, ?)",
        (ADMIN_USER, hash_password(ADMIN_PASS)),
    )

    # 2. basic_info
    cur.execute(
        """INSERT INTO basic_info
        (id, name, role, lead, intent, salary, location, email, profile)
        VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            "杨芳清",
            "视频运营 · AIGC 内容与应用",
            (
                "2013 年入行，十三年传媒全链路：电视台、广告公司、新媒体企业。做过涉外文旅宣传、名人专访、"
                "音乐节与大型演出、品牌商业片，也搭直播、写小程序、管服务器。近三年把同一套内容判断力接上大模型——"
                "做模型选型、做提示词与工作流、做AI内容的商业化落地。"
            ),
            "视频运营",
            "12–18K",
            "昆明",
            "136810610@qq.com",
            "男 · 37 岁 · 从业 13 年",
        ),
    )

    # 3. summary + cards
    cur.execute(
        "INSERT INTO summary (id, title, subtitle) VALUES (1, ?, ?)",
        (
            "内容出身，技术落地，最近三年做AIGC。",
            "从选题、拍摄、后期到宣发的完整链路都能独立完成；同时具备开发与运维能力，让新工具真正进到生产流程里，而不只是体验一下。",
        ),
    )
    cards = [
        (
            "内容全链路",
            "方案与脚本、分镜、拍摄、剪辑、包装、平面、宣发。独立完成多部可上星播出节目，累计产出上千期内容矩阵。",
        ),
        (
            "项目广度",
            "涉外文旅、名人专访、音乐节与大型演出、品牌商业内容、政务直播，覆盖从政府机构到头部企业的多种客户类型。",
        ),
        (
            "技术与AIGC",
            "大模型 API 聚合与多站点运营，覆盖对话、绘画、音乐、视频、智能体与工作流；网页、小程序开发与服务器运维。",
        ),
    ]
    for i, (t, c) in enumerate(cards):
        cur.execute(
            "INSERT INTO summary_cards (title, content, sort) VALUES (?, ?, ?)",
            (t, c, i),
        )

    # 4. categories + projects + images
    n_img = 0
    for ci, (gname, gcount, items, chips) in enumerate(GROUPS):
        cur.execute(
            "INSERT INTO categories (name, subtitle, tags, kind, sort) "
            "VALUES (?, ?, ?, 'group', ?)",
            (gname, gcount, ",".join(chips), ci),
        )
        cid = cur.lastrowid
        for pi, (title, desc, photos) in enumerate(items):
            cur.execute(
                "INSERT INTO projects (category_id, title, desc, detail_html, "
                "sort) VALUES (?, ?, ?, '', ?)",
                (cid, title, desc, pi),
            )
            pid = cur.lastrowid
            if photos:
                for prefix, count, label in photos:
                    for rel in folder_files(prefix)[:count]:
                        cur.execute(
                            "INSERT INTO images (project_id, filename, orientation, "
                            "caption, sort) VALUES (?, ?, ?, ?, ?)",
                            (
                                pid,
                                copy_photo(gname, title, rel),
                                "v" if portrait(os.path.join(FIG, rel)) else "h",
                                label,
                                n_img,
                            ),
                        )
                        n_img += 1

    # 5. AIGC 专区（kind='aigc'，一个项目 + 富文本详情 + 9 图）
    aigc_html = (
        '<ul class="ai-list">'
        "<li><b>平台侧：</b>搭建并运营 AI 应用站点与 API 中转，统一供给对话、绘画、音乐、视频、智能体与工作流能力；"
        "C 端站点拓展至 4 个场景站，并规划面向女性用户的简化交互与常用智能体。</li>"
        "<li><b>基础设施：</b>部署美、港及国内节点（约 40 核 / 64G / 千兆带宽），按模型厂商就近接入并做负载均衡；"
        "中转渠道扩至 56 个，接入 GPT-4o、Midjourney 等主流模型，完善计费倍率与用量看板。</li>"
        "<li><b>内容与选型：</b>持续做模型对比与提示词方法论，覆盖文生图、图生图、文生音乐（Suno）、文生视频；"
        "为客户提供「追求质量时如何选型国内外模型」的咨询。</li>"
        "<li><b>生产链路：</b>把 AIGC 嵌进原有视频运营流程——选题与脚本辅助、物料批产、配乐试听、"
        "重复工序交给智能体，降低团队出片成本。</li></ul>"
    )
    cur.execute(
        "INSERT INTO categories (name, subtitle, tags, kind, sort) "
        "VALUES ('AIGC 经历 · 2023 至今', '把模型能力，变成团队和客户用得上的东西。', '', 'aigc', 99)"
    )
    cid = cur.lastrowid
    cur.execute(
        "INSERT INTO projects (category_id, title, desc, "
        "detail_html, sort) VALUES (?, ?, ?, ?, 0)",
        (
            cid,
            "AIGC 内容与应用运营",
            "独立实践 · 对话 / 绘画 / 音乐 / 视频 / 智能体 / 工作流，面向高校、企业、工作室与个人创作者",
            aigc_html,
        ),
    )
    pid = cur.lastrowid
    for i, (prefix, _count, label) in enumerate(AIGC_PHOTOS):
        rel = folder_files(prefix)[0]
        cur.execute(
            "INSERT INTO images (project_id, filename, orientation, "
            "caption, sort) VALUES (?, ?, ?, ?, ?)",
            (
                pid,
                copy_photo("AIGC 经历 · 2023 至今", "AIGC 内容与应用运营", rel),
                "v" if portrait(os.path.join(FIG, rel)) else "h",
                label,
                i,
            ),
        )
        n_img += 1

    # 6. experiences
    exps = [
        (
            "技术部总监",
            "新媒体公司（可见）",
            "内容全链路统筹 + 技术落地",
            "2016 — 2026",
            [
                "统筹选题对接、前期策划、现场拍摄、后期制作、平面视觉与图文排版；累计产出上千期内容矩阵。",
                "业务覆盖公众号、抖音 / 小红书代运营、广告片、微电影、短视频、平面物料，以及多机位多平台推流直播。",
                "负责小程序开发与服务器运维：2018 年可见商城小程序 / APP 上线；具备网页设计、商城架构、裂变小程序开发能力。",
            ],
        ),
        (
            "视频部总监",
            "广告公司",
            "地产板块全案",
            "2015 — 2016",
            [
                "主导地产板块全案业务：广告视频制作、节目包装、平面物料设计、品牌活动策划。",
                "带领团队完成多档播出节目与户外广告项目，统筹策划并落地多项大型线下商业活动。",
            ],
        ),
        (
            "摄像 / 剪辑 / 包装",
            "电视台",
            "大学期间寒暑假即在电台、电视台实习",
            "2013 — 2015",
            [
                "负责新闻、纪录片拍摄剪辑、节目包装、平面设计与线下活动策划。",
                "独立完成多部可上星播出电视节目的全流程制作。",
            ],
        ),
    ]
    for i, (pos, org, org_desc, years, lines) in enumerate(exps):
        cur.execute(
            "INSERT INTO experiences (position, org, org_desc, years, "
            "content, detail_html, sort) VALUES (?, ?, ?, ?, ?, '', ?)",
            (pos, org, org_desc, years, "\n".join(lines), i),
        )

    # 7. skills + cards + tags
    cur.execute(
        "INSERT INTO skills (id, title, subtitle) VALUES (1, '会拍会剪，也懂技术。', '')"
    )
    skill_data = [
        (
            "影视与运营",
            [
                "方案与脚本",
                "分镜",
                "摄像机 / 单反 / 微单",
                "Edius",
                "Premiere",
                "After Effects",
                "Audition",
                "Photoshop",
                "Illustrator",
                "多机位直播推流",
                "新媒体代运营",
            ],
        ),
        (
            "技术与AIGC",
            [
                "大模型 API 聚合与中转",
                "模型选型与评测",
                "提示词工程",
                "智能体与工作流",
                "文生图 / 图生图",
                "文生音乐 · Suno",
                "文生视频",
                "小程序开发",
                "网页与商城架构",
                "服务器与节点运维",
                "Office 办公",
            ],
        ),
    ]
    for i, (t, tags) in enumerate(skill_data):
        cur.execute("INSERT INTO skill_cards (title, sort) VALUES (?, ?)", (t, i))
        cid = cur.lastrowid
        for j, tag in enumerate(tags):
            cur.execute(
                "INSERT INTO skill_tags (card_id, name, sort) VALUES (?, ?, ?)",
                (cid, tag, j),
            )

    conn.commit()
    conn.close()

    cats = len(GROUPS) + 1
    projs = sum(len(items) for _, _, items, _ in GROUPS) + 1
    print(f"migrated: categories={cats} projects={projs} images={n_img}")
    print("admin:", ADMIN_USER)


if __name__ == "__main__":
    main()
