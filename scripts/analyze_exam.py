#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从抽取稿中提取命题结构，生成"考情分析"素材（第一部分的数据底稿）。

用法：
  python analyze_exam.py --work .work
输出：exam-profile.json
"""
import argparse
import json
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")

VERB = re.compile(r"(谈谈|试述|试论|分析|论述|如何看待|如何理解|为什么|怎样|如何)")
SCORE = re.compile(r"[（(]\s*(\d+)\s*分\s*[）)]")
YEAR = re.compile(r"(20\d{2})\s*年")


def load(work):
    mf = os.path.join(work, "manifest.json")
    items = json.load(open(mf, encoding="utf-8")) if os.path.exists(mf) else []
    texts = {}
    for it in items:
        p = it.get("out")
        if p and os.path.exists(p):
            texts[it["file"]] = open(p, encoding="utf-8").read()
    return items, texts


def classify_role(name, text):
    if re.search(r"真题|试卷|考卷|真题集", name):
        return "exam"
    if re.search(r"重点|考点|提纲|大纲|复习", name):
        return "key"
    if re.search(r"教材|课本|教程", name):
        return "book"
    return "other"


def parse_exam(text):
    """按年份切分真题，提取每题的题干与分值。"""
    blocks = []
    marks = [(m.start(), m.group(1)) for m in YEAR.finditer(text)]
    for i, (pos, year) in enumerate(marks):
        end = marks[i + 1][0] if i + 1 < len(marks) else len(text)
        seg = text[pos:end]
        qs = []
        # 以「一、」「1.」等切题
        parts = re.split(r"(?=(?:^|\s)[一二三四五六1-6][、.])", seg)
        for p in parts:
            p = p.strip()
            if len(p) < 12:
                continue
            sc = SCORE.search(p)
            verb = VERB.search(p)
            qs.append({
                "stem": p[:120].replace("\n", " "),
                "score": int(sc.group(1)) if sc else None,
                "verb": verb.group(1) if verb else None,
            })
        blocks.append({"year": year, "questions": qs})
    # 去重（同一套卷子重复出现）
    seen, uniq = set(), []
    for b in blocks:
        key = (b["year"], len(b["questions"]))
        if key in seen:
            continue
        seen.add(key)
        uniq.append(b)
    return uniq


def parse_key_chapters(text):
    chs = []
    for m in re.finditer(r"(第[一二三四五六七八九十]+章|导论)\s*([^\n。…]{2,30})", text):
        name = (m.group(1) + " " + m.group(2)).strip()
        if name not in chs:
            chs.append(name)
    return chs[:20]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", default=".work")
    args = ap.parse_args()

    items, texts = load(args.work)
    profile = {"materials": [], "exam": [], "chapters": [], "has_exam": False}

    for name, txt in texts.items():
        role = classify_role(name, txt)
        profile["materials"].append({
            "file": name, "role": role, "chars": len(txt),
        })
        if role == "exam":
            profile["has_exam"] = True
            profile["exam"].extend(parse_exam(txt))
        if role == "key":
            profile["chapters"] = parse_key_chapters(txt)

    # 无真题时的降级提示
    if not profile["has_exam"]:
        profile["fallback"] = "无真题文件：请用教材/重点中的思考题作为真题代理，并标注'思考题反推'"

    out = os.path.join(args.work, "exam-profile.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(profile, f, ensure_ascii=False, indent=2)

    print(f"[ok] {out}")
    print(f"  材料 {len(profile['materials'])} 份，真题年份 "
          f"{sorted(b['year'] for b in profile['exam'])}")
    print(f"  章节识别 {len(profile['chapters'])} 个")


if __name__ == "__main__":
    main()
