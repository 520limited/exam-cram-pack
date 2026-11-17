#!/usr/bin/env python3
"""从系统 TTC 中抽出 Noto Sans/Serif CJK SC 单字面，供 WeasyPrint 嵌入。

本机（Android/proot）的 NotoSansCJK-Regular.ttc 在 fontconfig 里带有非法 face index，
直接写 font-family:"Noto Sans CJK SC" 会触发
    TTLibFileIsCollectionError: specify a font number between 0 and 4 (inclusive)
所以这里把 index=2（SC）单独导出为 .otf，再用 @font-face 引用。

用法: python scripts/prepare_fonts.py [--force]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FONT_DIR = ROOT / "fonts"

JOBS = [
    ("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc", 2, "NotoSansCJKsc-Regular.otf"),
    ("/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc", 2, "NotoSansCJKsc-Bold.otf"),
    ("/usr/share/fonts/opentype/noto/NotoSerifCJK-Regular.ttc", 2, "NotoSerifCJKsc-Regular.otf"),
    ("/usr/share/fonts/opentype/noto/NotoSerifCJK-Bold.ttc", 2, "NotoSerifCJKsc-Bold.otf"),
]


def extract(force: bool = False) -> int:
    FONT_DIR.mkdir(parents=True, exist_ok=True)
    try:
        from fontTools.ttLib import TTCollection
    except Exception:
        print("缺少 fontTools：pip install fonttools", file=sys.stderr)
        return 1

    missing = [j for j in JOBS if force or not (FONT_DIR / j[2]).exists()]
    for src, idx, out in missing:
        if not Path(src).exists():
            print(f"! 找不到 {src}", file=sys.stderr)
            continue
        ttc = TTCollection(src)
        ttc.fonts[idx].save(str(FONT_DIR / out))
        print(f"✓ {out}")
    print(f"字体目录: {FONT_DIR}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    return extract(args.force)


if __name__ == "__main__":
    raise SystemExit(main())
