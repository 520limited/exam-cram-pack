#!/usr/bin/env python3
"""exam-cram-pack builder.

Markdown(+YAML front matter) -> 打印级 HTML -> PDF（WeasyPrint）。

用法:
    python scripts/build.py 参考稿.md [--out out] [--stem 输出名] [--css templates/style.css]
    python scripts/build.py parts/            # 目录里按文件名排序拼接
"""
from __future__ import annotations

import argparse
import html
import re
import sys
from pathlib import Path

try:
    import weasyprint
except Exception:  # pragma: no cover
    weasyprint = None

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CSS = ROOT / "templates" / "style.css"

# ---------------------------------------------------------------- front matter


def split_front_matter(text: str) -> tuple[dict, str]:
    meta: dict = {}
    if not text.startswith("---"):
        return meta, text
    end = text.find("\n---", 3)
    if end < 0:
        return meta, text
    block = text[3:end].strip("\n")
    body = text[end + 4 :].lstrip("\n")
    key = None
    for raw in block.splitlines():
        if not raw.strip():
            continue
        if raw.startswith(("  - ", "- ", "  -\t")):
            if key:
                meta.setdefault(key, [])
                if isinstance(meta[key], str):
                    meta[key] = [meta[key]] if meta[key] else []
                meta[key].append(raw.split("-", 1)[1].strip())
            continue
        if ":" in raw and not raw.startswith(" "):
            key, val = raw.split(":", 1)
            key = key.strip()
            val = val.strip()
            meta[key] = val if val else []
    return meta, body


# ------------------------------------------------------------------- inline md

TAG_RE = re.compile(r"\{\{([^{}]+)\}\}")


def inline(text: str, badges: bool = True) -> str:
    out = html.escape(text, quote=False)
    out = out.replace("&lt;br&gt;", "<br>")
    if badges:
        def tag(m):
            label = m.group(1).strip()
            cls = "tag-green" if label in {"补", "补充"} else "tag-red"
            return f'<span class="tag {cls}">{label}</span>'
        out = TAG_RE.sub(tag, out)
    out = re.sub(r"`([^`]+)`", r"<code>\1</code>", out)
    out = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", out)
    out = re.sub(r"(?<![\w*])\*([^*\n]+)\*(?![\w*])", r"<em>\1</em>", out)
    out = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', out)
    return out


def slug(text: str, seen: dict) -> str:
    base = re.sub(r"[^\w\u4e00-\u9fff]+", "-", TAG_RE.sub("", text)).strip("-") or "sec"
    n = seen.get(base, 0) + 1
    seen[base] = n
    return base if n == 1 else f"{base}-{n}"


def clean_heading(text: str) -> str:
    return TAG_RE.sub("", text).replace("**", "").strip()


# -------------------------------------------------------------------- block md

def join_lines(parts: list[str]) -> str:
    out = ""
    for p in parts:
        p = p.strip()
        if not p:
            continue
        if out and re.search(r"[A-Za-z0-9]$", out) and re.match(r"[A-Za-z0-9]", p):
            out += " "
        out += p
    return out


