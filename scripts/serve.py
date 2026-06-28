#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""serve.py — 本地静态站点服务 + 产出资料"在文件管理器中显示"端点。

服务运行环境目录（含 index.html 网页驾驶舱）。

用法：
  serve.py start [--port 7788]   后台启动，记录 pid，打开浏览器
  serve.py stop                  停止后台服务
  serve.py status                查看状态
  serve.py run [--port 7788]     前台运行（调试用）
"""
import argparse
import json
import os
import socket
import subprocess
import sys
import platform
import webbrowser
from http.server import HTTPServer, SimpleHTTPRequestHandler

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(SCRIPT_DIR)
CONFIG_PATH = os.path.join(SKILL_DIR, "config.json")
PID_FILE = os.path.join(SKILL_DIR, ".serve.pid")
DEFAULT_ENV = os.path.expanduser("~/Documents/Zcode/work-distill")
GLOBAL_ENV_MARKER = os.path.expanduser("~/.work-distill-env")


def discover_env():
    """发现运行环境路径：全局标记 > 默认路径。跨工具共享。"""
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
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def get_env(cfg):
    # env 路径不读 config，靠 discover_env 跨工具发现
    return discover_env()


class EnvHandler(SimpleHTTPRequestHandler):
    """在运行环境目录起静态服务，并处理 /reveal 端点。"""

    def __init__(self, *a, env=None, **kw):
        self.env = env
        super().__init__(*a, directory=env, **kw)

    def do_GET(self):
        if self.path.startswith("/reveal"):
            self._handle_reveal()
            return
        return super().do_GET()

    def _handle_reveal(self):
        from urllib.parse import urlparse, parse_qs
        raw = self.path
        try:
            raw = raw.encode("latin-1").decode("utf-8")
        except (UnicodeDecodeError, UnicodeEncodeError):
            pass
        q = parse_qs(urlparse(raw).query)
        raw_path = (q.get("path", [""])[0])
        if os.path.isabs(raw_path):
            full = raw_path
        else:
            rel = raw_path.lstrip("/").replace("..", "").strip("/")
            full = os.path.join(self.env, rel) if rel else self.env
        if not os.path.exists(full):
            self._send_text(404, "文件不存在: " + raw_path)
            return
        msg = reveal_in_file_manager(full)
        self._send_text(200, msg)

    def _send_text(self, code, text):
        body = text.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


def reveal_in_file_manager(path):
    sysname = platform.system()
    if sysname == "Darwin":
        subprocess.Popen(["open", "-R", path])
        return f"已在访达中定位：{path}"
    elif sysname == "Windows":
        subprocess.Popen(["explorer", "/select,", path])
        return f"已在资源管理器中定位：{path}"
    else:
        subprocess.Popen(["xdg-open", os.path.dirname(path) or "."])
        return f"已在文件管理器中打开：{os.path.dirname(path) or path}"


def find_free_port(preferred):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    for port in range(preferred, preferred + 20):
        try:
            s.bind(("127.0.0.1", port))
            s.close()
            return port
        except OSError:
            continue
    s.close()
    return None


def make_server(env, port):
    handler = lambda *a, **kw: EnvHandler(*a, env=env, **kw)
    return HTTPServer(("127.0.0.1", port), handler)


def start(port, env, open_browser=True):
    if os.path.exists(PID_FILE):
        try:
            with open(PID_FILE) as f:
                pid = int(f.read().strip())
            os.kill(pid, 0)
            print(f"⚠️  服务已在运行 (pid {pid})")
            return 1
        except (ProcessLookupError, ValueError, OSError):
            os.remove(PID_FILE)

    port = find_free_port(port)
    if port is None:
        print("❌ 7788~7807 端口均被占用")
        return 1

    cmd = [sys.executable, os.path.abspath(__file__), "run", "--port", str(port), "--env", env]
    with open(os.path.join(SKILL_DIR, ".serve.log"), "w") as logf:
        p = subprocess.Popen(cmd, stdout=logf, stderr=logf, start_new_session=True)
    with open(PID_FILE, "w") as f:
        f.write(str(p.pid))
    print(f"✅ 服务已启动 (pid {p.pid}) → http://localhost:{port}")
    if open_browser:
        webbrowser.open(f"http://localhost:{port}")
    return 0


def stop():
    if not os.path.exists(PID_FILE):
        print("ℹ️  服务未在运行")
        return 0
    with open(PID_FILE) as f:
        pid = int(f.read().strip())
    try:
        os.kill(pid, 15)
        print(f"✅ 已停止服务 (pid {pid})")
    except ProcessLookupError:
        print(f"ℹ️  进程 {pid} 已不存在")
    os.remove(PID_FILE)
    return 0


def status():
    if not os.path.exists(PID_FILE):
        print("服务未运行")
        return 0
    with open(PID_FILE) as f:
        pid = int(f.read().strip())
    try:
        os.kill(pid, 0)
        cfg = load_config()
        print(f"服务运行中 (pid {pid})")
        print(f"  环境: {get_env(cfg)}")
        return 0
    except ProcessLookupError:
        print(f"pid 文件残留，进程 {pid} 已退出")
        os.remove(PID_FILE)
        return 1


def main():
    ap = argparse.ArgumentParser(description="工作沉淀本地服务")
    ap.add_argument("action", choices=["start", "stop", "status", "run"])
    ap.add_argument("--port", type=int, default=None)
    ap.add_argument("--env", default=None)
    ap.add_argument("--no-open", action="store_true")
    args = ap.parse_args()

    cfg = load_config()
    env = args.env or get_env(cfg)
    port = args.port or cfg.get("serve_port", 7788)

    if args.action == "start":
        return start(port, env, open_browser=not args.no_open)
    elif args.action == "stop":
        return stop()
    elif args.action == "status":
        return status()
    elif args.action == "run":
        httpd = make_server(env, port)
        print(f" serving {env} at http://localhost:{port} (Ctrl+C 退出)")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n已停止")
        return 0


if __name__ == "__main__":
    sys.exit(main())
