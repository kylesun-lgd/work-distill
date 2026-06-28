#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""sediment.py — 沉淀一条工作记录。

写入运行环境：
  1. 项目 MD（projects/<slug>.md，agent 的活说明书 + 提示词）
     - 概况区：自然语言总结项目现状（每次重写为最新）
     - 焦点区：当前下一步待办（带优先级+进度，每次重写为最新）
     - 历史区：所有沉淀的时间线（追加，保留全部）
  2. 网页数据（data/entries/ 分片正文 + data/index/ 按月索引）

用法：
  sediment.py --project "内容沉淀skill" --project-slug "content-distill" \\
              --type progress --summary "完成设计稿" --agent "zcode/glm-5.2" \\
              --status in-progress \\
              --next '[{"t":"用户审批","p":"高","prog":"50%"}]'
  正文经 stdin 传入（会写入项目 MD 概况区）。

必填：--project --type --summary --agent
"""
import argparse
import fcntl
import json
import os
import random
import re
import string
import sys
from datetime import datetime, timezone, timedelta

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(SCRIPT_DIR)
CONFIG_PATH = os.path.join(SKILL_DIR, "config.json")

# 运行环境固定默认路径——任何工具装的 skill 都用这个，无需各自初始化
DEFAULT_ENV = os.path.expanduser("~/Documents/Zcode/work-distill")
# 全局标记文件：记录运行环境实际路径（非默认时用）。放在用户主目录，跨工具共享
GLOBAL_ENV_MARKER = os.path.expanduser("~/.work-distill-env")
TZ = timezone(timedelta(hours=8))

VALID_TYPES = {"progress", "decision", "knowledge", "archive", "reactivate"}
VALID_STATUS = {"in-progress", "done", "blocked", "archived"}


def discover_env():
    """发现运行环境路径：全局标记 > 默认路径。跨工具共享，不依赖 skill 目录。

    优先级：
    1. 全局标记文件 ~/.work-distill-env（记录用户自定义的运行环境路径）
    2. 默认路径 ~/Documents/Zcode/work-distill
    """
    if os.path.exists(GLOBAL_ENV_MARKER):
        try:
            with open(GLOBAL_ENV_MARKER, "r", encoding="utf-8") as f:
                p = f.read().strip()
                if p and os.path.isdir(p):
                    return p
        except OSError:
            pass
    return DEFAULT_ENV


def load_config():
    """加载 skill 目录的 config（存端口/agent 等覆盖项），不存运行环境路径。"""
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def get_paths(cfg):
    # 运行环境路径不进 config，靠 discover_env() 跨工具共享发现
    env = discover_env()
    return {
        "env": env,
        "entries": os.path.join(env, "data", "entries"),
        "index_dir": os.path.join(env, "data", "index"),
        "projects": os.path.join(env, "projects"),
    }


def now_iso():
    return datetime.now(TZ).strftime("%Y-%m-%dT%H:%M:%S%z")


def slugify(s):
    s = re.sub(r"[\s/\\:*?\"<>|]+", "-", s.strip())
    s = re.sub(r"-+", "-", s).strip("-")
    return s[:40] or "entry"


def make_slug(name):
    """由项目显示名生成稳定 slug（跨 agent 聚合键）。"""
    s = name.strip().lower()
    s = re.sub(r"[\s/\\:*?\"<>|_]+", "-", s)
    s = re.sub(r"-+", "-", s).strip("-")
    return s or "project"


def err(msg):
    print(f"❌ {msg}", file=sys.stderr)


def rand4():
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=4))


def check_env_ready(paths):
    if not os.path.isdir(paths["env"]) or not os.path.exists(os.path.join(paths["env"], "index.html")):
        err(f"运行环境未初始化：{paths['env']}")
        print(f"   请先运行初始化（任一工具装了本 skill 都可初始化，运行环境共享）：", file=sys.stderr)
        print(f"   python3 {os.path.join(SCRIPT_DIR, 'setup.py')}", file=sys.stderr)
        print(f"   （运行环境固定在 {DEFAULT_ENV}，其它工具装的同名 skill 会自动发现它）", file=sys.stderr)
        return False
    return True


# ============ 多 agent 统一性辅助 ============
def _load_all_entries(paths):
    out = []
    idx_dir = paths["index_dir"]
    if not os.path.isdir(idx_dir):
        return out
    for fn in os.listdir(idx_dir):
        if not fn.endswith(".jsonl"):
            continue
        try:
            with open(os.path.join(idx_dir, fn), "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            out.append(json.loads(line))
                        except json.JSONDecodeError:
                            pass
        except OSError:
            pass
    return out


def dedup_next(paths, slug, next_list):
    """去掉同项目近期（30 天内）已存在的相同文本 next。"""
    if not next_list:
        return next_list
    all_entries = _load_all_entries(paths)
    cutoff = (datetime.now(TZ) - timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%S")
    existing = set()
    for e in all_entries:
        if e.get("slug") != slug or e.get("ts", "") < cutoff:
            continue
        for n in e.get("next", []):
            t = n.get("t", "").strip().lower() if isinstance(n, dict) else str(n).strip().lower()
            if t:
                existing.add(t)
    kept = []
    for n in next_list:
        t = n.get("t", "").strip().lower()
        if t and t in existing:
            continue
        existing.add(t)
        kept.append(n)
    return kept


# ============ 写项目 MD（agent 的活说明书 + 提示词）============
def write_project_md(paths, entry, goal, stage, force_meta):
    """更新项目 MD：概况+焦点 重写为最新，历史 追加。"""
    os.makedirs(paths["projects"], exist_ok=True)
    md_path = os.path.join(paths["projects"], f"{entry['slug']}.md")

    # goal/stage 首次写后不覆盖（除非 force_meta）
    goal, stage = resolve_meta(md_path, goal, stage, force_meta)

    lock_path = md_path + ".lock"
    with open(lock_path, "w") as lf:
        fcntl.flock(lf, fcntl.LOCK_EX)
        try:
            _write_md_inner(md_path, entry, goal, stage)
        finally:
            fcntl.flock(lf, fcntl.LOCK_UN)
    return md_path


def resolve_meta(md_path, goal, stage, force):
    if force or not os.path.exists(md_path):
        return goal, stage
    try:
        with open(md_path, "r", encoding="utf-8") as f:
            content = f.read()
        old_goal = ""
        old_stage = ""
        # 格式：<!-- goal: xxx | stage: yyy -->
        m = re.search(r"<!-- goal:\s*(.*?)\s*\|\s*stage:\s*(.*?)\s*-->", content)
        if m:
            old_goal = m.group(1).strip()
            old_stage = m.group(2).strip()
        return (goal if force and goal else (goal or old_goal)), (stage if force and stage else (stage or old_stage))
    except OSError:
        return goal, stage


def _write_md_inner(md_path, entry, goal, stage):
    """写项目 MD：顶部概况+焦点（每次重写），底部历史（追加）。"""
    existing = ""
    if os.path.exists(md_path):
        with open(md_path, "r", encoding="utf-8") as f:
            existing = f.read()

    # 切出历史区（保留全部追加历史）
    history = ""
    if existing:
        marker = "## 更新历史"
        idx = existing.find(marker)
        if idx >= 0:
            history = existing[idx:]
        else:
            history = "## 更新历史\n" + existing

    type_label = {"progress": "进展", "decision": "决策", "knowledge": "知识", "archive": "归档", "reactivate": "重新激活"}[entry["type"]]
    status_label = {"in-progress": "进行中", "done": "已完成", "blocked": "阻塞", "archived": "创意仓库"}[entry["status"]]

    # ============ 顶部：概况 + 焦点（agent 必读，每次重写）============
    md = f"# {entry['project']}\n\n"
    md += f"<!-- slug: {entry['slug']} | agent: {entry['agent']} | ts: {entry['ts']} -->\n"
    md += f"<!-- goal: {goal} | stage: {stage} -->\n\n"

    md += "> **agent 执行沉淀前先读本文件**，了解项目现状再更新。\n\n"

    md += "## 项目概况\n\n"
    if goal:
        md += f"**目标**：{goal}\n\n"
    if stage:
        md += f"**当前阶段**：{stage}\n\n"
    md += f"**最新动态**（{entry['ts']} · {entry['agent']}）：\n\n"
    if entry["body"]:
        md += entry["body"].strip() + "\n\n"
    else:
        md += f"{entry['summary']}（{type_label} · {status_label}）\n\n"

    md += "## 当前焦点\n\n"
    if entry["next"]:
        for n in entry["next"]:
            extra = []
            if n.get("p"):
                extra.append(f"优先级 {n['p']}")
            if n.get("prog"):
                extra.append(f"进度 {n['prog']}")
            extra_s = f"（{'，'.join(extra)}）" if extra else ""
            md += f"- {n['t']}{extra_s}\n"
        md += "\n"
    else:
        if entry["type"] == "archive":
            md += "_（项目已归档到创意仓库，暂无活跃待办）_\n\n"
        elif entry["type"] == "reactivate":
            md += "_（项目已从创意仓库重新激活）_\n\n"
        else:
            md += "_（暂无待办）_\n\n"

    # ============ 底部：更新历史（追加，保留全部）============
    if not history:
        history = "## 更新历史\n"
    history += _history_entry(entry, type_label, status_label)

    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md + history + "\n")


def _history_entry(entry, type_label, status_label):
    s = f"\n### {entry['ts']} · {entry['agent']} · {type_label} · {status_label}\n\n"
    s += f"**{entry['summary']}**\n\n"
    if entry["body"]:
        s += entry["body"].strip() + "\n\n"
    if entry["next"]:
        s += "**下一步**：\n"
        for n in entry["next"]:
            extra = []
            if n.get("p"):
                extra.append(f"优先级 {n['p']}")
            if n.get("prog"):
                extra.append(f"进度 {n['prog']}")
            if extra:
                s += f"- {n['t']}（{'，'.join(extra)}）\n"
            else:
                s += f"- {n['t']}\n"
        s += "\n"
    if entry["artifacts"]:
        s += "**产出**：" + "、".join(f"`{a}`" for a in entry["artifacts"]) + "\n\n"
    s += "---\n"
    return s


# ============ 写网页数据（entries 分片 + 索引）============
def write_repo(paths, entry):
    """写 entries 分片 MD + 追加按月索引一行（fcntl 锁）。返回分片相对路径。"""
    os.makedirs(paths["entries"], exist_ok=True)
    ym = entry["ts"][:7]
    month_dir = os.path.join(paths["entries"], ym)
    os.makedirs(month_dir, exist_ok=True)

    hhmm = entry["ts"][11:16].replace(":", "")
    fname = f"{entry['ts'][:10]}-{hhmm}-{slugify(entry['summary'])}-{rand4()}.md"
    frag_path = os.path.join(month_dir, fname)
    rel_path = f"data/entries/{ym}/{fname}"

    with open(frag_path, "w", encoding="utf-8") as f:
        f.write(_fragment_md(entry))

    # 索引追加（按月分片：data/index/YYYY-MM.jsonl）
    os.makedirs(paths["index_dir"], exist_ok=True)
    idx_file = os.path.join(paths["index_dir"], f"{ym}.jsonl")
    with open(idx_file + ".lock", "w") as lf:
        fcntl.flock(lf, fcntl.LOCK_EX)
        try:
            with open(idx_file, "a", encoding="utf-8") as f:
                f.write(json.dumps({
                    "ts": entry["ts"],
                    "agent": entry["agent"],
                    "project": entry["project"],
                    "slug": entry["slug"],
                    "type": entry["type"],
                    "summary": entry["summary"],
                    "status": entry["status"],
                    "file": rel_path,
                    "next": entry["next"],
                    "artifacts": entry["artifacts"],
                }, ensure_ascii=False) + "\n")
        finally:
            fcntl.flock(lf, fcntl.LOCK_UN)
    return rel_path


def _fragment_md(entry):
    type_label = {"progress": "进展", "decision": "决策", "knowledge": "知识", "archive": "归档", "reactivate": "重新激活"}[entry["type"]]
    status_label = {"in-progress": "进行中", "done": "已完成", "blocked": "阻塞", "archived": "创意仓库"}[entry["status"]]
    fm = "---\n"
    fm += f"ts: {entry['ts']}\n"
    fm += f"agent: {entry['agent']}\n"
    fm += f"project: {entry['project']}\n"
    fm += f"slug: {entry['slug']}\n"
    fm += f"type: {entry['type']}\n"
    fm += f"summary: {entry['summary']}\n"
    fm += f"status: {entry['status']}\n"
    if entry["next"]:
        fm += "next:\n"
        for n in entry["next"]:
            fm += f"  - t: {n['t']}\n"
            if n.get("p"):
                fm += f"    p: {n['p']}\n"
            if n.get("prog"):
                fm += f"    prog: {n['prog']}\n"
    if entry["artifacts"]:
        fm += "artifacts:\n"
        for a in entry["artifacts"]:
            fm += f"  - {a}\n"
    fm += "---\n\n"
    body = f"# {entry['summary']}\n\n"
    body += f"**{type_label} · {status_label}** · {entry['ts']} · {entry['agent']}\n\n"
    if entry["body"]:
        body += entry["body"].strip() + "\n\n"
    if entry["next"]:
        body += "## 下一步\n\n"
        for n in entry["next"]:
            extra = []
            if n.get("p"):
                extra.append(f"优先级 {n['p']}")
            if n.get("prog"):
                extra.append(f"进度 {n['prog']}")
            extra_s = f"（{'，'.join(extra)}）" if extra else ""
            body += f"- {n['t']}{extra_s}\n"
    if entry["artifacts"]:
        body += "\n## 产出\n\n"
        for a in entry["artifacts"]:
            body += f"- `{a}`\n"
    return fm + body


# ============ 主流程 ============
def list_projects(paths):
    """列出运行环境里所有已有项目（slug + 显示名 + 状态 + 最近更新 + 简介）。"""
    all_entries = _load_all_entries(paths)
    if not all_entries:
        print("（运行环境里还没有任何项目，下次沉淀会创建第一个）")
        return
    # 按 slug 聚合
    by_slug = {}
    for e in all_entries:
        k = e.get("slug") or e.get("project", "")
        if not k:
            continue
        by_slug.setdefault(k, []).append(e)
    print(f"运行环境里已有 {len(by_slug)} 个项目：")
    print("-" * 60)
    for slug, es in sorted(by_slug.items(), key=lambda x: max(e.get("ts", "") for e in x[1]), reverse=True):
        es_sorted = sorted(es, key=lambda e: e.get("ts", ""), reverse=True)
        latest = es_sorted[0]
        # 项目整体状态（最近一条非归档/激活）
        non_meta = [e for e in es_sorted if e.get("type") not in ("archive", "reactivate")]
        status = non_meta[0].get("status", "in-progress") if non_meta else "in-progress"
        status_label = {"in-progress": "进行中", "done": "已完成", "blocked": "阻塞", "archived": "创意仓库"}.get(status, status)
        # 归档态
        changes = [e for e in es_sorted if e.get("type") in ("archive", "reactivate")]
        if changes and changes[0].get("type") == "archive":
            status_label = "创意仓库"
        display = latest.get("project", slug)
        brief = latest.get("summary", "")
        last_ts = latest.get("ts", "")[:16].replace("T", " ")
        print(f"  slug: {slug}")
        print(f"  显示名: {display}")
        print(f"  状态: {status_label} · 最近更新: {last_ts} · 共 {len(es)} 条")
        print(f"  简介: {brief}")
        print("-" * 60)


def main():
    ap = argparse.ArgumentParser(description="沉淀一条工作记录")
    ap.add_argument("--list-projects", action="store_true", help="列出运行环境里所有已有项目（slug/显示名/状态），沉淀前用它确认项目身份")
    ap.add_argument("--current", action="store_true", help="读取 current.txt，快速知道最近沉淀的项目 slug（上下文压缩后恢复用）")
    ap.add_argument("--project", default="", help="项目显示名（沉淀时必填）")
    ap.add_argument("--project-slug", default="", help="项目稳定标识（跨 agent 聚合用），不填则由显示名生成")
    ap.add_argument("--type", default="", choices=sorted(VALID_TYPES)+[""], help="类型：progress/decision/knowledge/archive/reactivate")
    ap.add_argument("--summary", default="", help="一句话摘要（沉淀时必填）")
    ap.add_argument("--agent", default="", help="agent 标识，如 zcode/glm-5.2（沉淀时必填）")
    ap.add_argument("--status", default="in-progress", choices=sorted(VALID_STATUS), help="状态，默认 in-progress")
    ap.add_argument("--next", default="[]", help="下一步 JSON 数组：[{t,p,prog}]")
    ap.add_argument("--artifacts", default="[]", help="产出 JSON 数组：[\"path\"]")
    ap.add_argument("--goal", default="", help="项目目标（首次写入，后续默认不覆盖）")
    ap.add_argument("--stage", default="", help="项目当前阶段（首次写入，后续默认不覆盖）")
    ap.add_argument("--update-meta", action="store_true", help="强制更新 goal/stage")
    args = ap.parse_args()

    cfg = load_config()
    paths = get_paths(cfg)

    # --list-projects：列出已有项目，帮助 agent 确认 slug
    if args.list_projects:
        if not check_env_ready(paths):
            sys.exit(1)
        list_projects(paths)
        return

    # --current：读取 current.txt，快速知道最近沉淀的项目（上下文压缩后恢复用）
    if args.current:
        current_path = os.path.join(paths["env"], "current.txt")
        if not os.path.exists(current_path):
            print("（还没有沉淀过任何项目，没有当前项目记录）")
        else:
            with open(current_path, "r", encoding="utf-8") as f:
                lines = f.read().strip().split("\n")
            slug = lines[0] if len(lines) > 0 else ""
            display = lines[1] if len(lines) > 1 else ""
            ts = lines[2] if len(lines) > 2 else ""
            print(f"最近沉淀的项目：")
            print(f"  slug: {slug}")
            print(f"  显示名: {display}")
            print(f"  最近沉淀时间: {ts}")
            print(f"  项目 MD: {paths['projects']}/{slug}.md")
            print(f"  （读这个 MD 可恢复项目完整上下文）")
        return

    # 沉淀模式：校验必填
    missing = [n for n, v in [("--project", args.project), ("--type", args.type), ("--summary", args.summary), ("--agent", args.agent)] if not v]
    if missing:
        err(f"沉淀模式缺少必填参数: {' '.join(missing)}")
        print(f"   提示：不确定项目 slug？先运行: python3 {os.path.basename(__file__)} --list-projects", file=sys.stderr)
        sys.exit(2)

    slug = args.project_slug or make_slug(args.project)

    try:
        next_list = json.loads(args.next)
        artifacts = json.loads(args.artifacts)
    except json.JSONDecodeError as e:
        err(f"--next / --artifacts 不是合法 JSON: {e}")
        sys.exit(2)

    for n in next_list:
        if not isinstance(n, dict) or not n.get("t"):
            err(f"--next 每项必须是对象且含 t 字段: {n}")
            sys.exit(2)

    body = sys.stdin.read()

    # 用 config 默认 agent 兜底（仍以参数为准）
    agent = args.agent or cfg.get("default_agent", "unknown")

    # next 去重
    next_list = dedup_next(paths, slug, next_list)

    entry = {
        "ts": now_iso(),
        "agent": agent,
        "project": args.project,
        "slug": slug,
        "type": args.type,
        "summary": args.summary,
        "status": args.status,
        "next": next_list,
        "artifacts": artifacts,
        "body": body,
    }

    # 1. 写项目 MD
    md_path = write_project_md(paths, entry, args.goal, args.stage, args.update_meta)

    # 2. 写网页数据
    rel = write_repo(paths, entry)

    port = cfg.get("serve_port", 7788)

    # 写 current.txt：记录最近沉淀的项目 slug，作为上下文压缩后的恢复锚点
    current_path = os.path.join(paths["env"], "current.txt")
    with open(current_path, "w", encoding="utf-8") as f:
        f.write(f"{entry['slug']}\n{entry['project']}\n{entry['ts']}\n")

    print(f"✅ 已沉淀：{entry['project']} - {entry['summary']}")
    print(f"   📝 项目 MD: {md_path}")
    print(f"   📦 网页分片: {rel}")
    print(f"   🌐 查看: http://localhost:{port}（serve.py start）")


if __name__ == "__main__":
    main()
