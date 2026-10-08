"""Markdown viewer: serves a .md file in the browser with nice typography, math, and TOC."""
from __future__ import annotations

import argparse
import http.server
import json
import mimetypes
import socketserver
import sys
import threading
import webbrowser
from pathlib import Path

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Markdown Viewer</title>
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.css">
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/highlightjs/cdn-release@11.9.0/build/styles/github.min.css" id="hljs-light">
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/highlightjs/cdn-release@11.9.0/build/styles/github-dark.min.css" id="hljs-dark" disabled>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        :root {
            --bg: #f8f9fa; --text: #2c3e50; --border: #e0e6ed;
            --code-bg: #f1f3f5; --link: #3498db; --heading: #1a252f;
            --sidebar-bg: #ffffff; --sidebar-hover: #f0f4f8;
            --accent: #3498db; --shadow: rgba(0,0,0,0.08);
        }
        [data-theme="dark"] {
            --bg: #0f1419; --text: #d1d5db; --border: #2d3748;
            --code-bg: #1a1f2e; --link: #60a5fa; --heading: #f3f4f6;
            --sidebar-bg: #1a1f2e; --sidebar-hover: #252d3d;
            --accent: #60a5fa; --shadow: rgba(0,0,0,0.3);
        }
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
            color: var(--text); line-height: 1.7;
            transition: background 0.3s, color 0.3s;
        }
        [data-theme="dark"] body {
            background: linear-gradient(135deg, #0f1419 0%, #1a1f2e 100%);
        }
        .container { display: flex; min-height: 100vh; }
        .sidebar {
            width: 280px; background: var(--sidebar-bg); border-right: 1px solid var(--border);
            padding: 24px; position: fixed; height: 100vh; overflow-y: auto;
            transition: transform 0.3s; box-shadow: 2px 0 8px var(--shadow);
        }
        .sidebar h3 {
            font-size: 13px; text-transform: uppercase; letter-spacing: 1px;
            margin-bottom: 20px; color: var(--accent); font-weight: 700;
            padding-bottom: 12px; border-bottom: 2px solid var(--accent);
        }
        .toc { list-style: none; }
        .toc li { margin: 8px 0; }
        .toc a {
            color: var(--text); text-decoration: none; font-size: 14px;
            display: block; padding: 8px 12px; border-radius: 6px; transition: all 0.2s;
            border-left: 3px solid transparent;
        }
        .toc a:hover { 
            background: var(--sidebar-hover); 
            border-left-color: var(--accent);
            transform: translateX(4px);
        }
        .toc .level-2 { padding-left: 16px; }
        .toc .level-3 { padding-left: 32px; }
        .toc .level-4 { padding-left: 48px; }
        .main { 
            flex: 1; margin-left: 280px; padding: 50px; 
            max-width: 80%;
        }
        .controls { 
            position: fixed; top: 24px; right: 24px; 
            display: flex; gap: 12px; z-index: 100;
        }
        button {
            background: linear-gradient(135deg, var(--accent) 0%, #2980b9 100%);
            color: white; border: none; padding: 10px 20px;
            border-radius: 8px; cursor: pointer; font-size: 14px; font-weight: 600;
            transition: all 0.3s; box-shadow: 0 4px 12px var(--shadow);
        }
        button:hover { 
            transform: translateY(-2px); 
            box-shadow: 0 6px 16px var(--shadow);
        }
        .content {
            background: var(--bg);
            padding: 48px;
            border-radius: 12px;
            box-shadow: 0 8px 24px var(--shadow);
            text-align: justify;
            hyphens: auto;
            -webkit-hyphens: auto;
            -ms-hyphens: auto;
            word-wrap: break-word;
            overflow-wrap: break-word;
            word-break: normal;
        }
        .content h1, .content h2, .content h3, .content h4, .content h5, .content h6 {
            color: var(--heading); margin-top: 32px; margin-bottom: 16px;
            font-weight: 700; line-height: 1.3;
            position: relative;
        }
        .content h1 { 
            font-size: 2.2em; 
            background: linear-gradient(135deg, var(--heading) 0%, var(--accent) 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
            padding-bottom: 12px;
            border-bottom: 3px solid var(--accent);
        }
        .content h2 { 
            font-size: 1.6em; 
            padding-bottom: 10px;
            border-bottom: 2px solid var(--border);
        }
        .content h3 { font-size: 1.25em; }
        .content h4 { font-size: 1em; }
        .content p { margin-bottom: 18px; }
        .content a { 
            color: var(--link); text-decoration: none; 
            border-bottom: 1px solid transparent;
            transition: border-bottom 0.2s;
        }
        .content a:hover { 
            border-bottom-color: var(--link);
        }
        .content code {
            background: var(--code-bg); padding: 3px 8px; border-radius: 4px;
            font-size: 88%; font-family: "SFMono-Regular", Consolas, "Liberation Mono", Menlo, monospace;
            border: 1px solid var(--border);
        }
        .content pre {
            background: var(--code-bg); padding: 20px; border-radius: 8px;
            overflow-x: auto; margin-bottom: 20px;
            border: 1px solid var(--border);
            box-shadow: inset 0 2px 4px var(--shadow);
        }
        .content pre code { 
            background: none; padding: 0; font-size: 100%; 
            border: none;
        }
        .content blockquote {
            border-left: 4px solid var(--accent); 
            padding: 16px 20px; margin: 20px 0;
            background: var(--code-bg);
            border-radius: 0 8px 8px 0;
            font-style: italic;
        }
        .content table { 
            border-collapse: collapse; width: 100%; margin-bottom: 20px;
            border-radius: 8px; overflow: hidden;
            box-shadow: 0 2px 8px var(--shadow);
        }
        .content table th, .content table td {
            border: 1px solid var(--border); padding: 12px 16px; text-align: left;
        }
        .content table th { 
            background: linear-gradient(135deg, var(--accent) 0%, #2980b9 100%);
            color: white; font-weight: 600;
        }
        .content table tr:nth-child(even) {
            background: var(--code-bg);
        }
        .content table tr:hover {
            background: var(--sidebar-hover);
        }
        .content img { 
            max-width: 100%; height: auto; border-radius: 8px;
            box-shadow: 0 4px 12px var(--shadow);
            margin: 16px 0;
        }
        .content ul, .content ol { margin-bottom: 18px; padding-left: 2em; }
        .content li { margin: 6px 0; }
        .content hr { 
            border: none; height: 2px; 
            background: linear-gradient(90deg, transparent 0%, var(--accent) 50%, transparent 100%);
            margin: 32px 0;
        }
        .math-display { 
            margin: 20px 0; overflow-x: auto; 
            padding: 16px; background: var(--code-bg);
            border-radius: 8px; border: 1px solid var(--border);
        }
        .math-error { color: #d73a49; font-family: monospace; }
        @media (max-width: 768px) {
            .sidebar { transform: translateX(-100%); }
            .sidebar.open { transform: translateX(0); }
            .main { margin-left: 0; padding: 20px; }
            .menu-toggle { display: block; }
        }
        .menu-toggle { display: none; }
    </style>
</head>
<body>
    <div class="controls">
        <button class="menu-toggle" onclick="toggleSidebar()">☰</button>
        <button onclick="toggleTheme()">🌓 Theme</button>
    </div>
    <div class="container">
        <aside class="sidebar" id="sidebar">
            <h3>Mục lục</h3>
            <ul class="toc" id="toc"><li><em>Đang tải...</em></li></ul>
        </aside>
        <main class="main">
            <div class="content" id="content"><p>Đang tải...</p></div>
        </main>
    </div>
    <script src="https://cdn.jsdelivr.net/npm/markdown-it@14.0.0/dist/markdown-it.min.js"></script>
    <script src="https://cdn.jsdelivr.net/gh/highlightjs/cdn-release@11.9.0/build/highlight.min.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.js"></script>
    <script>
        const md = window.markdownit({
            html: true, linkify: true, typographer: true,
            highlight: function (str, lang) {
                if (lang && hljs.getLanguage(lang)) {
                    try { return hljs.highlight(str, { language: lang }).value; } catch (__) {}
                }
                return '';
            }
        });
        let currentTheme = localStorage.getItem('theme') || 'light';
        document.documentElement.setAttribute('data-theme', currentTheme);
        updateHljsTheme();
        function toggleTheme() {
            currentTheme = currentTheme === 'light' ? 'dark' : 'light';
            document.documentElement.setAttribute('data-theme', currentTheme);
            localStorage.setItem('theme', currentTheme);
            updateHljsTheme();
        }
        function updateHljsTheme() {
            document.getElementById('hljs-light').disabled = currentTheme === 'dark';
            document.getElementById('hljs-dark').disabled = currentTheme === 'light';
        }
        function toggleSidebar() { document.getElementById('sidebar').classList.toggle('open'); }
        fetch('/markdown')
            .then(r => r.text())
            .then(text => {
                text = text.replace(/\\$\\$([\\s\\S]+?)\\$\\$/g, function(match, math) {
                    try {
                        return '<div class="math-display">' + katex.renderToString(math, { displayMode: true, throwOnError: false }) + '</div>';
                    } catch (e) { return '<div class="math-error">' + match + '</div>'; }
                });
                text = text.replace(/(?<!\\$)\\$(?!\\$)(.+?)(?<!\\$)\\$(?!\\$)/g, function(match, math) {
                    try {
                        return katex.renderToString(math, { displayMode: false, throwOnError: false });
                    } catch (e) { return '<span class="math-error">' + match + '</span>'; }
                });
                let html = md.render(text);
                let headingIndex = 0;
                html = html.replace(/<(h[1-6])>(.*?)<\\/\\1>/g, function(match, tag, text) {
                    const id = 'heading-' + (headingIndex++);
                    return '<' + tag + ' id="' + id + '">' + text + '</' + tag + '>';
                });
                document.getElementById('content').innerHTML = html;
                const headings = document.querySelectorAll('.content h1, .content h2, .content h3, .content h4');
                const toc = document.getElementById('toc');
                if (headings.length === 0) {
                    toc.innerHTML = '<li><em>Không có tiêu đề</em></li>';
                } else {
                    let tocHtml = '';
                    headings.forEach(heading => {
                        const level = parseInt(heading.tagName[1]);
                        const text = heading.textContent;
                        const id = heading.id;
                        tocHtml += '<li class="level-' + level + '"><a href="#' + id + '">' + text + '</a></li>';
                    });
                    toc.innerHTML = tocHtml;
                }
                document.addEventListener('click', function(e) {
                    if (e.target.tagName === 'A' && e.target.getAttribute('href').startsWith('#')) {
                        e.preventDefault();
                        const target = document.querySelector(e.target.getAttribute('href'));
                        if (target) target.scrollIntoView({ behavior: 'smooth', block: 'start' });
                    }
                });
            });
    </script>
</body>
</html>"""


class ViewerHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, markdown_path=None, base_dir=None, **kwargs):
        self.markdown_path = markdown_path
        self.base_dir = base_dir
        super().__init__(*args, **kwargs)

    def do_GET(self):
        if self.path == "/":
            self.send_response(200)
            self.send_header("Content-type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(HTML_TEMPLATE.encode("utf-8"))
        elif self.path == "/markdown":
            self.send_response(200)
            self.send_header("Content-type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(self.markdown_path.read_text(encoding="utf-8").encode("utf-8"))
        else:
            file_path = self.base_dir / self.path.lstrip("/")
            if file_path.exists() and file_path.is_file():
                self.send_response(200)
                content_type, _ = mimetypes.guess_type(file_path)
                self.send_header("Content-type", content_type or "application/octet-stream")
                self.end_headers()
                self.wfile.write(file_path.read_bytes())
            else:
                self.send_error(404)

    def log_message(self, format, *args):
        pass


def find_free_port() -> int:
    with socketserver.TCPServer(("localhost", 0), None) as s:
        return s.server_address[1]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("markdown", type=Path, help="Path to .md file")
    parser.add_argument("--port", type=int, default=None, help="Port (default: auto)")
    args = parser.parse_args(argv)

    if not args.markdown.exists():
        print(f"Error: {args.markdown} not found", file=sys.stderr)
        return 1

    port = args.port or find_free_port()
    base_dir = args.markdown.parent.resolve()
    handler = lambda *a, **kw: ViewerHandler(*a, markdown_path=args.markdown, base_dir=base_dir, **kw)

    with socketserver.TCPServer(("localhost", port), handler) as httpd:
        url = f"http://localhost:{port}"
        print(f"Serving {args.markdown.name} at {url}")
        print("Press Ctrl+C to stop")
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nStopped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
