#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""成品自检：八部分是否齐全、标记是否规范。

用法：
  python check_pack.py <复习资料.md>
"""
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")

SECTIONS = [
    ("使用说明", r"^#+\s*使用说明"),
    ("第一部分·考情分析", r"^#+\s*第一部分"),
    ("第二部分·逻辑链", r"^#+\s*第二部分"),
    ("第三部分·逐章考点", r"^#+\s*第三部分"),
    ("第四部分·答题模板", r"^#+\s*第四部分"),
    ("第五部分·速记表", r"^#+\s*第五部分"),
    ("第六部分·金句", r"^#+\s*第六部分"),
    ("第七部分·模拟卷", r"^#+\s*第七部分"),
    ("第八部分·考场策略", r"^#+\s*第八部分"),
    ("附录·真题答案", r"^#+\s*附录"),
]


def main(path):
    text = open(path, encoding="utf-8").read()
    lines = text.splitlines()
    problems = []
    warnings = []

    # 1) 八部分齐全
    print("== 结构检查 ==")
    for name, pat in SECTIONS:
        hit = any(re.search(pat, ln) for ln in lines)
        print(f"  {'✓' if hit else '✗'} {name}")
        if not hit:
            problems.append(f"缺少 {name}")

    # 2) 真题标注
    zt = re.findall(r"真题\s*(\d{4})", text)
    print(f"\n== 真题标注 ==\n  出现 {len(zt)} 处，年份：{sorted(set(zt))}")
    if not zt:
        warnings.append("没有出现任何「真题 YYYY」标注——若无真题材料可忽略")

    # 3) 加粗是否为可背表述（抽查：加粗内容不应过长）
    bolds = re.findall(r"\*\*(.+?)\*\*", text)
    long_bolds = [b for b in bolds if len(b) > 80]
    print(f"\n== 加粗检查 ==\n  共 {len(bolds)} 处加粗，其中 >80 字 {len(long_bolds)} 处")
    if long_bolds:
        warnings.append(f"{len(long_bolds)} 处加粗过长，可能不是'可背表述'")

    # 4) 金句条数
    sec6 = re.search(r"第六部分.*?(?=第七部分)", text, re.S)
    if sec6:
        quotes = re.findall(r"^\s*\d+[.、]", sec6.group(0), re.M)
        print(f"\n== 金句条数 ==\n  {len(quotes)} 条")
        if not (10 <= len(quotes) <= 25):
            warnings.append(f"金句 {len(quotes)} 条，建议 15—20 条")

    # 5) 模板数量
    sec4 = re.search(r"第四部分.*?(?=第五部分)", text, re.S)
    if sec4:
        tpl = re.findall(r"^#+\s*模板", sec4.group(0), re.M)
        print(f"\n== 模板数量 ==\n  {len(tpl)} 个")
        if len(tpl) < 4:
            warnings.append(f"模板仅 {len(tpl)} 个，建议 5—8 个")

    # 6) 素材库条数
    sec8 = re.search(r"第八部分.*?(?=附录)", text, re.S)
    if sec8:
        rows = [ln for ln in sec8.group(0).splitlines()
                if ln.strip().startswith("|") and ln.count("|") >= 3]
        print(f"\n== 素材库表格行 ==\n  {len(rows)} 行（含表头）")
        if len(rows) < 10:
            warnings.append(f"素材库表格仅 {len(rows)} 行，建议 10—15 条素材")

    # 7) 附录年份覆盖
    secA = re.search(r"附录.*", text, re.S)
    if secA:
        years = re.findall(r"(20\d{2})\s*年", secA.group(0))
        print(f"\n== 附录年份 ==\n  {sorted(set(years))}")
        if not years:
            problems.append("附录没有分年份")

    # 8) 未标注的补充内容（启发式：出现"联系实际"但段落无 补）
    print("\n== 汇总 ==")
    if problems:
        print("  ❌ 必须修复：")
        for p in problems:
            print(f"     - {p}")
    if warnings:
        print("  ⚠️  建议改进：")
        for w in warnings:
            print(f"     - {w}")
    if not problems and not warnings:
        print("  ✅ 全部通过")

    return 1 if problems else 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python check_pack.py <复习资料.md>", file=sys.stderr)
        sys.exit(2)
    sys.exit(main(sys.argv[1]))