def split_row(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def render(md: str) -> tuple[str, list[tuple[str, str]]]:
    lines = md.splitlines()
    out: list[str] = []
    toc: list[tuple[str, str]] = []
    seen: dict = {}
    i, n = 0, len(lines)
    while i < n:
        raw = lines[i]
        s = raw.strip()

        if not s:
            i += 1
            continue

        # fenced container  ::: selftest
        m = re.match(r"^:::\s*([\w-]+)\s*$", s)
        if m:
            cls = m.group(1)
            i += 1
            buf = []
            while i < n and lines[i].strip() != ":::":
                buf.append(lines[i])
                i += 1
            i += 1
            inner, _ = render("\n".join(buf))
            out.append(f'<div class="{cls}">{inner}</div>')
            continue

        if s.startswith("```"):
            i += 1
            buf = []
            while i < n and not lines[i].strip().startswith("```"):
                buf.append(lines[i])
                i += 1
            i += 1
            out.append("<pre><code>" + html.escape("\n".join(buf)) + "</code></pre>")
            continue

        m = re.match(r"^(#{1,6})\s+(.*)$", s)
        if m:
            level = len(m.group(1))
            title = m.group(2).strip()
            sid = slug(title, seen)
            if level == 1:
                toc.append((clean_heading(title), sid))
            out.append(f'<h{level} id="{sid}">{inline(title)}</h{level}>')
            i += 1
            continue

        if s.startswith(">"):
            buf = []
            while i < n and lines[i].strip().startswith(">"):
                buf.append(lines[i].strip()[1:].strip())
                i += 1
            para = join_lines(buf)
            out.append("<blockquote><p>" + inline(para) + "</p></blockquote>")
            continue

        if s.startswith("|") and i + 1 < n and re.match(r"^\|[\s:\-|]+\|$", lines[i + 1].strip()):
            header = split_row(s)
            i += 2
            rows = []
            while i < n and lines[i].strip().startswith("|"):
                rows.append(split_row(lines[i]))
                i += 1
            thead = "".join(f"<th>{inline(c)}</th>" for c in header)
            tbody = "".join(
                "<tr>" + "".join(f"<td>{inline(c)}</td>" for c in r) + "</tr>" for r in rows
            )
            out.append(f"<table><thead><tr>{thead}</tr></thead><tbody>{tbody}</tbody></table>")
            continue

        if re.match(r"^[-*+]\s+", s):
            items = []
            while i < n and re.match(r"^[-*+]\s+", lines[i].strip()):
                items.append(re.sub(r"^[-*+]\s+", "", lines[i].strip()))
                i += 1
                while i < n and lines[i].startswith(("   ", "\t")) and lines[i].strip():
                    items[-1] += lines[i].strip()
                    i += 1
            out.append("<ul>" + "".join(f"<li>{inline(x)}</li>" for x in items) + "</ul>")
            continue

        m = re.match(r"^(\d+)[.、)]\s*", s)
        if m:
            start = int(m.group(1))
            items = []
            while i < n and re.match(r"^\d+[.、)]\s*", lines[i].strip()):
                items.append(re.sub(r"^\d+[.、)]\s*", "", lines[i].strip()))
                i += 1
                while i < n and lines[i].startswith(("   ", "\t")) and lines[i].strip():
                    items[-1] += lines[i].strip()
                    i += 1
            attr = "" if start == 1 else f' style="counter-reset:list-item {start-1}"'
            out.append(f"<ol{attr}>" + "".join(f"<li>{inline(x)}</li>" for x in items) + "</ol>")
            continue

        buf = [s]
        i += 1
        while i < n and lines[i].strip() and not re.match(
            r"^(#{1,6}\s|:::|```|\||[-*+]\s|\d+[.、)]\s*|>)", lines[i].strip()
        ):
            buf.append(lines[i].strip())
            i += 1
        out.append("<p>" + inline(join_lines(buf)) + "</p>")

    return "\n".join(out), toc


# ------------------------------------------------------------------- assembly

COVER = """<section class="cover">
  <div class="kicker">{kicker}</div>
  <h1>{title}</h1>
  <div class="subtitle">{subtitle}</div>
  <div class="rule"></div>
  <ul>{bullets}</ul>
  <p class="note">{note}</p>
</section>
"""


def build_html(meta: dict, body_html: str, toc: list[tuple[str, str]], css: str) -> str:
    title = meta.get("title", "期末复习资料")
    kicker = meta.get("kicker", "")
    subtitle = meta.get("subtitle", "期 末 复 习 资 料")
    bullets = meta.get("bullets") or []
    if isinstance(bullets, str):
        bullets = [bullets] if bullets else []
    note_bits = [b for b in (meta.get("source_note", ""), meta.get("date_note", "")) if b]
    note = "<br>".join(html.escape(b) for b in note_bits)
    cover = COVER.format(
        kicker=html.escape(kicker),
        title=html.escape(title),
        subtitle=html.escape(subtitle),
        bullets="".join(f"<li>{html.escape(b)}</li>" for b in bullets),
        note=note,
    )
    toc_title = meta.get("toc_title", "目 　 录")
    toc_html = "".join(
        f'<li><a href="#{sid}"><span class="t">{html.escape(t)}</span>'
        f'<span class="d"></span><span class="p" data-href="#{sid}"></span></a></li>'
        for t, sid in toc
    )
    nav = f'<nav class="toc"><h1 class="toc-title">{html.escape(toc_title)}</h1><ul>{toc_html}</ul></nav>'
    return (
        "<!DOCTYPE html>\n<html lang=\"zh-CN\"><head><meta charset=\"utf-8\">"
        f"<title>{html.escape(title)}</title><style>{css}</style></head><body>"
        f"{cover}{nav}<article>{body_html}</article></body></html>"
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("src", help="markdown 文件或 parts 目录")
    ap.add_argument("--out", default=None)
    ap.add_argument("--stem", default=None)
    ap.add_argument("--css", default=str(DEFAULT_CSS))
    args = ap.parse_args()

    src = Path(args.src)
    if src.is_dir():
        files = sorted(p for p in src.glob("*.md") if not p.name.startswith(("_", ".")))
        text = "\n\n".join(p.read_text(encoding="utf-8") for p in files)
    else:
        text = src.read_text(encoding="utf-8")
        files = [src]

    meta, md = split_front_matter(text)
    out_dir = Path(args.out) if args.out else (src.parent / "out" if src.is_file() else src / "out")
    out_dir.mkdir(parents=True, exist_ok=True)

    title = meta.get("title", "期末复习资料")
    stem = args.stem or re.sub(r"[^\w\u4e00-\u9fff]+", "_", f"{title}_期末复习资料").strip("_")
    (out_dir / f"{stem}.md").write_text(text, encoding="utf-8")

    body_html, toc = render(md)
    font_dir = ROOT / "fonts"
    if not (font_dir / "NotoSansCJKsc-Bold.otf").exists():
        try:
            sys.path.insert(0, str(ROOT / "scripts"))
            import prepare_fonts
            prepare_fonts.extract(False)
        except Exception as exc:  # pragma: no cover
            print(f"字体准备失败（将回退到系统字体名）: {exc}", file=sys.stderr)
    css = Path(args.css).read_text(encoding="utf-8")
    running = meta.get("running") or f"{title} · 期末复习资料"
    css = css.replace("__RUNNING__", running.replace('"', '\\"'))
    css = css.replace("__FONT_DIR__", (ROOT / "fonts").as_uri())
    doc = build_html(meta, body_html, toc, css)

    html_path = out_dir / f"{stem}.html"
    html_path.write_text(doc, encoding="utf-8")

    pdf_path = out_dir / f"{stem}.pdf"
    ok = False
    if weasyprint is not None:
        try:
            weasyprint.HTML(string=doc, base_url=str(out_dir)).write_pdf(str(pdf_path))
            ok = True
        except Exception as exc:  # pragma: no cover
            print(f"pdf failed: {exc}", file=sys.stderr)

    print(f"html : {html_path}")
    print(f"pdf  : {pdf_path if ok else '(skipped)'}")
    print(f"目录 : {len(toc)} 条; 正文字数 {len(re.sub(r'\\s+', '', md))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
