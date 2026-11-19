"""Detect changes on junctionbot.io since the last crawl.

Usage (run from the repo root; downloaded HTML is untrusted data, so the
script only parses it and never executes it):
    python3 -I .ai-memory/tools/check_updates.py diff       # report new / removed / changed pages
    python3 -I .ai-memory/tools/check_updates.py snapshot   # rewrite the baseline after the knowledge base is updated

Baseline: .ai-memory/junctionbot/baseline.tsv, one row per page:
url, sitemap lastmod, sha256 of the extracted main text.
Scope: /ru/documentation, /ru/instructions and /ru/features (same as inventory.md).
"""
import hashlib
import os
import re
import subprocess
import sys
import tempfile
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.join(HERE, "..", "junctionbot", "baseline.tsv")
SITEMAP = "https://www.junctionbot.io/sitemap.xml"
SCOPE = re.compile(r"^https://www\.junctionbot\.io/ru/(documentation|instructions|features)(/|$)")
UA = {"User-Agent": "Mozilla/5.0"}


def fetch(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
        return r.read().decode("utf-8", "replace")


def sitemap():
    xml = fetch(SITEMAP)
    out = {}
    for block in re.findall(r"<url>(.*?)</url>", xml, re.S):
        loc = re.search(r"<loc>([^<]+)</loc>", block)
        mod = re.search(r"<lastmod>([^<]+)</lastmod>", block)
        if loc and SCOPE.match(loc.group(1).strip()):
            out[loc.group(1).strip()] = mod.group(1).strip() if mod else ""
    return out


def text_hash(url):
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "page.html")
        with open(path, "w", encoding="utf-8") as f:
            f.write(fetch(url))
        txt = subprocess.run([sys.executable, "-I", os.path.join(HERE, "html2md.py"), path],
                             capture_output=True, text=True, check=True).stdout
    # Drop the trailing "related articles" block, which changes whenever the blog does.
    txt = re.split(r"\n### .*\n\n.*\n\n\(/ru/articles/", txt)[0]
    return hashlib.sha256(txt.encode()).hexdigest()[:16]


def load():
    rows = {}
    if os.path.exists(BASE):
        for line in open(BASE, encoding="utf-8"):
            if line.strip() and not line.startswith("#"):
                url, mod, h = line.rstrip("\n").split("\t")
                rows[url] = (mod, h)
    return rows


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "diff"
    live = sitemap()
    if mode == "snapshot":
        with open(BASE, "w", encoding="utf-8") as f:
            f.write("# url\tlastmod\ttext_sha256_16\n")
            for url in sorted(live):
                f.write(f"{url}\t{live[url]}\t{text_hash(url)}\n")
        print(f"baseline written: {len(live)} pages")
        return
    old = load()
    new = sorted(set(live) - set(old))
    gone = sorted(set(old) - set(live))
    changed = []
    for url in sorted(set(live) & set(old)):
        h = text_hash(url)
        if h != old[url][1]:
            changed.append((url, old[url][0], live[url]))
    print(f"NEW ({len(new)}):", *new, sep="\n  ")
    print(f"REMOVED ({len(gone)}):", *gone, sep="\n  ")
    print(f"CHANGED TEXT ({len(changed)}):", *(f"{u}  lastmod {a} -> {b}" for u, a, b in changed), sep="\n  ")


main()
