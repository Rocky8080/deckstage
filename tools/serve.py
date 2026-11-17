#!/usr/bin/env python3
"""tools/serve.py — 极简静态服务器（给无头导出/Pptx 校验用）

用法：
  python3 tools/serve.py                 # 默认 127.0.0.1:8123，根目录 = 项目根
  python3 tools/serve.py --port 9000
  python3 tools/serve.py --port 0        # 自动挑空闲端口，第一行打印实际端口
  python3 tools/serve.py --root tools/fixtures

也可作为模块用：
  from serve import start_server
  httpd, port = start_server(root, 0)    # port=0 -> 自动
  ...
  httpd.shutdown()
"""
import argparse
import functools
import http.server
import os
import socket
import socketserver
import sys

VERBOSE = False


class Handler(http.server.SimpleHTTPRequestHandler):
    """不缓存 + 安静日志；支持 .mjs / .json 的 MIME。"""

    extensions_map = dict(
        http.server.SimpleHTTPRequestHandler.extensions_map,
        **{
            ".js": "text/javascript; charset=utf-8",
            ".mjs": "text/javascript; charset=utf-8",
            ".css": "text/css; charset=utf-8",
            ".json": "application/json; charset=utf-8",
            ".html": "text/html; charset=utf-8",
            ".svg": "image/svg+xml",
            ".woff2": "font/woff2",
        },
    )
    protocol_version = "HTTP/1.1"

    def end_headers(self):
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        super().end_headers()

    def log_message(self, fmt, *args):
        if VERBOSE:
            sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))


class Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


def start_server(root=".", port=0, host="127.0.0.1"):
    """启动静态服务器（后台线程由调用方用 serve_forever 的线程版启动）。

    返回 (httpd, port, thread) —— thread 已 start()。
    """
    import threading

    root = os.path.abspath(root)
    if not os.path.isdir(root):
        raise SystemExit("目录不存在: %s" % root)
    handler = functools.partial(Handler, directory=root)
    httpd = Server((host, port), handler)
    actual = httpd.socket.getsockname()[1]
    th = threading.Thread(target=httpd.serve_forever, daemon=True)
    th.start()
    return httpd, actual, th


def free_port(host="127.0.0.1"):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((host, 0))
        return s.getsockname()[1]


def project_root():
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main(argv=None):
    global VERBOSE
    ap = argparse.ArgumentParser(description="静态服务器（导出用）")
    ap.add_argument("--port", type=int, default=8123, help="端口，0 = 自动挑空闲端口")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--root", default=None, help="站点根目录，默认项目根")
    ap.add_argument("--verbose", action="store_true")
    a = ap.parse_args(argv)
    VERBOSE = a.verbose

    root = os.path.abspath(a.root or project_root())
    handler = functools.partial(Handler, directory=root)
    httpd = Server((a.host, a.port), handler)
    port = httpd.socket.getsockname()[1]
    print("http://%s:%d/" % (a.host, port), flush=True)
    print("root: %s" % root, file=sys.stderr, flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nbye", file=sys.stderr)
    finally:
        httpd.server_close()


if __name__ == "__main__":
    main()
