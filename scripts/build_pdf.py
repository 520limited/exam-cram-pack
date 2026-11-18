#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把复习包 Markdown 导出为「学术讲义」风格的 HTML / PDF。

用法：
    python build_pdf.py <复习资料.md>                  # 自动选引擎，出 PDF
    python build_pdf.py <复习资料.md> --pdf            # 强制出 PDF
    python build_pdf.py <复习资料.md> --html-only      # 只出 HTML
    python build_pdf.py <复习资料.md> --engine chrome  # auto | weasyprint | chrome | edge
    python build_pdf.py <复习资料.md> --css 主题.css    # 换样式表
    python build_pdf.py <复习资料.md> --no-toc         # 不要目录页
    python build_pdf.py <复习资料.md> --no-cover       # 不要封面

渲染引擎：
    Chrome/Edge —— 默认。桌面浏览器自带，零外部依赖，已实测。
    WeasyPrint  —— 可选（--engine weasyprint）。需 `pip install weasyprint`
                   且系统装有 GTK 3（Windows 无法仅靠 pip 装齐），否则自动回退。

两个引擎都原生支持 CSS 的 @page 边距框与 counter(page)/counter(pages)，
因此页眉、页脚、封面无边框页全部由样式表负责，脚本只做三件事：
     1) Markdown → HTML（含封面、目录）
     2) 两遍渲染：第一遍定位各章页码，第二遍把页码写进目录
     3) 用 PyMuPDF 写入书签（outline）与文档元数据

封面信息写在 Markdown 开头的 YAML 头部：
    ---
    title: 马克思主义与社会科学方法论
    eyebrow: 硕士生思想政治理论课 · 选修课
    subtitle: 期末复习资料
    points:
      - 考点精讲（七章全覆盖）
      - 2020—2025 真题命题规律
    foot: |
      依据材料：教材（112 页扫描件）、课程重点整理（52 页）
      整理日期：2026 年 11 月 17 日
    ---
