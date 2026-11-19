"""Usage: python3 -I html2md.py <file.html>  -> markdown-ish text of the main content on stdout.

Stdlib only. Keeps headings, paragraphs, list items, table cells, links, image alt, buttons.
Prefers the innermost content <main> (docs-content_*) or <article>; falls back to <body>.
"""
import re
import sys
from html.parser import HTMLParser

SKIP = {"script", "style", "noscript", "svg", "head", "nav", "footer", "form"}
BLOCK = {"p", "div", "section", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "br",
         "blockquote", "pre", "table", "ul", "ol", "figure", "figcaption", "dt", "dd"}


class P(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out, self.skip, self.href = [], 0, None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in SKIP:
            self.skip += 1
            return
        if self.skip:
            return
        if tag in BLOCK:
            self.out.append("\n")
        if tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            self.out.append("#" * int(tag[1]) + " ")
        elif tag == "li":
            self.out.append("- ")
        elif tag in ("td", "th"):
            self.out.append(" | ")
        elif tag == "a" and a.get("href"):
            self.href = a["href"]
        elif tag == "img" and a.get("alt"):
            self.out.append(f" [img: {a['alt']}] ")
        elif tag in ("strong", "b"):
            self.out.append("**")
        elif tag == "code":
            self.out.append("`")

    def handle_endtag(self, tag):
        if tag in SKIP:
            self.skip = max(0, self.skip - 1)
            return
        if self.skip:
            return
        if tag == "a" and self.href:
            self.out.append(f" ({self.href})")
            self.href = None
        elif tag in ("strong", "b"):
            self.out.append("**")
        elif tag == "code":
            self.out.append("`")
        if tag in BLOCK:
            self.out.append("\n")

    def handle_data(self, data):
        if not self.skip:
            self.out.append(re.sub(r"\s+", " ", data))


def pick(html):
    for pat in (r'<main class="docs-content[^"]*"[^>]*>(.*)</main>', r"<article[^>]*>(.*?)</article>",
                r'<main[^>]*>(.*)</main>', r"<body[^>]*>(.*)</body>"):
        m = re.search(pat, html, re.S)
        if m:
            return m.group(1)
    return html


def main():
    html = open(sys.argv[1], encoding="utf-8", errors="replace").read()
    p = P()
    p.feed(pick(html))
    text = "".join(p.out).replace("‍", "").replace(" ", " ")
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n[ \t]+", "\n", text)
    text = re.sub(r"\*\*\s*\*\*", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    print(text.strip())


main()
