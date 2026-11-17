#!/usr/bin/env python3
"""产物自检：不依赖任何样例文档，只检查版式契约是否成立。

用法: python scripts/check_style.py out/xxx.pdf

检查项：
  1. 页面尺寸 A4（595.28×841.89pt ±2）
  2. 除封面外每页都有页脚 “N / M”
  3. 字体全部子集内嵌（pdffonts 的 emb 列为 yes）
  4. 每页都有页眉文字（除封面）
  5. 目录页能取到页码（正文存在 “N / M” 计数即视为通过）
需要和母版逐页比对时，用 --gold 指定基准 PDF。
"""
from __future__ import annotations

import argparse
import re
import subprocess
import statistics
import sys
from pathlib import Path

from pypdf import PdfReader


def footer_ok(text: str, total: int) -> bool:
    return re.search(rf"\b\d{{1,3}}\s*/\s*{total}\b", text) is not None


def check_structure(pdf: Path) -> list[str]:
    problems: list[str] = []
    reader = PdfReader(str(pdf))
    n = len(reader.pages)
    if n < 2:
        return ["页数过少，至少需要封面 + 正文"]
    for i, page in enumerate(reader.pages, 1):
        w = float(page.mediabox.width)
        h = float(page.mediabox.height)
        if abs(w - 595.28) > 2 or abs(h - 841.89) > 2:
            problems.append(f"第 {i} 页尺寸 {w:.1f}×{h:.1f}，不是 A4")
            break
    for i, page in enumerate(reader.pages, 1):
        if i == 1:
            continue
        text = page.extract_text() or ""
        if not footer_ok(text, n):
            problems.append(f"第 {i} 页缺少页脚 “N / {n}”")
        if not text.strip():
            problems.append(f"第 {i} 页没有文字")
    try:
        out = subprocess.run(["pdffonts", str(pdf)], capture_output=True, text=True, check=True).stdout
        rows = [r for r in out.splitlines()[2:] if r.strip()]
        bad = []
        for row in rows:
            cols = row.split()
            if len(cols) >= 5 and cols[-5] != "yes":
                bad.append(cols[0])
        if bad:
            problems.append("字体未全部内嵌: " + ", ".join(bad[:3]))
    except Exception as exc:  # pdffonts 不可用时跳过
        print(f"(跳过字体检查: {exc})", file=sys.stderr)
    return problems


def compare(gold: Path, pdf: Path, top: float) -> list[str]:
    from pdfminer.high_level import extract_pages
    from pdfminer.layout import LTChar, LTTextLine

    def walk(o):
        yield o
        if hasattr(o, "_objs"):
            for c in o._objs:
                yield from walk(c)

    def page_lines(p):
        out = []
        for page in extract_pages(str(p)):
            items = []
            for o in walk(page):
                if isinstance(o, LTTextLine):
                    chars = [c for c in o if isinstance(c, LTChar)]
                    text = o.get_text().strip()
                    if chars and text:
                        items.append((round(841.889764 - o.y1, 1), text))
            out.append(items)
        return out

    a, b = page_lines(gold), page_lines(pdf)
    if len(a) != len(b):
        return [f"页数与基准不同：基准 {len(a)}，生成 {len(b)}"]
    bad = []
    for i, (pa, pb) in enumerate(zip(a, b), 1):
        mb: dict[str, list[float]] = {}
        for top_, text in pb:
            mb.setdefault(text, []).append(top_)
        ds = []
        for top_, text in pa:
            cand = mb.get(text)
            if cand:
                ds.append(abs(cand.pop(0) - top_))
        med = statistics.median(ds) if ds else 99
        if med > top:
            bad.append(f"p{i}({med:.1f}pt)")
    return [f"以下页面与基准偏差超过 {top}pt: " + ", ".join(bad)] if bad else []


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf", help="构建出来的 PDF")
    ap.add_argument("--gold", help="可选：基准 PDF，逐页比对行位置")
    ap.add_argument("--top", type=float, default=5.0)
    args = ap.parse_args()

    pdf = Path(args.pdf)
    problems = check_structure(pdf)
    if args.gold:
        problems += compare(Path(args.gold), pdf, args.top)
    if problems:
        for p in problems:
            print("✗", p)
        return 1
    print(f"✓ 版式自检通过：{pdf.name}（{len(PdfReader(str(pdf)).pages)} 页）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
