# -*- coding: utf-8 -*-
"""镜像同步脚本：从上游目录拉取全部 .py/.js 文件到本目录（仓库根目录）。

- 新增/更新：覆盖写入
- 删除：上游已不存在的同名 .py/.js 会被删除（实现完整镜像）
- 保护：本脚本自身、README、.github、.gitignore 等非爬虫文件不受影响
- 行尾统一为 LF，避免 CRLF/LF 差异导致每次运行都误报变更

本地运行：  python sync.py
GitHub Actions 每 6 小时自动运行（见 .github/workflows/sync.yml）
"""
import os
import re
import sys
import urllib.parse

import requests

BASE = "http://49.235.139.80:81/zjys9/py/"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

# 仅镜像这两种扩展名，避免误删仓库里的其它文件
MANAGED_EXTS = (".py", ".js")

# 这些文件即使以 .py/.js 结尾也不属于上游爬虫，绝不删除
PROTECTED = {"sync.py"}

HERE = os.path.dirname(os.path.abspath(__file__))


def normalize(data: bytes) -> bytes:
    """统一行尾为 LF"""
    return data.replace(b"\r\n", b"\n").replace(b"\r", b"\n")


def fetch_index():
    r = requests.get(BASE, headers=HEADERS, timeout=30)
    r.raise_for_status()
    return r.text


def parse_files(html):
    """返回 {文件名: 链接}，只保留 .py/.js"""
    links = re.findall(r'href="([^"]+)"', html)
    out = {}
    for l in links:
        if l in ("../", "/", "/zjys9/") or l.startswith("?"):
            continue
        name = urllib.parse.unquote(l.split("/")[-1])
        if not name:
            continue
        if not name.lower().endswith(MANAGED_EXTS):
            continue
        out[name] = urllib.parse.urljoin(BASE, l)
    return out


def main():
    html = fetch_index()
    upstream = parse_files(html)

    changed = []

    # 下载/更新上游文件
    for name, url in sorted(upstream.items()):
        path = os.path.join(HERE, name)
        r = requests.get(url, headers=HEADERS, timeout=60)
        r.raise_for_status()
        data = normalize(r.content)
        if os.path.exists(path):
            with open(path, "rb") as f:
                old = normalize(f.read())
            if old == data:
                continue  # 无变化
            changed.append(("更新", name))
        else:
            changed.append(("新增", name))
        with open(path, "wb") as f:
            f.write(data)

    # 删除上游已不存在的文件（跳过受保护文件）
    local_managed = [
        f for f in os.listdir(HERE)
        if os.path.isfile(os.path.join(HERE, f))
        and f.lower().endswith(MANAGED_EXTS)
        and f not in PROTECTED
    ]
    for f in local_managed:
        if f not in upstream:
            os.remove(os.path.join(HERE, f))
            changed.append(("删除", f))

    print(f"上游文件数: {len(upstream)}")
    if changed:
        print("变更:")
        for action, name in changed:
            print(f"  [{action}] {name}")
    else:
        print("无变更，仓库已是最新。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
