#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从真题抽取稿生成「考情分析」数据表（第一部分的可复用底稿）。

用法：
  python build_exam_profile.py --work .work --out exam-profile.md

产出内容：
  1. 题型结构表（年份 × 题号 × 分值）
  2. 题干动词统计
  3. 分值分布
  4. 关键主题词频（用于推断命题主线）
"""
import argparse
import json
import os
import re
import sys
from collections import Counter

sys.stdout.reconfigure(encoding="utf-8")

YEAR = re.compile(r"(20\d{2})\s*年[^\n]{0,24}?真题")
SCORE = re.compile(r"[（(]\s*(\d+)\s*分\s*[）)]")
VERB = re.compile(r"(谈谈|试述|试论|分析|论述|如何看待|如何理解|为什么|怎样|如何)")
QSPLIT = re.compile(
    r"(?<=[。？！）)])(?=[一二三四五六1-6][、.])"   # 句末/括号后接题号
    r"|(?<=[。？！）)]) ?(?=[一二三四五六1-6][、.])"
    r"|(?<=[。？！）)]) ?(?=\d[、.]?\s*(?:联系|阅读|谈谈|试述|运用|根据|如何|在))"
    r"|(?=[一二三四五六][、．.])"
    r"|(?=真题)(?!$)"
)

# 常见「分析工具」词，用于识别命题主线
TOOLS = [
    "矛盾", "系统", "实践", "调查研究", "问题意识", "真理", "价值",
    "世界历史", "全球化", "共同体", "人的本质", "阶层", "阶级",
    "过程", "规律", "主体", "认识", "评价", "科学方法", "求真",
]


def parse_questions(text):
    """按年份切块，返回 [(year, [question, ...])]"""
    marks = [(m.start(), m.group(1)) for m in YEAR.finditer(text)]
    blocks = []
    seen = set()
    for i, (pos, year) in enumerate(marks):
        end = marks[i + 1][0] if i + 1 < len(marks) else len(text)
        seg = text[pos:end]
        # 去掉开头的「YYYY年……真题」标题
        seg = YEAR.sub("", seg, count=1).lstrip(" \n\u3000")
        qs = []
        for p in QSPLIT.split(seg):
            p = p.strip()
            if len(p) < 15:
                continue
            # 去掉题号前缀
            p = re.sub(r"^[一二三四五六1-6][、.]\s*", "", p)
            sc = SCORE.search(p)
            vm = VERB.search(p)
            qs.append({
                "stem": re.sub(r"\s+", " ", p)[:150],
                "score": int(sc.group(1)) if sc else None,
                "verb": vm.group(1) if vm else None,
            })
        key = (year, len(qs))
        if qs and key not in seen:
            seen.add(key)
            blocks.append((year, qs))
    return blocks

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", default=".work")
    ap.add_argument("--out", default="exam-profile.md")
    args = ap.parse_args()

    mf = os.path.join(args.work, "manifest.json")
    items = json.load(open(mf, encoding="utf-8")) if os.path.exists(mf) else []

    exam_text = ""
    for it in items:
        if re.search(r"真题|试卷|考卷", it["file"]) and it.get("out"):
            exam_text += open(it["out"], encoding="utf-8").read()

    if not exam_text.strip():
        print("⚠️  未找到真题文件。请用思考题作为代理，并在产出中标注「思考题反推」。",
              file=sys.stderr)
        return 1

    blocks = parse_questions(exam_text)
    years = [y for y, _ in blocks]

    lines = ["# 考情分析（数据底稿）", ""]
    lines.append(f"**真题年份**：{'、'.join(sorted(years))}（共 {len(years)} 套）")
    lines.append("")

    # 1) 分值分布
    all_scores = [q["score"] for _, qs in blocks for q in qs if q["score"]]
    if all_scores:
        lines.append("## 分值分布")
        lines.append("")
        lines.append(f"单题分值出现：{dict(Counter(all_scores))}")
        lines.append(f"整套合计（取最大值那套）：{sum(sorted(all_scores, reverse=True)[:len(max(blocks, key=lambda b: len(b[1]))[1])])}")
        lines.append("")

    # 2) 题型判断
    verbs = Counter(q["verb"] for _, qs in blocks for q in qs if q["verb"])
    lines.append("## 题干动词（判断题型）")
    lines.append("")
    for v, c in verbs.most_common():
        lines.append(f"- {v}：{c} 次")
    lines.append("")

    # 3) 年份 × 题号 表
    lines.append("## 年份 × 题号")
    lines.append("")
    maxq = max(len(qs) for _, qs in blocks)
    header = "| 年份 | " + " | ".join(
        f"第{i+1}题" for i in range(maxq)) + " |"
    lines.append(header)
    lines.append("|" + "---|" * (maxq + 1))
    for year, qs in sorted(blocks, reverse=True):
        cells = []
        for i in range(maxq):
            if i < len(qs):
                q = qs[i]
                sc = f"（{q['score']}分）" if q["score"] else ""
                cells.append(re.sub(r"[|\n]", " ", q["stem"])[:80] + sc)
            else:
                cells.append("—")
        lines.append(f"| {year} | " + " | ".join(cells) + " |")
    lines.append("")

    # 4) 主题词频 → 命题主线候选
    lines.append("## 主题词频（命题主线候选）")
    lines.append("")
    joined = " ".join(q["stem"] for _, qs in blocks for q in qs)
    freq = [(t, joined.count(t)) for t in TOOLS]
    freq.sort(key=lambda x: -x[1])
    lines.append("| 主题 | 题干命中次数 |")
    lines.append("|---|---|")
    for t, c in freq:
        if c:
            lines.append(f"| {t} | {c} |")
    lines.append("")
    lines.append("> 提示：把上述高频主题按语义归并成 4—7 条主线，"
                 "每条需补充「已考题目（年份-题号）」与「还可能怎么考」。")

    out = args.out
    with open(out, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"[ok] {out}")
    print("\n".join(lines[:14]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
