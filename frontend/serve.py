#!/usr/bin/env python3
"""
DialogMesh v3.0 — SPA Static File Server
正确 MIME 类型 + SPA 路由回退 + CORS
"""

import http.server
import socketserver
import os
import sys

PORT = 5173
DIRECTORY = os.path.join(os.path.dirname(__file__), "dist")

# 强制覆盖 Windows 注册表错误的 MIME 类型
MIME_TYPES = {
    ".js": "application/javascript",
    ".mjs": "application/javascript",
    ".css": "text/css",
    ".html": "text/html; charset=utf-8",
    ".htm": "text/html; charset=utf-8",
    ".svg": "image/svg+xml",
    ".json": "application/json",
    ".woff": "font/woff",
    ".woff2": "font/woff2",
    ".ttf": "font/ttf",
    ".eot": "application/vnd.ms-fontobject",
    ".otf": "font/otf",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".ico": "image/x-icon",
    ".webp": "image/webp",
}

class SPAHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=DIRECTORY, **kwargs)

    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        super().end_headers()

    def guess_type(self, path):
        ext = os.path.splitext(path)[1].lower()
        return MIME_TYPES.get(ext, super().guess_type(path))

    def do_GET(self):
        # 静态资源直接服务
        if self.path.startswith("/assets/"):
            return super().do_GET()

        # 检查文件是否存在
        file_path = os.path.join(DIRECTORY, self.path.lstrip("/"))
        if os.path.exists(file_path) and os.path.isfile(file_path):
            return super().do_GET()

        # SPA 回退：所有非文件路由返回 index.html
        self.path = "/index.html"
        return super().do_GET()


def main():
    os.chdir(DIRECTORY)
    with socketserver.TCPServer(("", PORT), SPAHandler) as httpd:
        print("=" * 50)
        print("  DialogMesh v3.0 Frontend Server")
        print("  http://localhost:%d" % PORT)
        print("  Directory: %s" % DIRECTORY)
        print("  Press Ctrl+C to stop")
        print("=" * 50)
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n[Server] Stopped.")
            sys.exit(0)


if __name__ == "__main__":
    main()
