import json
import os
from datetime import datetime, timedelta

from sediment_common import LOCK_EX, LOCK_UN, TZ, file_lock, load_all_entries, rand4, slugify
from sediment_project import STATUS_LABELS, TYPE_LABELS


def dedup_next(paths, slug, next_list):
    if not next_list:
        return next_list
    all_entries = load_all_entries(paths)
    cutoff = (datetime.now(TZ) - timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%S")
    existing = set()
    for entry in all_entries:
        if entry.get("slug") != slug or entry.get("ts", "") < cutoff:
            continue
        for next_item in entry.get("next", []):
            text = next_item.get("t", "").strip().lower() if isinstance(next_item, dict) else str(next_item).strip().lower()
            if text:
                existing.add(text)
    kept = []
    for next_item in next_list:
        text = next_item.get("t", "").strip().lower()
        if text and text in existing:
            continue
        existing.add(text)
        kept.append(next_item)
    return kept


def write_repo(paths, entry):
    os.makedirs(paths["entries"], exist_ok=True)
    ym = entry["ts"][:7]
    month_dir = os.path.join(paths["entries"], ym)
    os.makedirs(month_dir, exist_ok=True)

    hhmm = entry["ts"][11:16].replace(":", "")
    filename = f"{entry['ts'][:10]}-{hhmm}-{slugify(entry['summary'])}-{rand4()}.md"
    fragment_path = os.path.join(month_dir, filename)
    rel_path = f"data/entries/{ym}/{filename}"

    with open(fragment_path, "w", encoding="utf-8") as f:
        f.write(fragment_md(entry))

    os.makedirs(paths["index_dir"], exist_ok=True)
    index_file = os.path.join(paths["index_dir"], f"{ym}.jsonl")
    with open(index_file + ".lock", "w") as lock_file:
        file_lock(lock_file, LOCK_EX)
        try:
            with open(index_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(index_row(entry, rel_path), ensure_ascii=False) + "\n")
        finally:
            file_lock(lock_file, LOCK_UN)
    return rel_path


def index_row(entry, rel_path):
    return {
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
        "goal": entry.get("goal", ""),
        "stage": entry.get("stage", ""),
    }


def fragment_md(entry):
    type_label = TYPE_LABELS[entry["type"]]
    status_label = STATUS_LABELS[entry["status"]]
    frontmatter = "---\n"
    frontmatter += f"ts: {entry['ts']}\n"
    frontmatter += f"agent: {entry['agent']}\n"
    frontmatter += f"project: {entry['project']}\n"
    frontmatter += f"slug: {entry['slug']}\n"
    frontmatter += f"type: {entry['type']}\n"
    frontmatter += f"summary: {entry['summary']}\n"
    frontmatter += f"status: {entry['status']}\n"
    if entry.get("goal"):
        frontmatter += f"goal: {entry['goal']}\n"
    if entry.get("stage"):
        frontmatter += f"stage: {entry['stage']}\n"
    if entry["next"]:
        frontmatter += "next:\n"
        for next_item in entry["next"]:
            frontmatter += f"  - t: {next_item['t']}\n"
            if next_item.get("p"):
                frontmatter += f"    p: {next_item['p']}\n"
            if next_item.get("prog"):
                frontmatter += f"    prog: {next_item['prog']}\n"
    if entry["artifacts"]:
        frontmatter += "artifacts:\n"
        for artifact in entry["artifacts"]:
            frontmatter += f"  - {artifact}\n"
    frontmatter += "---\n\n"

    body = f"# {entry['summary']}\n\n"
    body += f"**{type_label} · {status_label}** · {entry['ts']} · {entry['agent']}\n\n"
    if entry["body"]:
        body += entry["body"].strip() + "\n\n"
    if entry["next"]:
        body += "## 下一步\n\n"
        for next_item in entry["next"]:
            extra = []
            if next_item.get("p"):
                extra.append(f"优先级 {next_item['p']}")
            if next_item.get("prog"):
                extra.append(f"进度 {next_item['prog']}")
            extra_text = f"（{'，'.join(extra)}）" if extra else ""
            body += f"- {next_item['t']}{extra_text}\n"
    if entry["artifacts"]:
        body += "\n## 产出\n\n"
        for artifact in entry["artifacts"]:
            body += f"- `{artifact}`\n"
    return frontmatter + body


def list_projects(paths):
    all_entries = load_all_entries(paths)
    if not all_entries:
        print("（运行环境里还没有任何项目，下次沉淀会创建第一个）")
        return
    by_slug = {}
    for entry in all_entries:
        key = entry.get("slug") or entry.get("project", "")
        if key:
            by_slug.setdefault(key, []).append(entry)
    print(f"运行环境里已有 {len(by_slug)} 个项目：")
    print("-" * 60)
    for slug, entries in sorted(by_slug.items(), key=lambda item: max(entry.get("ts", "") for entry in item[1]), reverse=True):
        sorted_entries = sorted(entries, key=lambda entry: entry.get("ts", ""), reverse=True)
        latest = sorted_entries[0]
        non_meta = [entry for entry in sorted_entries if entry.get("type") not in ("archive", "reactivate")]
        status = non_meta[0].get("status", "in-progress") if non_meta else "in-progress"
        status_label = STATUS_LABELS.get(status, status)
        changes = [entry for entry in sorted_entries if entry.get("type") in ("archive", "reactivate")]
        if changes and changes[0].get("type") == "archive":
            status_label = "创意仓库"
        display = latest.get("project", slug)
        brief = latest.get("summary", "")
        last_ts = latest.get("ts", "")[:16].replace("T", " ")
        print(f"  slug: {slug}")
        print(f"  显示名: {display}")
        print(f"  状态: {status_label} · 最近更新: {last_ts} · 共 {len(entries)} 条")
        print(f"  简介: {brief}")
        print("-" * 60)
