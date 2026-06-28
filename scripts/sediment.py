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

必填：--project --type --summary；--agent 可用 setup.py 里的默认 agent 兜底
"""
import argparse
import json
import os
import sys

from sediment_common import (
    VALID_STATUS,
    VALID_TYPES,
    check_env_ready,
    err,
    get_paths,
    load_config,
    make_slug,
    now_iso,
)
from sediment_project import write_project_md
from sediment_repo import dedup_next, list_projects, write_repo


def main():
    ap = argparse.ArgumentParser(description="沉淀一条工作记录")
    ap.add_argument("--list-projects", action="store_true", help="列出运行环境里所有已有项目（slug/显示名/状态），沉淀前用它确认项目身份")
    ap.add_argument("--current", action="store_true", help="读取 current.txt，快速知道最近沉淀的项目 slug（上下文压缩后恢复用）")
    ap.add_argument("--project", default="", help="项目显示名（沉淀时必填）")
    ap.add_argument("--project-slug", default="", help="项目稳定标识（跨 agent 聚合用），不填则由显示名生成")
    ap.add_argument("--type", default="", choices=sorted(VALID_TYPES)+[""], help="类型：progress/decision/knowledge/archive/reactivate")
    ap.add_argument("--summary", default="", help="一句话摘要（沉淀时必填）")
    ap.add_argument("--agent", default="", help="agent 标识，如 zcode/glm-5.2（未传则使用默认 agent 配置）")
    ap.add_argument("--status", default="in-progress", choices=sorted(VALID_STATUS), help="状态，默认 in-progress")
    ap.add_argument("--next", default="[]", help="下一步 JSON 数组：[{t,p,prog}]")
    ap.add_argument("--artifacts", default="[]", help="产出 JSON 数组：[\"path\"]")
    ap.add_argument("--goal", default="", help="项目目标（首次写入，后续默认不覆盖）")
    ap.add_argument("--stage", default="", help="项目当前阶段（首次写入，后续默认不覆盖）")
    ap.add_argument("--update-meta", action="store_true", help="强制更新 goal/stage")
    args = ap.parse_args()

    cfg = load_config()
    paths = get_paths()

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

    # 用 config 默认 agent 兜底（仍以参数为准）
    agent = args.agent or cfg.get("default_agent", "")

    # 沉淀模式：校验必填
    missing = [n for n, v in [("--project", args.project), ("--type", args.type), ("--summary", args.summary), ("--agent 或默认 agent 配置", agent)] if not v]
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

    if not check_env_ready(paths):
        sys.exit(1)

    body = sys.stdin.read()

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

    # 1. 写项目 MD（resolve 后的 goal/stage 同步给网页索引）
    md_path, goal, stage = write_project_md(paths, entry, args.goal, args.stage, args.update_meta)
    entry["goal"] = goal
    entry["stage"] = stage

    # 提示：传了 goal/stage 但被"首次写后不覆盖"规则忽略
    if not args.update_meta:
        ignored = []
        if args.goal and args.goal != goal:
            ignored.append(f"--goal '{args.goal}'")
        if args.stage and args.stage != stage:
            ignored.append(f"--stage '{args.stage}'")
        if ignored:
            print(f"   ℹ️  {', '.join(ignored)} 未生效（目标/阶段首次写后不覆盖，当前沿用 goal='{goal}' stage='{stage}'）。如需覆盖请加 --update-meta", file=sys.stderr)

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
