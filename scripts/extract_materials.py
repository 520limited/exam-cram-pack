#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""材料探测与抽取。

用法：
  python extract_materials.py --probe <file...>            # 只探测，不落盘
  python extract_materials.py --extract <file...> --out DIR # 抽取到 DIR

支持：PDF（含扫描件检测）、DOCX、PPTX、TXT/MD。
不依赖第三方库（PDF 用手写解析 + zlib）。
"""
import argparse
import io
import json
import os
import re
import sys
import zipfile
import zlib

sys.stdout.reconfigure(encoding="utf-8")


# ---------------------------------------------------------------- PDF helpers

def _pdf_objects(data):
    objs = {}
    for m in re.finditer(rb"(?<!\d)(\d+)\s+0\s+obj(.*?)endobj", data, re.S):
        objs[int(m.group(1))] = m.group(2)
    return objs


def _decompress(body):
    m = re.search(rb"stream\r?\n(.*?)endstream", body, re.S)
    if not m:
        return None
    raw = m.group(1)
    head = body[: m.start()]
    if b"FlateDecode" in head:
        try:
            return zlib.decompress(raw)
        except Exception:
            try:
                return zlib.decompressobj().decompress(raw)
            except Exception:
                return None
    return raw


def _parse_cmap(data):
    mp = {}
    for m in re.finditer(rb"beginbfchar(.*?)endbfchar", data, re.S):
        for p in re.finditer(rb"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>", m.group(1)):
            try:
                mp[int(p.group(1), 16)] = bytes.fromhex(
                    p.group(2).decode()).decode("utf-16-be", "ignore")
            except Exception:
                pass
    for m in re.finditer(rb"beginbfrange(.*?)endbfrange", data, re.S):
        for r in re.finditer(
                rb"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>", m.group(1)):
            lo, hi = int(r.group(1), 16), int(r.group(2), 16)
            try:
                b = bytes.fromhex(r.group(3).decode())
                base = int.from_bytes(b[:2], "big")
            except Exception:
                continue
            for i in range(min(hi - lo + 1, 65536)):
                mp[lo + i] = chr(base + i)
    return mp


def probe_pdf(path):
    data = open(path, "rb").read()
    info = {
        "file": os.path.basename(path),
        "kind": "pdf",
        "bytes": len(data),
        "pages": len(re.findall(rb"/Type\s*/Page[^s]", data)),
        "images": data.count(b"/Image"),
        "tounicode": data.count(b"/ToUnicode"),
        "objstm": data.count(b"/ObjStm"),
    }
    info["text_layer"] = "yes" if info["tounicode"] > 0 else "no"
    return info


def extract_pdf(path):
    data = open(path, "rb").read()
    objs = _pdf_objects(data)

    # 收集 ToUnicode CMap（含对象流内部的），code -> char 全局合并
    merged = {}
    streams_to_scan = [data]
    for body in objs.values():
        if b"/ObjStm" in body:
            dec = _decompress(body)
            if dec:
                streams_to_scan.append(dec)

    for blob in streams_to_scan:
        for m in re.finditer(rb"/ToUnicode\s+(\d+)\s+0\s+R", blob):
            num = int(m.group(1))
            target = objs.get(num)
            if target is None:
                continue
            dec = _decompress(target)
            if dec:
                merged.update(_parse_cmap(dec))

    out = []
    for body in objs.values():
        if b"/Type" in body and b"/Page" in body and b"/Contents" not in body:
            continue
        dec = _decompress(body)
        if not dec or b"BT" not in dec:
            continue
        buf = []
        for m in re.finditer(
                rb"<([0-9A-Fa-f]+)>\s*Tj|\[(.*?)\]\s*TJ|"
                rb"\(((?:\\.|[^()\\])*)\)\s*Tj|(T\*)", dec, re.S):
            if m.group(1):
                h = m.group(1).decode()
                for i in range(0, len(h) - 3, 4):
                    buf.append(merged.get(int(h[i:i + 4], 16), ""))
            elif m.group(2):
                for sm in re.finditer(rb"<([0-9A-Fa-f]+)>", m.group(2)):
                    h = sm.group(1).decode()
                    for i in range(0, len(h) - 3, 4):
                        buf.append(merged.get(int(h[i:i + 4], 16), ""))
            elif m.group(3) is not None:
                buf.append(m.group(3).decode("utf-8", "ignore"))
            else:
                if buf and buf[-1] != "\n":
                    buf.append("\n")
        txt = "".join(buf).strip()
        if txt:
            out.append(txt)
    return "\n\n".join(out)


# ---------------------------------------------------------------- Office

def extract_docx(path):
    with zipfile.ZipFile(path) as z:
        try:
            xml = z.read("word/document.xml").decode("utf-8", "ignore")
        except KeyError:
            return ""
    xml = re.sub(r"</w:p>", "\n", xml)
    xml = re.sub(r"<w:tab[^>]*/>", "\t", xml)
    xml = re.sub(r"<[^>]+>", "", xml)
    return re.sub(r"\n{3,}", "\n\n", xml)


def extract_pptx(path):
    out = []
    with zipfile.ZipFile(path) as z:
        names = sorted(n for n in z.namelist()
                       if re.match(r"ppt/slides/slide\d+\.xml$", n))
        for n in names:
            xml = z.read(n).decode("utf-8", "ignore")
            texts = re.findall(r"<a:t>(.*?)</a:t>", xml, re.S)
            if texts:
                out.append(" ".join(texts))
    return "\n\n".join(out)


def extract_text(path):
    for enc in ("utf-8", "gbk", "gb18030", "big5"):
        try:
            return open(path, encoding=enc).read()
        except (UnicodeDecodeError, LookupError):
            continue
    return open(path, "rb").read().decode("utf-8", "ignore")


# ---------------------------------------------------------------- main

def probe(path):
    ext = os.path.splitext(path)[1].lower()
    if ext == ".pdf":
        return probe_pdf(path)
    info = {"file": os.path.basename(path), "kind": ext.lstrip("."),
            "bytes": os.path.getsize(path)}
    info["text_layer"] = "yes"
    return info


def extract_one(path):
    ext = os.path.splitext(path)[1].lower()
    if ext == ".pdf":
        return extract_pdf(path)
    if ext == ".docx":
        return extract_docx(path)
    if ext == ".pptx":
        return extract_pptx(path)
    if ext in (".txt", ".md", ".markdown"):
        return extract_text(path)
    return ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--probe", nargs="+", metavar="FILE")
    ap.add_argument("--extract", nargs="+", metavar="FILE")
    ap.add_argument("--out", default=".work")
    args = ap.parse_args()

    if args.probe:
        rows = [probe(p) for p in args.probe if os.path.exists(p)]
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        warn = [r for r in rows if r.get("text_layer") == "no"]
        if warn:
            print("\n⚠️  以下文件无文字层（扫描件），需视觉读取，不要要求用户 OCR：",
                  file=sys.stderr)
            for r in warn:
                print(f"   - {r['file']} ({r.get('images', '?')} 张图)", file=sys.stderr)
        return

    if args.extract:
        os.makedirs(args.out, exist_ok=True)
        manifest = []
        for p in args.extract:
            if not os.path.exists(p):
                print(f"[skip] 不存在: {p}", file=sys.stderr)
                continue
            txt = extract_one(p)
            stem = os.path.splitext(os.path.basename(p))[0]
            dst = os.path.join(args.out, stem + ".txt")
            with open(dst, "w", encoding="utf-8") as f:
                f.write(txt)
            meta = probe(p)
            meta["out"] = dst
            meta["chars"] = len(txt)
            manifest.append(meta)
            print(f"[ok] {meta['file']} → {dst} ({len(txt)} 字)")
        with open(os.path.join(args.out, "manifest.json"), "w",
                  encoding="utf-8") as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2)
        print(f"\n清单已写入 {os.path.join(args.out, 'manifest.json')}")


if __name__ == "__main__":
    main()
