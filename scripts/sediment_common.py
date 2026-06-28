import json
import os
import random
import re
import string
import sys
from datetime import datetime, timedelta, timezone

try:
    import fcntl

    LOCK_EX = fcntl.LOCK_EX
    LOCK_UN = fcntl.LOCK_UN
except ImportError:
    fcntl = None
    LOCK_EX = LOCK_UN = 0

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(SCRIPT_DIR)
CONFIG_PATH = os.path.join(SKILL_DIR, "config.json")
DEFAULT_ENV = os.path.expanduser("~/Documents/Zcode/work-distill")
GLOBAL_ENV_MARKER = os.path.expanduser("~/.work-distill-env")
TZ = timezone(timedelta(hours=8))

VALID_TYPES = {"progress", "decision", "knowledge", "archive", "reactivate"}
VALID_STATUS = {"in-progress", "done", "blocked", "archived"}


def file_lock(lock_file, op):
    if fcntl is not None:
        fcntl.flock(lock_file, op)


def discover_env():
    if os.path.exists(GLOBAL_ENV_MARKER):
        try:
            with open(GLOBAL_ENV_MARKER, "r", encoding="utf-8") as f:
                path = f.read().strip()
                if path and os.path.isdir(path):
                    return path
        except OSError:
            pass
    return DEFAULT_ENV


def load_config():
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def get_paths():
    env = discover_env()
    return {
        "env": env,
        "entries": os.path.join(env, "data", "entries"),
        "index_dir": os.path.join(env, "data", "index"),
        "projects": os.path.join(env, "projects"),
    }


def now_iso():
    return datetime.now(TZ).strftime("%Y-%m-%dT%H:%M:%S%z")


def slugify(value):
    slug = re.sub(r"[\s/\\:*?\"<>|]+", "-", value.strip())
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug[:40] or "entry"


def make_slug(name):
    slug = name.strip().lower()
    slug = re.sub(r"[\s/\\:*?\"<>|_]+", "-", slug)
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug or "project"


def err(message):
    print(f"❌ {message}", file=sys.stderr)


def rand4():
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=4))


def check_env_ready(paths):
    if os.path.isdir(paths["env"]) and os.path.exists(os.path.join(paths["env"], "index.html")):
        return True
    err(f"运行环境未初始化：{paths['env']}")
    print("   请先运行初始化（任一工具装了本 skill 都可初始化，运行环境共享）：", file=sys.stderr)
    print(f"   python3 {os.path.join(SCRIPT_DIR, 'setup.py')}", file=sys.stderr)
    print(f"   （运行环境固定在 {DEFAULT_ENV}，其它工具装的同名 skill 会自动发现它）", file=sys.stderr)
    return False


def load_all_entries(paths):
    entries = []
    index_dir = paths["index_dir"]
    if not os.path.isdir(index_dir):
        return entries
    for filename in os.listdir(index_dir):
        if not filename.endswith(".jsonl"):
            continue
        try:
            with open(os.path.join(index_dir, filename), "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entries.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
        except OSError:
            pass
    return entries
