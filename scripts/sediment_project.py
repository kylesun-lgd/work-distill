import os
import re

from sediment_common import LOCK_EX, LOCK_UN, file_lock

TYPE_LABELS = {
    "progress": "进展",
    "decision": "决策",
    "knowledge": "知识",
    "archive": "归档",
    "reactivate": "重新激活",
}
STATUS_LABELS = {
    "in-progress": "进行中",
    "done": "已完成",
    "blocked": "阻塞",
    "archived": "创意仓库",
}


def write_project_md(paths, entry, goal, stage, force_meta):
    os.makedirs(paths["projects"], exist_ok=True)
    md_path = os.path.join(paths["projects"], f"{entry['slug']}.md")
    goal, stage = resolve_meta(md_path, goal, stage, force_meta)

    lock_path = md_path + ".lock"
    with open(lock_path, "w") as lock_file:
        file_lock(lock_file, LOCK_EX)
        try:
            write_project_md_inner(md_path, entry, goal, stage)
        finally:
            file_lock(lock_file, LOCK_UN)
    return md_path, goal, stage


def resolve_meta(md_path, goal, stage, force):
    if not os.path.exists(md_path):
        return goal, stage
    try:
        with open(md_path, "r", encoding="utf-8") as f:
            content = f.read()
        old_goal = ""
        old_stage = ""
        match = re.search(r"<!-- goal:\s*(.*?)\s*\|\s*stage:\s*(.*?)\s*-->", content)
        if match:
            old_goal = match.group(1).strip()
            old_stage = match.group(2).strip()
        if force:
            return (goal if goal else old_goal), (stage if stage else old_stage)
        return old_goal, old_stage
    except OSError:
        return goal, stage


def write_project_md_inner(md_path, entry, goal, stage):
    existing = ""
    if os.path.exists(md_path):
        with open(md_path, "r", encoding="utf-8") as f:
            existing = f.read()

    history = ""
    if existing:
        marker = "## 更新历史"
        idx = existing.find(marker)
        if idx >= 0:
            history = existing[idx:]
        else:
            history = "## 更新历史\n" + existing

    type_label = TYPE_LABELS[entry["type"]]
    status_label = STATUS_LABELS[entry["status"]]
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
        for next_item in entry["next"]:
            extra = []
            if next_item.get("p"):
                extra.append(f"优先级 {next_item['p']}")
            if next_item.get("prog"):
                extra.append(f"进度 {next_item['prog']}")
            extra_text = f"（{'，'.join(extra)}）" if extra else ""
            md += f"- {next_item['t']}{extra_text}\n"
        md += "\n"
    elif entry["type"] == "archive":
        md += "_（项目已归档到创意仓库，暂无活跃待办）_\n\n"
    elif entry["type"] == "reactivate":
        md += "_（项目已从创意仓库重新激活）_\n\n"
    else:
        md += "_（暂无待办）_\n\n"

    if not history:
        history = "## 更新历史\n"
    history += history_entry(entry, type_label, status_label)

    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md + history + "\n")


def history_entry(entry, type_label, status_label):
    text = f"\n### {entry['ts']} · {entry['agent']} · {type_label} · {status_label}\n\n"
    text += f"**{entry['summary']}**\n\n"
    if entry["body"]:
        text += entry["body"].strip() + "\n\n"
    if entry["next"]:
        text += "**下一步**：\n"
        for next_item in entry["next"]:
            extra = []
            if next_item.get("p"):
                extra.append(f"优先级 {next_item['p']}")
            if next_item.get("prog"):
                extra.append(f"进度 {next_item['prog']}")
            if extra:
                text += f"- {next_item['t']}（{'，'.join(extra)}）\n"
            else:
                text += f"- {next_item['t']}\n"
        text += "\n"
    if entry["artifacts"]:
        text += "**产出**：" + "、".join(f"`{artifact}`" for artifact in entry["artifacts"]) + "\n\n"
    text += "---\n"
    return text
