#!/usr/bin/env python3
"""Check the README and docs: links, anchors, line references, alt text, assets, secrets.

usage (from the repository root, standard library only):
  python3 docs/check_docs.py            # local checks
  python3 docs/check_docs.py --external # also fetch external links
"""

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FILES = [
    ROOT / "README.md",
    *sorted((ROOT / "docs").glob("*.md")),
    ROOT / "assets/readme/src/README.md",
]
LINK = re.compile(r"\[[^\]\n]*\]\(([^)\s]+)\)")
HTML = re.compile(r"""(?:href|src|srcset)="([^"]+)\"""")
HEADING = re.compile(r"^(#{1,6})\s+(.*)$", re.M)
HTML_HEADING = re.compile(r"<h[1-6][^>]*>(.*?)</h[1-6]>", re.S)
FENCE = re.compile(r"```.*?```", re.S)
INLINE_CODE = re.compile(r"`[^`\n]*`")
# Budgets that keep the README quick to load.
MAX_GIF = 6 * 1024 * 1024
MAX_IMAGE = 1024 * 1024
SECRET = re.compile(
    r"(sk-[A-Za-z0-9]{20,}|ak-[A-Za-z0-9]{20,}|ghp_[A-Za-z0-9]{20,}|"
    r"MODEL_API_KEY=[A-Za-z0-9_\-]{8,}|Bearer\s+[A-Za-z0-9._\-]{20,})"
)


def slug(text):
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"[`*]", "", text)
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = text.strip().lower()
    text = re.sub(r"[^\w\- ]", "", text)
    return text.replace(" ", "-")


def anchors(path, cache={}):
    if path not in cache:
        text = FENCE.sub("", path.read_text())
        found = set()
        counts = {}
        for _, title in HEADING.findall(text):
            base = slug(title)
            n = counts.get(base, 0)
            counts[base] = n + 1
            found.add(base if n == 0 else f"{base}-{n}")
        for title in HTML_HEADING.findall(text):
            found.add(slug(title))
        cache[path] = found
    return cache[path]


def targets(path):
    text = FENCE.sub("", path.read_text())
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    for match in HTML.finditer(text):
        yield match.group(1)
    text = INLINE_CODE.sub("", text)
    for match in LINK.finditer(text):
        yield match.group(1)


def check_local():
    problems = []
    external = set()
    for path in FILES:
        rel = path.relative_to(ROOT)
        for target in targets(path):
            if target.startswith(("http://", "https://")):
                external.add(target)
                continue
            if target.startswith("mailto:"):
                continue
            base, _, fragment = target.partition("#")
            dest = (path.parent / base).resolve() if base else path
            if not dest.exists():
                problems.append(f"{rel}: missing {target}")
                continue
            if not fragment:
                continue
            if fragment.startswith("L") and fragment[1:].isdigit():
                total = dest.read_text().count("\n")
                if int(fragment[1:]) > total:
                    problems.append(f"{rel}: {target} is past the end of the file")
            elif dest.suffix == ".md" and fragment not in anchors(dest):
                problems.append(f"{rel}: no heading for #{fragment} in {dest.name}")
        for img in re.findall(r"<img\b[^>]*>", path.read_text()):
            if 'alt="' not in img or 'alt=""' in img:
                problems.append(f"{rel}: image without alt text: {img[:70]}")
    return problems, external


def check_assets():
    problems = []
    referenced = set()
    for path in FILES:
        for target in targets(path):
            if "assets/" in target and not target.startswith("http"):
                referenced.add((path.parent / target.partition("#")[0]).resolve())
    total = 0
    for asset in sorted(p for p in (ROOT / "assets/readme").iterdir() if p.is_file()):
        size = asset.stat().st_size
        total += size
        limit = MAX_GIF if asset.suffix == ".gif" else MAX_IMAGE
        if size > limit:
            problems.append(f"{asset.name}: {size} bytes is over budget")
        if asset.resolve() not in referenced:
            problems.append(f"{asset.name}: not referenced by the README or docs")
        print(f"  {asset.name:36} {size / 1024:9.1f} KB")
    print(f"  {'total':36} {total / 1024 / 1024:9.2f} MB")
    return problems


def check_secrets():
    problems = []
    tracked = subprocess.run(
        ["git", "ls-files", "README.md", "docs", "assets/readme"],
        cwd=ROOT, capture_output=True, text=True, check=True,
    ).stdout.split()
    for name in tracked:
        path = ROOT / name
        if path.suffix in (".md", ".py", ".svg", ".json") and path.exists():
            if SECRET.search(path.read_text(errors="ignore")):
                problems.append(f"{name}: looks like a credential")
    return problems


def check_external(urls):
    problems = []
    for url in sorted(urls):
        result = subprocess.run(
            ["curl", "-sL", "-o", "/dev/null", "-m", "30", "-A", "Mozilla/5.0", "-w", "%{http_code}", url],
            capture_output=True, text=True,
        )
        status = result.stdout.strip()
        print(f"  {status}  {url}")
        if status != "200":
            problems.append(f"{url}: {status}")
    return problems


def main():
    problems, external = check_local()
    print("assets")
    problems += check_assets()
    problems += check_secrets()
    if "--external" in sys.argv:
        print("external links")
        problems += check_external(external)
    if problems:
        print(f"\n{len(problems)} problem(s)")
        for problem in problems:
            print(" -", problem)
        return 1
    print(f"\nOK: {len(FILES)} documents, {len(external)} external links found")
    return 0


if __name__ == "__main__":
    sys.exit(main())
