# exam-cram-pack

**Turn lecture notes and past papers into a print-ready revision pack — with one command.**

把课程讲义（PDF/PPT/扫描件）和历年真题，整理成一份可以直接打印、直接背的期末复习资料：
封面、目录、考情分析、知识框架、逐章考点、论述题模板、概念速记表、必背金句、模拟卷、
考场策略，附录附上真题原文与参考答案。输出 Markdown / HTML / A4 PDF 三件套。

---

## 它解决什么问题

期末复习真正的难点不是“资料太少”，而是三件事：

1. **不知道考什么** —— 讲义几十页，考纲没写重点，真题散落在各处；
2. **背了写不出来** —— 笔记是“知识”，考场要的是“答案”，中间差一个答题框架；
3. **排版靠手搓** —— 用 Word 拼封面、目录、页码、表格，一晚上就没了。

这个仓库把这三件事串成一条流水线：**抽取 → 提纲 → 写作 → 排版 → 自检**。
你负责提供材料和判断对错，剩下的结构化、排版、页码、目录交给它。

## 产出长什么样

| 部分 | 内容 | 作用 |
|---|---|---|
| 封面 | 课程名、资料定位、五条卖点、依据材料 | 一眼知道这份东西是什么 |
| 目录 | 一级标题 + 页码，自动生成 | 打印后能翻 |
| 使用说明 | 不同剩余时间的用法、标记说明 | 决定先看哪一块 |
| 考情分析 | 题型分值表、命题主线、阅卷逻辑 | 先搞清楚“怎么考” |
| 全书框架 | 一张表把各章串成一条逻辑链 | 大题不再各写各的 |
| 逐章考点 | 每章 6–8 节：导读 + 对比表 + 可背表述 + 自测 | 主体背诵内容 |
| 论述模板 | 题干特征、五到七段框架、联系实际、收束句 | 考场直接套 |
| 速记表 | 概念 / 一句话定义，40 条以上 | 考前 2 小时翻 |
| 必背金句 | 20 条原文级表述 | 提高答案“像教材”的程度 |
| 模拟卷 | 按真题分值结构出题 + 答案要点 | 限时自测 |
| 考场策略 | 时间分配、素材库、失分点、最后三天 | 把资料变成分数 |
| 附录 | 历年真题原文 + 参考答案（每题 700–900 字） | 对照真题练手 |

## 特点

- **证据优先**：真题题干、引文、分值逐字保留；答案可以组织，题干不许润色。
- **面向考场**：每个考点都落到“怎么问、怎么答、哪几句必须写”。
- **版式即成品**：A4、页眉页脚、目录页码、表格跨页处理都是现成的，打印即用。
- **纯本地**：Markdown + WeasyPrint，不需要任何云服务；课程材料不出本机。

## 快速开始

### 方式一：作为 Agent Skill

```bash
git clone https://github.com/520limited/exam-cram-pack.git
cp -r exam-cram-pack ~/.dsh/skills/exam-review-generator
python ~/.dsh/skills/exam-review-generator/scripts/prepare_fonts.py
```

然后在对话里说「用 exam review generator 整理这门课的复习资料」，把讲义和真题丢给它。

### 方式二：直接当命令行工具

```bash
pip install weasyprint fonttools pdfminer.six pypdf
python scripts/prepare_fonts.py          # 首次运行，抽中文字体

python scripts/build.py book/ --out out  # book/00_front.md + 若干章节 md
python scripts/build.py 复习资料.md --out out
```

产物：`out/<标题>_期末复习资料.{md,html,pdf}`。

## 输入格式

一个 Markdown 文件（或 `book/` 目录，按文件名排序拼接），开头是 YAML front matter：

```markdown
---
kicker: 本科专业选修课 · 期末
title: 课程名称
subtitle: 期末复习资料
running: 课程名称 · 期末复习资料
toc_title: 目录
bullets:
  - 考点精讲（全章覆盖）
  - 近五年真题命题规律
  - 高频论述题答题模板
  - 核心概念速记 + 必背金句 + 模拟卷
  - 附录：历年真题参考答案
source_note: 依据材料：教材《……》、课堂讲义（N 页）、20XX—20XX 年期末真题
date_note: 整理日期：2026 年 1 月 1 日
---
```

