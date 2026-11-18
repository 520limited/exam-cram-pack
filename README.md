# exam-cram-pack · 期末冲刺复习包生成器

一个把**课程材料**变成**考场上能直接写出来的复习包**的 Agent Skill。

不是"知识点总结"，是"答案生产线"。

---

## 它解决什么问题

期末前你手上有：教材 PDF（可能是扫描件）、老师划的重点、几套历年真题。
你需要的不是又一份笔记，而是：

- 这门课**到底怎么考**（题型、分值、命题主线、阅卷看什么）
- 每个考点**会怎么问、该怎么写**
- 每类题**分几段、每段写什么**
- 考场上**用什么素材**、**哪里最容易丢分**

这个 skill 就产出这些。

---

## 输出长什么样

一份八部分的 Markdown（可一键导出 PDF）：

| 部分 | 内容 | 作用 |
|---|---|---|
| 使用说明 | 按剩余时间给三条路径 | 决定你今天看什么 |
| 一 · 考情分析 | 题型结构表 / 命题主线 / 阅卷逻辑 | **决定全篇篇幅分配** |
| 二 · 逻辑链 | 章节串成一条链 + 记忆口诀 | 大题有框架 |
| 三 · 逐章考点 | 每个考点的考法提示 + 可背表述 | 真正背的部分 |
| 四 · 答题模板 | 5—8 个题型模板，分段到"第一段写什么" | 提笔就会写 |
| 五 · 速记表 | 概念 → 一句话定义 | 考前 2 小时 |
| 六 · 必背金句 | 15—20 条真实引文 | 考场点睛 |
| 七 · 模拟卷 | 新题 + 参考答案要点 | 自测 |
| 八 · 考场策略 | 时间表 / 素材库 / 失分点 / 冲刺日程 | 上场前 |
| 附录 | 历年真题参考答案 | 对着原题复习 |

---

## 核心方法：真题反推

普通做法是按章节平均用力。这个 skill 反过来：

```
先读真题 → 按知识点归并成 4—7 条命题主线
        → 算出每条主线考了几次、占多少分
        → 按频率分配篇幅与模板数量
        → 把已考题迁移成"还可能怎么考"（押题落点）
```

所以第一部分「考情分析」是整份产出的地基，不是装饰。

---

## 安装

### DSH / Claude Code / Codex

把整个目录复制到你的 skills 目录：

```bash
git clone https://github.com/520limited/exam-cram-pack.git
cp -r exam-cram-pack ~/.claude/skills/     # Claude Code
cp -r exam-cram-pack ~/.codex/skills/      # Codex
cp -r exam-cram-pack ~/.agents/skills/     # 通用 agents
```

或直接从仓库安装：

```bash
npx skills add https://github.com/520limited/exam-cram-pack --skill exam-cram-pack
```

### 依赖

**无第三方依赖。** 脚本只用 Python 标准库（3.8+）。

导出 PDF 可选装：

```bash
pip install weasyprint
```

没有 weasyprint 时 `build_pdf.py` 会产出 HTML，效果同样可读。

---

## 使用

在支持 Skill 的 agent 里说：

> 帮我整理这三份材料的期末复习资料：`教材.pdf`、`重点.pdf`、`真题.pdf`，按 exam-cram-pack 的格式。

或更短：

> 用 exam-cram-pack 做一份期末复习包

Skill 会按五个阶段自动执行：材料盘点 → 真题反推 → 搭骨架 → 写考点/模板/速记/金句 → 模拟卷与考场策略。

---

## 脚本

```bash
# 1) 探测材料（自动识别扫描件）
python scripts/extract_materials.py --probe 教材.pdf 重点.pdf 真题.pdf

# 2) 抽取文本到 .work/
python scripts/extract_materials.py --extract 重点.pdf 真题.pdf --out .work

# 3) 分析真题结构（题型/分值/主题词频）
python scripts/analyze_exam.py --work .work
python scripts/build_exam_profile.py --work .work --out .work/exam-profile.md

# 4) 成品自检
python scripts/check_pack.py 复习资料.md

# 5) 导出 PDF/HTML
python scripts/build_pdf.py 复习资料.md
```

---

## 关于扫描件

教材常是纯图片扫描件（无文字层）。这个 skill **不要求你预先 OCR**：

1. `--probe` 会检测出无文字层并提示
2. Agent 用**视觉能力**读扫描页
3. 页数多时只读目录 + 每章首末页，教材仅作"核对表述"用

**重点与真题通常有文字层，它们才是骨架。** 教材缺失内容不会致命。

---

## 三条证据铁律

产出的每句话都能溯源：

| 标记 | 含义 |
|---|---|
| `真题 2024` | 该考点确实在某年真题出现 |
| `补` | AI 补充的时政/案例，材料没有原话 |
| `推断` | 依据材料结构推断的高频 |

正文里 `**加粗**` 语义固定：**可以直接背下来写进卷面的表述**。

---

## 学科适配

不只能做文科论述题。见 `references/subject-adaptation.md`：

- **A 论述型**（思政/法学/文史哲）→ 论点递进式模板
- **B 计算型**（数学/物理/计算机）→ 解题流程模板 + 完整推导
- **C 语言型**（英语/二外）→ 写作框架 + 万能句型
- **D 实务型**（工程/医学/财会）→ 决策树/流程模板

---

## 目录结构

```
exam-cram-pack/
├── SKILL.md                        # 主文件：五阶段工作流 + 四条铁律
├── references/
│   ├── output-contract.md          # 八部分字段与写法细则（核心）
│   ├── subject-adaptation.md       # A/B/C/D 四类学科适配
│   ├── evidence-policy.md          # 证据分层与防编造
│   └── quality-gates.md            # 交付前自检清单
├── assets/
│   └── pack-template.md            # 可直接套用的空模板
└── scripts/
    ├── extract_materials.py        # 材料探测与抽取
    ├── analyze_exam.py             # 真题结构分析
    ├── build_exam_profile.py       # 考情数据底稿
    ├── check_pack.py               # 成品自检
    └── build_pdf.py                # Markdown → HTML/PDF
```

---

## 设计取舍

- **为什么强调真题优先**：没有真题反推，"重点"就是主观的；有了真题，篇幅分配才有依据。
- **为什么要求模板分段到"第一段写什么"**：讲"要辩证分析"没有用，学生需要的是能落笔的骨架。
- **为什么加粗只给可背表述**：让学生扫一眼就知道背哪句，而不是满页重点等于没有重点。
- **为什么不内置 OCR**：OCR 质量不稳且慢；视觉读取扫描页更准，且重点/真题本来就有文字层。

---

## License

MIT