没有 YAML 头部时，用正文第一个 # 标题当封面主标题，其余留空。
"""
import argparse
import html
import os
import re
import shutil
import subprocess
import sys
import tempfile

sys.stdout.reconfigure(encoding="utf-8")

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL_ROOT = os.path.dirname(HERE)
DEFAULT_CSS = os.path.join(SKILL_ROOT, "assets", "pack.css")

TAG_CLASSES = [("真题", "tag-zt"), ("补", "tag-bu"), ("推断", "tag-td"), ("待核", "tag-hc")]
LIST_RE = re.compile(r"^(\s*)([-*+]|\d+[.、])\s+(.*)$")
TABLE_SEP_RE = re.compile(r"^\s*\|?[\s:|-]{3,}\|?\s*$")


# ============================================================== front matter

def split_front_matter(text):
    """解析开头的 --- ... --- 块，返回 (dict, body)。"""
    text = text.lstrip("\ufeff").replace("\r\n", "\n").replace("\r", "\n")
    if not text.startswith("---"):
        return {}, text
    m = re.match(r"^---[ \t]*\n(.*?)\n---[ \t]*\n?", text, re.S)
    if not m:
        return {}, text
    raw, body = m.group(1), text[m.end():]

    meta, key, buf = {}, None, []
    for line in raw.split("\n"):
        if not line.strip():
            continue
        lm = re.match(r"^([A-Za-z_][\w-]*)\s*:\s*(.*)$", line)
        if lm:
            if key:
                meta[key] = _coerce(buf)
            key, buf = lm.group(1), [lm.group(2)]
        else:
            buf.append(line)
    if key:
        meta[key] = _coerce(buf)
    return meta, body


def _coerce(buf):
    items = [b for b in buf if re.match(r"^\s*-\s+", b)]
    if items and all(re.match(r"^\s*-\s+", b) for b in buf if b.strip()):
        return [re.sub(r"^\s*-\s+", "", b).strip() for b in items]
    txt = "\n".join(buf).strip()
    if txt in ("|", ">"):
        return ""
    return re.sub(r"^[|>]\s?", "", txt, flags=re.M).strip()


# ============================================================== inline

def smart_quotes(s):
    """把直引号转成中文弯引号（成对交替）。已是弯引号的原样保留。"""
    out, open_q = [], True
    for ch in s:
        if ch == '"':
            out.append("\u201c" if open_q else "\u201d")
            open_q = not open_q
        else:
            if ch in "\u201c\u201d":
                open_q = True if ch == "\u201c" else open_q
            out.append(ch)
    return "".join(out)


def inline(s):
    """行内 Markdown → HTML。"""
    s = smart_quotes(html.escape(s, quote=False))

    codes = []

    def stash_code(m):
        codes.append(m.group(1))
        return f"\x00C{len(codes) - 1}\x00"

    s = re.sub(r"`([^`]+)`", stash_code, s)

    def tag_repl(m):
        inner = m.group(1)
        for key, cls in TAG_CLASSES:
            if inner.startswith(key):
                return f'<span class="tag {cls}">{inner}</span>'
        return f'<span class="tag tag-td">{inner}</span>'

    s = re.sub(r"〔([^〕]+)〕", tag_repl, s)

    bolds = []

    def stash_bold(m):
        bolds.append(m.group(1))
        return f"\x00B{len(bolds) - 1}\x00"

    s = re.sub(r"\*\*(.+?)\*\*", stash_bold, s)
    s = re.sub(r"(?<![\w*])\*([^*\n]+?)\*(?![\w*])", r"<em>\1</em>", s)
    s = re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)", r'<a href="\2">\1</a>', s)

    for i, b in enumerate(bolds):
        s = s.replace(f"\x00B{i}\x00", f"<strong>{b}</strong>")
    for i, c in enumerate(codes):
        s = s.replace(f"\x00C{i}\x00", f"<code>{c}</code>")
    return s


def plain(s):
    """去掉行内标记，只留纯文本（用于目录、书签、页眉）。保留中文弯引号。"""
    s = re.sub(r"`[^`]*`", "", s or "")
    s = re.sub(r"〔[^〕]*〕", "", s)
    s = re.sub(r"[*_`#>\[\]]", "", s)
    s = smart_quotes(s)          # 书签/页眉里也用弯引号，与正文一致
    return re.sub(r"\s+", " ", s).strip()


# ============================================================== block parser

def parse_blocks(body):
    lines = body.split("\n")
    blocks, i, n = [], 0, len(lines)

    while i < n:
        line, stripped = lines[i], lines[i].strip()

        if not stripped:
            i += 1
            continue

        if re.fullmatch(r"-{3,}|\*{3,}|_{3,}", stripped):
            blocks.append(("hr", None))
            i += 1
            continue

        m = re.match(r"^(#{1,6})\s+(.*)$", line)
        if m:
            blocks.append((f"h{len(m.group(1))}", m.group(2).strip()))
            i += 1
            continue

        if stripped.startswith("```"):
            i += 1
            buf = []
            while i < n and not lines[i].strip().startswith("```"):
                buf.append(lines[i])
                i += 1
            i += 1
            blocks.append(("code", "\n".join(buf)))
            continue

        if stripped.startswith(">"):
            buf = []
            while i < n and lines[i].strip().startswith(">"):
                buf.append(re.sub(r"^\s*>\s?", "", lines[i]))
                i += 1
            blocks.append(("quote", "\n".join(buf)))
            continue

        if stripped.startswith("|") and i + 1 < n and TABLE_SEP_RE.match(lines[i + 1].strip()):
            head = _row(stripped)
            aligns = _aligns(lines[i + 1].strip(), len(head))
            i += 2
            rows = []
            while i < n and lines[i].strip().startswith("|"):
                rows.append(_row(lines[i].strip()))
                i += 1
            blocks.append(("table", {"head": head, "rows": rows, "aligns": aligns}))
            continue

        if LIST_RE.match(line):
            items = []
            while i < n:
                cur = lines[i]
                lm = LIST_RE.match(cur)
                if lm:
                    items.append({
                        "indent": len(lm.group(1).expandtabs(4)),
                        "ordered": lm.group(2)[0].isdigit(),
                        "text": lm.group(3).strip(),
                    })
                    i += 1
                    continue
                # 缩进续行并入上一条（如金句下的"　用在：……"）
                if cur.strip() and items and cur[:1] in (" ", "\t", "\u3000"):
                    items[-1]["text"] += "\n" + cur.strip()
                    i += 1
                    continue
                # 空行之后若仍是同级/更深层的列表项，视为同一个列表（保留编号连续）
                if not cur.strip():
                    j = i
                    while j < n and not lines[j].strip():
                        j += 1
                    if j < n and LIST_RE.match(lines[j]):
                        nxt = LIST_RE.match(lines[j])
                        ind = len(nxt.group(1).expandtabs(4))
                        if items and ind >= items[0]["indent"]:
                            i = j
                            continue
                    break
                break
            blocks.append(("list", {"items": items,
                                    "ordered": items[0]["ordered"] if items else False}))
            continue

        buf = [stripped]
        i += 1
        while i < n:
            nxt = lines[i]
            if not nxt.strip():
                break
            if re.match(r"^#{1,6}\s", nxt) or nxt.strip().startswith((">", "```")):
                break
            if LIST_RE.match(nxt):
                break
            if nxt.strip().startswith("|") and i + 1 < n and TABLE_SEP_RE.match(lines[i + 1].strip()):
                break
            if re.fullmatch(r"-{3,}|\*{3,}", nxt.strip()):
                break
            buf.append(nxt.strip())
            i += 1
        blocks.append(("p", "\n".join(buf)))

    return blocks


def _row(line):
    line = line.strip()
    if line.startswith("|"):
        line = line[1:]
    if line.endswith("|"):
        line = line[:-1]
    return [c.strip() for c in line.split("|")]


def _aligns(sep, count):
    out = []
    for c in _row(sep):
        c = c.strip()
        if c.startswith(":") and c.endswith(":"):
            out.append("center")
        elif c.endswith(":"):
            out.append("right")
        else:
            out.append("left")
    while len(out) < count:
        out.append("left")
    return out


# ============================================================== renderers

def render_list(payload):
    items = payload["items"]
    out, stack = [], []
    for it in items:
        tag = "ol" if it["ordered"] else "ul"
        ind = it["indent"]
        if not stack:
            out.append(f"<{tag}>")
            stack.append((ind, tag))
        else:
            while len(stack) > 1 and ind < stack[-1][0]:
                out.append(f"</{stack.pop()[1]}>")
            if ind > stack[-1][0]:
                out.append(f"<{tag}>")
                stack.append((ind, tag))
        parts = it["text"].split("\n")
        body = inline(parts[0])
        for extra in parts[1:]:
            body += "<br>" + inline(extra)
        out.append(f"<li>{body}</li>")
    while stack:
        out.append(f"</{stack.pop()[1]}>")
    html_str = "".join(out)

    # 长有序列表（金句、清单类）套米色面板，与参考件观感一致
    if payload.get("ordered") and len(items) >= 8:
        html_str = f'<div class="panel-cream">{html_str}</div>'
    return html_str


def _col_widths(t, ncol, usable_pt=516.0):
    """估算各列宽度百分比，配合 table-layout:fixed 使用。

    中文表格列宽的几个坑：
      1. `table-layout:auto` 时 WeasyPrint 倾向均分列宽，把"年份"这类窄列
         撑宽、把内容列挤窄，整页行高翻倍；
      2. 改成 fixed 后，若某一列权重算得过小（如只填"—"的列），会把字挤成
         竖排。所以每列都有**基于表头长度的硬下限**；
      3. 徽章 `〔真题 2024〕` 是 inline-block + nowrap，**不能折行**。列宽一旦
         小于它的实际渲染宽度就会溢出、压到相邻列上（表格里最常见的一类
         bug）。所以"整格只有一个徽章"的单元格要单独计为硬下限。

    宽度一律按磅值估算，最后再换算成百分比，避免单位混用。
    """
    if ncol == 0:
        return []

    # 与 pack.css 对齐的度量参数
    CELL_FONT = 8.6          # table 的 font-size
    CELL_PAD = 4.5           # td/th 的左右 padding 各一个
    CELL_BORDER = 0.45       # td/th 的单边边框
    TAG_FONT = 7.2           # .tag 的 font-size
    TAG_CHROME = 3.8         # .tag 的 padding(1.2*2) + border(0.7*2)
    TAG_MARGIN = 1.2         # 表格内 .tag 左右 margin 各 0.6
    SLACK = 5.0              # 亚像素与字距余量；SimSun 全角字实际略宽于字号，留足才不折行

    def cjk_w(ch):
        """中文字体下（SimSun / china-s），**所有字符都按全角算**。
        实测：7.2pt 徽章里 '2024' 与 '真题' 同宽（各 7.2pt/字）；
        所以不能对 ASCII 打折，否则含数字的徽章会被低估约一半。"""
        return CELL_FONT

    def tag_w(ch):
        return TAG_FONT

    def text_pt(s):
        """去掉标签后剩下的纯文本宽度（磅）。"""
        s = re.sub(r"<[^>]+>", "", s or "")
        s = re.sub(r"〔[^〕]*〕", "", s)
        s = re.sub(r"`[^`]*`", "", s)        # 行内 code 也按徽章处理，单独算
        return sum(cjk_w(ch) for ch in s)

    def tags_pt(s):
        """所有徽章/行内 code 的总宽度（磅），含其内外边距。"""
        s = s or ""
        total = 0.0
        for inner in re.findall(r"〔([^〕]*)〕", s):
            inner = inner.strip()
            if inner:
                total += (sum(TAG_FONT if ord(c) > 0x2E80 else TAG_FONT * 0.5
                              for c in inner) + TAG_CHROME + TAG_MARGIN)
        for inner in re.findall(r"`([^`]*)`", s):
            inner = inner.strip()
            if inner:
                total += (sum(TAG_FONT if ord(c) > 0x2E80 else TAG_FONT * 0.5
                              for c in inner) + TAG_CHROME + TAG_MARGIN)
        return total

    def cell_pt(s):
        return text_pt(s) + tags_pt(s)

    def unbreakable_pt(s):
        """整格只有一个徽章/短 code 时，这个宽度是死下限（nowrap 不可折行）。"""
        s = re.sub(r"\s+", "", s or "")
        if re.fullmatch(r"〔[^〕]+〕", s):
            return tags_pt(s)
        if re.fullmatch(r"`[^`]+`", s):
            return tags_pt(s)
        return 0.0

    weights, min_pct = [], []

    for j in range(ncol):
        head_raw = t["head"][j] if j < len(t["head"]) else ""
        head_pt = cell_pt(head_raw)

        cells = [row[j] for row in t["rows"] if j < len(row)]
        cell_pts = sorted(cell_pt(c) for c in cells) or [head_pt]
        p75 = cell_pts[int(len(cell_pts) * 0.75)] if len(cell_pts) > 1 else cell_pts[0]

        # 硬下限：表头宽度、以及不可折行的徽章单元格
        hard = max(head_pt, max([unbreakable_pt(c) for c in cells], default=0.0))

        # 权重：常规取 75 分位，但不低于硬下限；上限防止单列独大
        w = max(hard, min(p75, 320.0))
        weights.append(w)

        # 该列必须占的最小百分比。
        # table-layout:fixed 下 <col> 的 width 已含 padding 与 border，
        # 所以这里算的是"整列"宽度：内容硬下限 + 左右 padding + 双边框 + 余量。
        col_min_pt = hard + CELL_PAD * 2 + CELL_BORDER * 2 + SLACK
        min_pct.append(100.0 * col_min_pt / usable_pt)

    total = sum(weights) or 1.0
    pct = [w / total * 100.0 for w in weights]

    # 逐轮把低于各自下限的列抬到下限，按比例压缩**仍有余量**的列。
    # 关键：被抬升的列被冻结（frozen），后续轮次不再压缩，否则会被弹回去。
    frozen = set()
    for _ in range(12):
        low = [i for i, p in enumerate(pct)
               if i not in frozen and p < min_pct[i] - 1e-9]
        if not low:
            break
        deficit = sum(min_pct[i] - pct[i] for i in low)
        high = [i for i, p in enumerate(pct) if i not in frozen and i not in low]
        # 只从"高于自己下限"的列里收，收不满就按比例收
        pool = sum(pct[i] for i in high) or 1.0
        for i in low:
            pct[i] = min_pct[i]
            frozen.add(i)
        for i in high:
            pct[i] -= deficit * (pct[i] / pool)

    # 归一化前先确保没有负数
    pct = [max(p, 1.0) for p in pct]
    s = sum(pct) or 1.0
    pct = [p / s * 100.0 for p in pct]

    # 归一化可能把徽章列又压下来一点点，做一次补偿：
    # 把仍低于下限的差额从最大列身上扣掉。
    for i in range(ncol):
        gap = min_pct[i] - pct[i]
        if gap > 0.01:
            j = max(range(ncol), key=lambda k: pct[k])
            if pct[j] - gap > 1.0:
                pct[j] -= gap
                pct[i] += gap

    return [round(p, 2) for p in pct]


def render_table(t):
    ncol = len(t["head"]) if t["head"] else (len(t["rows"][0]) if t["rows"] else 0)
    pct = _col_widths(t, ncol)

    out = ["<table>"]
    if pct:
        out.append("<colgroup>")
        for w in pct:
            out.append(f'<col style="width:{w}%">')
        out.append("</colgroup>")

    out.append("<thead><tr>")
    for j, cell in enumerate(t["head"]):
        al = t["aligns"][j] if j < len(t["aligns"]) else "left"
        out.append(f'<th class="al-{al}">{inline(cell)}</th>')
    out.append("</tr></thead><tbody>")
    for row in t["rows"]:
        out.append("<tr>")
        for j, cell in enumerate(row):
            al = t["aligns"][j] if j < len(t["aligns"]) else "left"
            out.append(f'<td class="al-{al}">{inline(cell)}</td>')
        out.append("</tr>")
    out.append("</tbody></table>")
    return "".join(out)


def render_quote(text):
    paras = [p for p in text.split("\n") if p.strip()]
    if len(paras) == 1:
        return f"<blockquote><p>{inline(paras[0])}</p></blockquote>"
    return "<blockquote>" + "".join(f"<p>{inline(p)}</p>" for p in paras) + "</blockquote>"


# ============================================================== html assembly

def build_html(meta, body, css, want_toc=True, want_cover=True, page_numbers=None):
    blocks = parse_blocks(body)

    # 丢弃手写目录（统一由脚本生成）
    cleaned, skipping = [], False
    for kind, payload in blocks:
        if kind == "h2" and re.fullmatch(r"目\s*录", plain(payload or "")):
            skipping = True
            continue
        if skipping and kind == "h1":
            skipping = False
        if not skipping:
            cleaned.append((kind, payload))
    blocks = cleaned

    title = meta.get("title") or "复习资料"
    subtitle = meta.get("subtitle") or ""
    eyebrow = meta.get("eyebrow") or ""
    points = meta.get("points") or []
    foot = meta.get("foot") or ""
    if isinstance(points, str):
        points = [p.strip() for p in points.split("\n") if p.strip()]
    foot_lines = ([f.strip() for f in foot.split("\n") if f.strip()]
                  if isinstance(foot, str) else list(foot))

    headings = [{"level": int(kind[1]), "text": payload, "plain": plain(payload)}
                for kind, payload in blocks if kind in ("h1", "h2")]

    t_plain = plain(title)
    running = f"{t_plain} · {plain(subtitle)}" if subtitle else t_plain

    # 页眉页脚：两个引擎都支持 @page 边距框与 counter()
    page_css = [
        "\n/* --- 由 build_pdf.py 注入 --- */",
        "@page { @top-right { content: \"%s\"; } }" % running.replace('"', "'"),
    ]
    if want_cover:
        page_css.append(
            "@page :first { margin: 0;"
            " @top-right { content: none; }"
            " @bottom-center { content: none; } }"
        )
    page_css = "\n".join(page_css) + "\n"

    out = ['<!DOCTYPE html>', '<html lang="zh-CN"><head><meta charset="utf-8">',
           f"<title>{html.escape(t_plain)}</title>",
           f"<style>\n{css}\n{page_css}</style></head><body>"]

    # ---------------- 封面
    if want_cover:
        out.append('<section class="cover"><div class="cover-inner">')
        if eyebrow:
            out.append(f'<div class="cover-eyebrow">{inline(eyebrow)}</div>')
        out.append(f'<div class="cover-title">{inline(title)}</div>')
        if subtitle:
            out.append(f'<div class="cover-subtitle">{inline(subtitle)}</div>')
        out.append('<div class="cover-rule"></div>')
        if points:
            out.append('<ul class="cover-points">')
            out.extend(f"<li>{inline(p)}</li>" for p in points)
            out.append("</ul>")
        out.append("</div>")
        if foot_lines:
            out.append('<div class="cover-foot">')
            out.extend(f"<p>{inline(f)}</p>" for f in foot_lines)
            out.append("</div>")
        out.append("</section>")

    # ---------------- 目录
    if want_toc and headings:
        out.append('<section class="toc-page"><div class="toc-title">目\u3000录</div><div class="toc">')
        for idx, h in enumerate(headings):
            if h["level"] != 1:
                continue
            num = page_numbers.get(h["plain"], "") if page_numbers is not None else ""
            out.append(
                f'<div class="toc-entry"><span class="toc-name">'
                f'<a href="#sec-{idx}">{inline(h["text"])}</a></span>'
                f'<span class="toc-dots"></span>'
                f'<span class="toc-page-no">{num}</span></div>')
        out.append("</div></section>")

    # ---------------- 正文
    counter = {"n": 0}
    idx = 0
    while idx < len(blocks):
        kind, payload = blocks[idx]

        if kind == "h1":
            # 若这一节正文只有一个列表（金句/速记那样），整节套米色面板
            sec_end = idx + 1
            while sec_end < len(blocks) and blocks[sec_end][0] != "h1":
                sec_end += 1
            body_kinds = [k for k, _ in blocks[idx + 1:sec_end]
                          if k not in ("hr",)]
            only_list = len(body_kinds) == 1 and body_kinds[0] == "list"

            anchor = f' id="sec-{counter["n"]}"'
            counter["n"] += 1
            out.append(f"<h1{anchor}>{inline(payload)}</h1>")

            if only_list:
                out.append('<div class="panel-cream">')
                out.append(render_list(blocks[idx + 1][1]))
                out.append("</div>")
                idx = sec_end
                continue
            idx += 1
            continue

        if kind in ("h2", "h3", "h4", "h5", "h6"):
            lvl = int(kind[1])
            anchor = ""
            if lvl == 2:
                anchor = f' id="sec-{counter["n"]}"'
                counter["n"] += 1
            out.append(f"<{kind}{anchor}>{inline(payload)}</{kind}>")
        elif kind == "p":
            cls = ' class="tight"' if len(payload) < 14 and payload.endswith(("：", ":")) else ""
            out.append(f"<p{cls}>{inline(payload)}</p>")
        elif kind == "table":
            out.append(render_table(payload))
        elif kind == "list":
            out.append(render_list(payload))
        elif kind == "quote":
            out.append(render_quote(payload))
        elif kind == "hr":
            out.append("<hr>")
        elif kind == "code":
            out.append(f"<pre><code>{html.escape(payload)}</code></pre>")

        idx += 1

    out.append("</body></html>")
    return "\n".join(out), headings


# ============================================================== engines

def find_browser(prefer="auto"):
    cands = []
    if prefer in ("auto", "chrome"):
        cands += [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            shutil.which("google-chrome") or "",
            shutil.which("chromium") or "",
            shutil.which("chromium-browser") or "",
        ]
    if prefer in ("auto", "edge"):
        cands += [
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
            "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
            shutil.which("microsoft-edge") or "",
        ]
    for c in cands:
        if c and os.path.exists(c):
            return c
    return None


# ---------------------------------------------------------------- WeasyPrint

# GTK 运行库常见位置（Windows）。WeasyPrint 靠 ctypes/cffi 加载 libgobject 等，
# 必须让这些 DLL 出现在 PATH 或 WEASYPRINT_DLL_DIRECTORIES 里。
GTK_HINT_DIRS = [
    r"C:\Program Files\GTK3-Runtime Win64\bin",
    r"C:\msys64\ucrt64\bin",
    r"C:\msys64\mingw64\bin",
    # conda 环境：Library\bin 是 DLL 实际所在，根目录放 python.exe
    r"D:\miniConda\envs\weasy\Library\bin",
    os.path.expandvars(r"%CONDA_PREFIX%\Library\bin"),
    os.path.expandvars(r"%USERPROFILE%\miniconda3\envs\weasy\Library\bin"),
    os.path.expandvars(r"%USERPROFILE%\anaconda3\envs\weasy\Library\bin"),
]


def _conda_python_candidates():
    """列出可能的 Python 解释器，**优先带 GTK 的环境**。

    WeasyPrint 的 pip 包装在哪都行，但缺 GTK 就 import 失败。所以先排
    conda 的 `weasy` 环境（我们推荐用它装 GTK），再排当前解释器。
    """
    cands = []
    roots = [
        r"D:\miniConda",
        os.path.expandvars(r"%CONDA_PREFIX%"),
        os.path.expandvars(r"%USERPROFILE%\miniconda3"),
        os.path.expandvars(r"%USERPROFILE%\anaconda3"),
        os.path.expandvars(r"%LOCALAPPDATA%\miniconda3"),
        os.path.expandvars(r"%ProgramData%\miniconda3"),
        "/opt/conda",
    ]
    # 1) 专门的 GTK 环境优先
    for root in roots:
        if not root or not os.path.isdir(root):
            continue
        for env in ("weasy", "weasyprint", "gtk"):
            base = os.path.join(root, "envs", env)
            for exe in ("python.exe", os.path.join("bin", "python3")):
                p = os.path.join(base, exe)
                if os.path.isfile(p):
                    cands.append(p)
    # 2) 当前解释器
    if sys.executable not in cands:
        cands.append(sys.executable)
    # 3) 其他 conda 环境（base 等）
    for root in roots:
        if not root or not os.path.isdir(root):
            continue
        for exe in ("python.exe", os.path.join("bin", "python3")):
            p = os.path.join(root, exe)
            if os.path.isfile(p) and p not in cands:
                cands.append(p)
    return cands


def _gtk_env(interp):
    """构造带 GTK DLL 路径的环境变量。"""
    env = os.environ.copy()
    extra = []

    # 解释器所在环境下的 Library\bin（conda 布局）
    env_root = os.path.dirname(os.path.dirname(interp))
    for p in (os.path.join(env_root, "Library", "bin"),
              os.path.join(os.path.dirname(interp), "Library", "bin")):
        if os.path.isdir(p):
            extra.append(p)

    for p in GTK_HINT_DIRS:
        if p and os.path.isdir(p):
            extra.append(p)

    # 去重保序
    seen, uniq = set(), []
    for p in extra:
        if p not in seen:
            seen.add(p)
            uniq.append(p)

    if uniq:
        env["PATH"] = ";".join(uniq) + ";" + env.get("PATH", "")
        env["WEASYPRINT_DLL_DIRECTORIES"] = ";".join(uniq)
    return env


_PROBE_CACHE = {}


def weasyprint_available():
    """探测哪个 Python 解释器能 import WeasyPrint（含 GTK）。

    返回解释器路径，失败返回 None。缺 GTK 时 WeasyPrint 会往 fd 2 打一大段
    警告（绕过 sys.stderr），因此放到子进程里跑并吞掉输出。
    """
    if "interp" in _PROBE_CACHE:
        return _PROBE_CACHE["interp"]

    for interp in _conda_python_candidates():
        try:
            r = subprocess.run(
                [interp, "-c", "from weasyprint import HTML"],
                capture_output=True, timeout=90, env=_gtk_env(interp),
            )
            if r.returncode == 0:
                _PROBE_CACHE["interp"] = interp
                return interp
        except Exception:
            continue

    _PROBE_CACHE["interp"] = None
    return None


def render_weasyprint(html_path, pdf_path, interp):
    """用指定解释器跑一个小渲染脚本（子进程），避免主进程被 GTK 版本影响。"""
    script = os.path.join(tempfile.mkdtemp(prefix="packwp-"), "render.py")
    with open(script, "w", encoding="utf-8") as f:
        f.write(
            "import sys\n"
            "from weasyprint import HTML\n"
            "src, dst = sys.argv[1], sys.argv[2]\n"
            "HTML(filename=src).write_pdf(dst)\n"
        )
    try:
        r = subprocess.run(
            [interp, script, os.path.abspath(html_path), os.path.abspath(pdf_path)],
            capture_output=True, timeout=600, env=_gtk_env(interp),
        )
        if r.returncode != 0:
            msg = (r.stderr or b"").decode("utf-8", "ignore").strip()
            print(f"[x] WeasyPrint 渲染失败：\n{msg[-1200:]}", file=sys.stderr)
            return False
    finally:
        shutil.rmtree(os.path.dirname(script), ignore_errors=True)
    return os.path.exists(pdf_path) and os.path.getsize(pdf_path) > 0


def render_browser(html_path, pdf_path, browser):
    url = "file:///" + os.path.abspath(html_path).replace("\\", "/")
    profile = tempfile.mkdtemp(prefix="packpdf-")
    cmd = [
        browser, "--headless=new", "--disable-gpu", "--no-sandbox",
        "--no-pdf-header-footer", "--run-all-compositor-stages-before-draw",
        "--virtual-time-budget=12000",
        f"--user-data-dir={profile}",
        f"--print-to-pdf={os.path.abspath(pdf_path)}",
        url,
    ]
    try:
        subprocess.run(cmd, check=False, capture_output=True, timeout=300)
    finally:
        shutil.rmtree(profile, ignore_errors=True)
    return os.path.exists(pdf_path) and os.path.getsize(pdf_path) > 0


# ============================================================== 页码定位 & 书签

def locate_pages(pdf_path, headings):
    """定位每个一/二级标题所在页码（1 起），跳过封面与目录页。"""
    import pymupdf

    doc = pymupdf.open(pdf_path)
    texts = [re.sub(r"\s+", "", doc[p].get_text()) for p in range(doc.page_count)]
    doc.close()

    l1 = [re.sub(r"\s+", "", h["plain"]) for h in headings if h["level"] == 1]
    # 目录页：同时出现 >=3 个一级标题（取最短的 12 字做特征）
    toc_pages = set()
    for p, txt in enumerate(texts):
        if sum(1 for n in l1 if n and n[:12] in txt) >= 3:
            toc_pages.add(p)

    pages, cursor = {}, (max(toc_pages) + 1) if toc_pages else 1
    for h in headings:
        if h["level"] not in (1, 2):
            continue
        needle = re.sub(r"\s+", "", h["plain"])[:12]
        if not needle:
            continue
        for p in range(cursor, len(texts)):
            if p in toc_pages:
                continue
            if needle in texts[p]:
                pages[h["plain"]] = p + 1
                cursor = p
                break
    return pages


def write_bookmarks(pdf_path, headings, meta):
    """写入 outline 与元数据（不动页面内容）。"""
    import pymupdf

    page_map = locate_pages(pdf_path, headings)
    doc = pymupdf.open(pdf_path)

    toc = []
    for h in headings:
        if h["level"] in (1, 2) and h["plain"] in page_map:
            toc.append([h["level"], h["plain"], page_map[h["plain"]]])
    if toc:
        try:
            doc.set_toc(toc)
        except Exception:
            pass

    doc.set_metadata({
        "title": plain(meta.get("title") or ""),
        "author": plain(meta.get("author") or ""),
        "subject": plain(meta.get("subject") or meta.get("subtitle") or ""),
        "keywords": plain(meta.get("keywords") or ""),
        "creator": "exam-cram-pack build_pdf.py",
        "producer": "exam-cram-pack",
    })
    tmp = pdf_path + ".tmp"
    doc.save(tmp, garbage=3, deflate=True)
    doc.close()
    os.replace(tmp, pdf_path)
    return len(toc)


# ============================================================== main

def main():
    ap = argparse.ArgumentParser(description="复习包 Markdown → 讲义风格 HTML/PDF")
    ap.add_argument("source")
    ap.add_argument("--html-only", action="store_true")
    ap.add_argument("--pdf", action="store_true")
    ap.add_argument("--engine", default="auto", choices=["auto", "weasyprint", "chrome", "edge"])
    ap.add_argument("--css", default=None)
    ap.add_argument("--no-toc", action="store_true")
    ap.add_argument("--no-cover", action="store_true")
    args = ap.parse_args()

    if not os.path.exists(args.source):
        print(f"[x] 找不到文件：{args.source}", file=sys.stderr)
        return 2

    css_path = args.css or DEFAULT_CSS
    if not os.path.exists(css_path):
        print(f"[x] 找不到样式表：{css_path}", file=sys.stderr)
        return 2
    css = open(css_path, encoding="utf-8").read()

    meta, body = split_front_matter(open(args.source, encoding="utf-8").read())
    if not meta.get("title"):
        m = re.search(r"^#\s+(.+)$", body, re.M)
        meta["title"] = (m.group(1).strip() if m
                         else os.path.splitext(os.path.basename(args.source))[0])

    base = os.path.splitext(args.source)[0]
    html_path, pdf_path = base + ".html", base + ".pdf"
    base_dir = os.path.dirname(os.path.abspath(args.source))
    want_toc, want_cover = not args.no_toc, not args.no_cover

    # ---------- 选引擎
    # WeasyPrint 优先（本 skill 的基准版式由它渲染，字体度量最贴合）；
    # 不可用时回退到本机 Chrome / Edge。
    engine = args.engine
    wp_interp = None
    if engine in ("auto", "weasyprint"):
        wp_interp = weasyprint_available()

    if engine == "auto":
        engine = ("weasyprint" if wp_interp
                  else "chrome" if find_browser("chrome")
                  else "edge" if find_browser("edge")
                  else "none")
    if engine == "weasyprint" and not wp_interp:
        print("[!] WeasyPrint 不可用（找不到带 GTK 的 Python 环境），回退到浏览器引擎。",
              file=sys.stderr)
        print("    修复：conda create -n weasy -c conda-forge python=3.12 gtk3 pango cairo", file=sys.stderr)
        print("          conda run -n weasy pip install weasyprint", file=sys.stderr)
        engine = "chrome" if find_browser("chrome") else ("edge" if find_browser("edge") else "none")
    if engine == "weasyprint":
        print(f"[i] 引擎：WeasyPrint（{wp_interp}）")
    elif engine in ("chrome", "edge"):
        print(f"[i] 引擎：{engine}（WeasyPrint 不可用）", file=sys.stderr)

    browser = find_browser(engine) if engine in ("chrome", "edge") else None

    def emit(pnums=None):
        h, hd = build_html(meta, body, css, want_toc=want_toc,
                           want_cover=want_cover, page_numbers=pnums)
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(h)
        return h, hd

    # ---------- 第一遍
    html_str, headings = emit(None)
    print(f"[ok] HTML → {html_path}")
    if args.html_only:
        return 0

    tmp_pdf = pdf_path + ".pass1.pdf"
    if engine == "weasyprint":
        if not render_weasyprint(html_path, tmp_pdf, wp_interp):
            return 1
    elif browser:
        if not render_browser(html_path, tmp_pdf, browser):
            print("[x] 浏览器渲染失败。", file=sys.stderr)
            return 1
    else:
        print("[!] 未找到渲染引擎，只输出 HTML。", file=sys.stderr)
        print("    安装任一：pip install weasyprint（需 GTK）或 Chrome / Edge。", file=sys.stderr)
        return 0

    # ---------- 第二遍：把页码写进目录
    if want_toc:
        nums = locate_pages(tmp_pdf, headings)
        html_str, headings = emit(nums)
        if engine == "weasyprint":
            if not render_weasyprint(html_path, tmp_pdf, wp_interp):
                return 1
        elif not render_browser(html_path, tmp_pdf, browser):
            print("[x] 第二遍渲染失败。", file=sys.stderr)
            return 1
        print(f"[ok] 目录页码已写入（{len(nums)} 条）")

    os.replace(tmp_pdf, pdf_path)

    engine_label = "WeasyPrint" if engine == "weasyprint" else os.path.basename(browser)
    print(f"[ok] PDF → {pdf_path}  ({engine_label})")

    try:
        n = write_bookmarks(pdf_path, headings, meta)
        print(f"[ok] 书签 {n} 条，元数据已写入")
    except Exception as e:
        print(f"[!] 书签写入失败（PDF 仍可阅读）：{e}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