正文语法：

| 写法 | 效果 |
|---|---|
| `# 第一部分　考情分析` | 一级标题（自动另起一页，1.5pt 下划线） |
| `## 一、题型结构` | 二级标题（蓝色，左侧竖线） |
| `### 1.1 小节` | 三级标题 |
| `**关键表述**` | 加粗 = 考场上可直接写出去的句子 |
| `\| 表头 \| 表头 \|` | 表格（自动表头底色、跨页不重复表头） |
| `> 提示文字` | 灰色提示框 |
| `::: selftest` … `:::` | 自测题块（橙色竖线） |
| `::: quotes` … `:::` | 金句块（米色底、加粗） |
| `{{真题 2024}}` `{{高频}}` | 红色标签 |
| `{{补}}` | 绿色标签（时政/补充素材） |

完整骨架见 `templates/book-skeleton.md`，字段示例见 `templates/front-matter.yml`。

## 默认版式

| 元素 | 规格 |
|---|---|
| 页面 | A4，页边距 18 / 16 / 16 mm |
| 页眉页脚 | 右上 `课程名 · 期末复习资料` 8pt `#CBD5E1`；居中 `N / M` 8.5pt `#94A3B8` |
| 封面 | 主标题 27pt 深蓝 `#0E3A63`，副标题 15pt 橙 `#B45309`，五条要点 11pt |
| 一级标题 | 17pt 加粗 `#0E3A63` + 1.5pt 下划线，每章新页 |
| 二级标题 | 12.5pt 加粗 `#1D4ED8` + 3pt 竖线 |
| 正文 | 衬线 10.5pt `#1F2937`，行高 18pt，段后 7.5pt |
| 表格 | 0.5pt `#CBD5E1` 边框，表头 `#EEF2F7`，正文 9pt / 行高 14pt |
| 提示框 / 自测框 / 金句框 | `#F1F5F9` + 深灰竖线 / 橙色竖线 / 米色 `#FBF7EF` |

所有数值都写在 `templates/style.css` 的 `:root` 变量和对应规则里，
换配色改变量即可，不需要动 Python。

## 质量检查

```bash
# 结构自检：A4 尺寸、页脚编号、字体内嵌、页眉
python scripts/check_style.py out/xxx.pdf

# 手上有基准稿时，逐页比对行位置（中位偏差 ≤ 5pt 视为通过）
python scripts/check_style.py out/xxx.pdf --gold reference.pdf
```

写作层面的红线在 `SKILL.md`：真题逐字不动、答案落在教材术语体系、覆盖不到的考点要显式标注。

## 目录结构

```
scripts/
  build.py            Markdown → HTML → PDF
  prepare_fonts.py    从系统 TTC 抽出 Noto CJK SC 单字面
  check_style.py      产物结构自检 / 与基准逐页比对
templates/
  style.css           默认版式（改这里换皮肤）
  front-matter.yml    封面与页眉字段示例
  book-skeleton.md    八部分写作骨架
```

## 常见问题

**讲义是扫描件怎么办？**
`pdftotext` 出乱码时改用 `pdftoppm -r 200` + OCR，再把文本按章切分；结构照旧。

**没有真题？**
保留“考情分析/逐章考点/速记表/金句/模拟卷”五块，把附录换成自拟模拟题与答案，
同样能导出完整册子。

**构建报 `specify a font number between 0 and 4`？**
本机 `NotoSansCJK-*.ttc` 的 face index 异常。跑一次 `python scripts/prepare_fonts.py`，
脚本会把 SC 单字面导出成独立 `.otf`，`build.py` 会在缺字体时自动调用。

**能改成双栏 / 换色 / 换字体吗？**
改 `templates/style.css`：栏目宽度、颜色都在 `:root` 变量和 `@page` 规则里；
字体换成任意已安装的字体名即可。

## 许可

MIT
