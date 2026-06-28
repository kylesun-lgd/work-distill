#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""setup.py — 初始化运行环境（交互式）+ 后续修改配置。

所有数据（网页、entries、索引、项目 MD）都存在一个运行环境目录里。

用法：
  python3 setup.py                    # 交互式初始化（推荐）
  python3 setup.py init --env ~/path  # 指定运行环境路径
  python3 setup.py config             # 修改已有配置
"""
import argparse
import json
import os
import shutil
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(SCRIPT_DIR)
CONFIG_PATH = os.path.join(SKILL_DIR, "config.json")
TEMPLATE_HTML = os.path.join(SKILL_DIR, "templates", "index.html")

DEFAULT_ENV = os.path.expanduser("~/Documents/Zcode/work-distill")
# 全局标记文件：记录运行环境实际路径（非默认时用）。跨工具共享
GLOBAL_ENV_MARKER = os.path.expanduser("~/.work-distill-env")
DEFAULT_PORT = 7788


def discover_env():
    """发现已有运行环境（全局标记 > 默认路径）。跨工具共享。"""
    if os.path.exists(GLOBAL_ENV_MARKER):
        try:
            with open(GLOBAL_ENV_MARKER, "r", encoding="utf-8") as f:
                p = f.read().strip()
                if p and os.path.isdir(p):
                    return p
        except OSError:
            pass
    return DEFAULT_ENV


def err(msg):
    print(f"❌ {msg}", file=sys.stderr)


def ask(prompt, default=""):
    """带默认值的输入，回车用默认。"""
    suffix = f" [{default}]" if default else ""
    val = input(f"? {prompt}{suffix}: ").strip()
    return val if val else default


def ask_required(prompt, default=""):
    while True:
        val = ask(prompt, default)
        if val:
            return val
        print("   ⚠️ 此项必填")


def main():
    ap = argparse.ArgumentParser(description="初始化工作沉淀运行环境 / 修改配置")
    sub = ap.add_subparsers(dest="cmd")

    p_init = sub.add_parser("init", help="交互式初始化")
    p_init.add_argument("--env", default=None, help=f"运行环境路径，默认 {DEFAULT_ENV}")
    p_init.add_argument("--port", type=int, default=None, help=f"本地服务端口，默认 {DEFAULT_PORT}")
    p_init.add_argument("--agent", default=None, help="默认 agent 标识，如 zcode/glm-5.2")

    p_cfg = sub.add_parser("config", help="修改已有配置")
    p_cfg.add_argument("--env", default=None)
    p_cfg.add_argument("--port", type=int, default=None)
    p_cfg.add_argument("--agent", default=None)

    args = ap.parse_args()
    if args.cmd == "config":
        return do_config(args)
    return do_init(args)


def do_init(args):
    print("=" * 50)
    print("  工作沉淀 skill 初始化")
    print("=" * 50)
    print("  所有数据（网页、沉淀记录、项目 MD）将存在一个运行环境目录里，纯本地。")

    # 1. 运行环境路径
    env = args.env or ask("运行环境根目录", DEFAULT_ENV)
    env = os.path.expanduser(env)

    # 2. 端口
    port = args.port or int(ask("本地服务端口", str(DEFAULT_PORT)))

    # 3. 默认 agent
    agent = args.agent or ask("默认 agent 标识（沉淀时可覆盖）", "zcode/glm-5.2")

    # 4. 建运行环境目录结构
    dirs = {
        "根": env,
        "网页": env,
        "沉淀记录": os.path.join(env, "data", "entries"),
        "索引": os.path.join(env, "data", "index"),
        "项目MD": os.path.join(env, "projects"),
    }
    for label, d in dirs.items():
        os.makedirs(d, exist_ok=True)
    print(f"\n📁 运行环境：{env}")
    print(f"   ├─ index.html（网页驾驶舱）")
    print(f"   ├─ data/entries/（沉淀记录正文）")
    print(f"   ├─ data/index/（按月分片索引）")
    print(f"   └─ projects/（项目 MD，agent 先读的提示词）")

    # 5. 复制网页模板
    if os.path.exists(TEMPLATE_HTML):
        shutil.copy(TEMPLATE_HTML, os.path.join(env, "index.html"))
        print(f"\n📄 已写入 index.html 网页驾驶舱")

    # 6. 记录运行环境路径：非默认路径写全局标记（跨工具共享），默认路径不需标记
    if env != DEFAULT_ENV:
        with open(GLOBAL_ENV_MARKER, "w", encoding="utf-8") as f:
            f.write(env)
        print(f"🔗 运行环境路径已记录到全局标记：{GLOBAL_ENV_MARKER}（其它工具装的 skill 会自动发现）")
    else:
        # 默认路径：若之前有标记指向别处，清掉
        if os.path.exists(GLOBAL_ENV_MARKER):
            os.remove(GLOBAL_ENV_MARKER)

    # 7. 写 config.json（只存端口/agent，不存 env 路径——env 靠全局标记或默认路径发现）
    config = {
        "serve_port": port,
        "default_agent": agent,
    }
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
    print(f"⚙️  本工具配置已写入：{CONFIG_PATH}")

    _print_usage(port, env)
    return 0


def do_config(args):
    if not os.path.exists(CONFIG_PATH):
        err("config.json 不存在，请先运行初始化: python3 setup.py")
        return 1
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        config = json.load(f)

    current_env = discover_env()
    changed = False

    if args.env is not None:
        _set_env_path(args.env)
        changed = True
    if args.port is not None:
        config["serve_port"] = args.port
        print(f"✅ 本地服务端口 → {args.port}")
        changed = True
    if args.agent is not None:
        config["default_agent"] = args.agent
        print(f"✅ 默认 agent → {args.agent}")
        changed = True

    if not changed:
        print("当前配置（回车保持不变）：")
        v = ask("运行环境路径", current_env)
        if v and os.path.expanduser(v) != os.path.expanduser(current_env):
            _set_env_path(v)
        cur_port = str(config.get("serve_port", DEFAULT_PORT))
        v = ask("本地服务端口", cur_port)
        if v and v != cur_port:
            config["serve_port"] = int(v)
            print(f"   ✅ 已改为：{config['serve_port']}")
        cur_agent = config.get("default_agent", "")
        v = ask("默认 agent 标识", cur_agent)
        if v and v != cur_agent:
            config["default_agent"] = v
            print(f"   ✅ 已改为：{config['default_agent']}")

    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
    print(f"\n⚙️  config.json 已更新")
    return 0


def _set_env_path(env):
    """更新全局运行环境标记（跨工具共享，不进 config.json）。"""
    env = os.path.expanduser(env)
    if env != DEFAULT_ENV:
        with open(GLOBAL_ENV_MARKER, "w", encoding="utf-8") as f:
            f.write(env)
        print(f"✅ 运行环境路径 → {env}")
    else:
        if os.path.exists(GLOBAL_ENV_MARKER):
            os.remove(GLOBAL_ENV_MARKER)
        print(f"✅ 运行环境路径 → {DEFAULT_ENV}（默认）")
    return env


def _print_usage(port, env):
    print("\n" + "=" * 50)
    print("🎉 初始化完成！后续用法：")
    print("=" * 50)
    print(f"  沉淀:  对 agent 说「沉淀一下」")
    print(f"         agent 会先读 {env}/projects/<项目>.md 了解项目现状，再沉淀")
    print(f"  查看:  python3 {os.path.join(SCRIPT_DIR, 'serve.py')} start")
    print(f"         浏览器打开 http://localhost:{port}")
    print(f"  改配置: python3 {os.path.join(SCRIPT_DIR, 'setup.py')} config")
    print(f"  项目 MD 在: {env}/projects/（agent 的活说明书 + 提示词）")


if __name__ == "__main__":
    sys.exit(main())
