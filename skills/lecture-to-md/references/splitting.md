# 长课程切分规范（主代理前置工作）

短课程单线程就够；长课程一次写完会导致上下文溢出、后段质量塌陷、配图张冠李戴、中途失败全盘重来。  
本文件规定主代理在**派发子代理之前**必须做完的四件事：定大纲 → 定切分 → 切素材 → 自检。  
派发与汇总见 [`subagent-workflow.md`](./subagent-workflow.md)。

```
S0 子代理（并行）                        S1 子代理（大纲之后）
  S0-a 文字稿获取  ──┐
  S0-b 视频+抽帧    ──┼──▶ 主代理验收素材 ──▶ 主代理通读文字稿 ──▶ outline.md
  S0-c 课件转PNG    ──┘                        （H1 骨架 + 锚点 + 课件页码）
                                                        │
                                                        ▼
                                              S1 子代理切素材 ──▶ 主代理验收
                                                        │
                    parts/transcript_part_XX.txt        │
                    parts/frames_part_XX/               │
                    slides/（不搬动，只给页码区间）          │
                                                        ▼
                  并行派发撰写子代理 ──▶ 主代理汇总 ──▶ 结构重排（只改标题）──▶ 交付
                  （subagent-workflow.md）      （structure-reorder.md）
```

---

## 0. 角色分工

| 角色      | 职责                              | 禁止事项                                   |
| ------- | ------------------------------- | -------------------------------------- |
| **主代理** | 通读全文、定 H1 大纲、派发任务、验收素材、汇总统稿 | ❌ 不把「定大纲」交给子代理；❌ 不闭眼收子代理的素材结果     |
| **S0 子代理** | 下载视频 / 字幕、ASR 转写、抽帧、课件转 PNG（Phase 1） | ❌ 不碰内容决策；❌ 不写笔记正文            |
| **S1 子代理** | 按 outline.md 切文字稿、帧按时段分目录（第 4 节） | ❌ 不改锚点/区间；❌ 不写笔记正文             |
| **撰写子代理** | 只写分到自己那 1–3 个 H1 及其下级内容 + 本片段配图 | ❌ 不改名/增删/调序 H1；❌ 不写自己片段以外的文件；❌ 不做跨片段整合 |

**核心原则：结构由主代理定死，子代理只负责在给定骨架内填充高质量内容。**  
S0/S1 做机械搬运（省主代理上下文、可并行），撰写子代理做内容填充，最后主代理统一验收与汇总——这样笔记是一门课，而不是 N 篇风格各异的短文拼接。

---

## 1. 何时启用

- 视频 `ffprobe` 时长 **> 30 分钟** → 启用。
- 纯文字稿：中文 ≈ 250 字/分钟、英文 ≈ 150 词/分钟，估算 > 30 分钟 → 启用。
- 边界情况（28–35 分钟、或结构极简单）：倾向启用——多一个子代理的成本远低于长上下文的质量衰减。
- **≤ 30 分钟一律不启用**，直接单线程（拆分成子代理的开销与衔接损耗反而不划算）。

---

## 2. 主代理先出大纲（不可跳过）

**主代理必须自己完整读一遍文字稿**（必要时配合课件目录页、章节标题页），产出 `<outdir>/outline.md`。

### outline.md 格式

````markdown
# 大纲：{课程标题}
- 总时长：约 XX 分钟 / 文字稿约 XXXXX 字
- 一级标题数：N（≤ 10）
- 计划切成 M 个子任务

## 素材说明
- 文字稿：transcript.txt（无时间戳，共 1320 行）
- 视频帧：frames/（共 792 帧，times.txt 已生成）
- 课件：slides/slide-01.png … slide-312.png
  ← **整门课合订 PDF，本课时只用到第 12–180 页**；其余页码属于别的课时，任何子代理都不要用

## 切分方案

### Part 01（子代理 1）
- 稿子锚点：第 1–420 行（或 [00:00:00 – 00:18:40]）
- 视频帧区间：0 – 1120 秒
- **课件页码：pp. 12–38**（文件名 slide-012.png … slide-038.png）
- 预估时长：18 分钟
- 负责的一级标题：
  1. 课程导论与学习路径
  2. 开发环境搭建
- 内容摘要：开场说明课程定位、评分方式，随后演示环境安装与第一个示例

### Part 02（子代理 2）
- 稿子锚点：第 400–880 行（与前一段重叠 20 行）
- 视频帧区间：1120 – 2465 秒
- **课件页码：pp. 39–92**
- 预估时长：22 分钟
- 负责的一级标题：
  1. 变量与类型系统
  2. 运算符与表达式
  3. 控制流
- 内容摘要：……

### Part 03（子代理 3）
- 稿子锚点：第 860–1320 行
- 视频帧区间：2465 – 3780 秒
- **课件页码：pp. 93–180**
- 衔接提示：紧接 Part 02 末尾的「循环嵌套」例子，不要重复铺垫
- ……

## 全局统一约定（所有子代理遵守）
- 术语表：XXX 统一称「词元」，不写「令牌」；YYY 统一称「嵌入」
- 代码语言标注：Python 示例一律 ```python
- 人名/专有名词原文：Geoffrey Hinton、Karpathy
````

### 大纲的三条硬约束

1. **一级标题就是最终笔记的 H1**——子代理会原样输出，所以此刻定的名字必须是最终稿要的样子。
2. **数量约束**：一级标题 ≤ 10 个，每个一级标题下二级标题 ≤ 10 个（见 `assets/notes-prompt.md` 第六节）。
3. **锚点必须可定位**：有时间戳的稿子（srt/vtt/带时标的 txt）用时间区间；无时间戳的用行号区间。**课件必须标页码区间**——课件常常是整门课合订的几百页 PDF，不标页码子代理就会用到别的课时的页。

---

## 3. 切分规则

1. **沿一级标题边界切**，一个 H1 绝不跨两个子代理（否则汇总时出现半截章节）。
2. **每个子代理最多 1–3 个一级标题**。
3. **单个 H1 预估 > 40 分钟时，只需要让这个子代理处理一个 H1，不需要再让这个子代理派发新的子代理。**
4. **保持原始授课顺序**：Part 01/02/03 必须按讲课先后排列，不得按主题相似度重排。
5. **衔接处理**（二选一，推荐同时做）：
   - 文字稿切片时让相邻片段**重叠 30–60 秒**（或 150–250 字 / 15–25 行）；
   - 在子代理 prompt 里附上**上一段结尾的 200 字原文**与「衔接提示」，让它自然接续、不重复铺垫。
6. 子任务数量的经验值（按每子代理约 20–30 分钟正文估算）：30–60 分钟 → 2 个；1–2 小时 → 4–5 个；2–3 小时 → 6–8 个。**超过 8 个改按 8 个一批分多批派发**，避免并发过高。

> **注意**：文字稿做重叠，但**视频帧不做重叠**（用左闭右开区间 `[start, end)`），否则相邻两个子代理会各自复制同一张边界帧、可能配出重复图。

---

## 4. 切素材（委派 S1 子代理）

切素材是纯机械操作（`sed` 切行、`awk` 搬帧），但很吃命令细节、也占主代理上下文。**委派给一个 S1 子代理一次做完**，主代理只验收结果（第 5 节）。下面的 4.1–4.4 命令手册就是写给 S1 看的，主代理照着验收即可。

> **为什么要切？** 让撰写子代理只读自己那一段——省上下文，且从物理上杜绝它越界写到别的章节去。

### 4.0 S1 子代理 prompt 模板

把占位符替换后派发（`subagent_type: general-purpose`），并附上 `outline.md` 的「切分方案」一节作为依据：

````text
你是素材切分子代理。主代理已定好大纲 {outdir}/outline.md，你按其中「切分方案」把三类素材切成每个 Part 一份。只做机械搬运，不改任何锚点/区间/文件名约定。

工作目录（绝对路径）：{outdir}
仓库根目录：{repo_root}

## 先读
{outdir}/outline.md 的「切分方案」——每个 Part 的稿子锚点（行号或时间）、视频帧区间（秒）、课件页码区间。

## 任务（按下面 4.1–4.4 的命令手册执行）
1. 文字稿切片：{transcript} → parts/transcript_part_01.txt …（相邻段重叠，见切分方案）
   - 无时间戳纯文本 → 用 sed 按行号切（4.1）
   - srt/vtt/带时标 → 首选 ffmpeg 按时间切，异常时用 python 兜底（4.2），务必保留时间戳
2. 视频帧分目录：按每 Part 的帧区间，把 frames/ 里的帧复制进 parts/frames_part_XX/，随带局部 times.txt（4.3）
3. 课件：不搬动。只确认 outline.md 每个 Part 的页码区间都写清楚了（4.4），缺了就在返回里报告，不要自己瞎标。

## 输出（返回给主代理，200 字内）
- 每个 Part 的切片行数/字幕块数、帧目录张数
- 任何异常（切片越界、帧区间无帧、页码缺失等）
````

工作目录一律用绝对路径，S1 执行前先 `cd "<outdir>" && mkdir -p parts`。

### 4.1 文字稿：按行号切（无时间戳的纯文本）

`sed -n '起,止p'` 取行号区间，含首含尾。BSD/GNU sed 都支持。

```bash
# 例：1320 行稿子切成 3 段，相邻段重叠约 20 行（≈ 30–60 秒讲课）
sed -n '1,420p'    transcript.txt > parts/transcript_part_01.txt
sed -n '400,880p'  transcript.txt > parts/transcript_part_02.txt
sed -n '860,1320p' transcript.txt > parts/transcript_part_03.txt

# 自检：行数 + 首尾行（确认没切偏、重叠确实存在）
wc -l parts/transcript_part_*.txt
for f in parts/transcript_part_*.txt; do echo "== $f"; head -2 "$f"; echo "  ..."; tail -2 "$f"; done
```

想用字符数而不是行号切（比如原稿是一整段没有换行）：

```bash
# 取第 1–12000 个字符（-c 是按字节，中文一个字 3 字节，用 python 更准）
python3 -c "
t = open('transcript.txt', encoding='utf-8').read()
open('parts/transcript_part_01.txt','w',encoding='utf-8').write(t[:12000])
open('parts/transcript_part_02.txt','w',encoding='utf-8').write(t[11800:25000])
print('ok', len(t))"
```

### 4.2 文字稿：按时间切（srt / vtt / 带时标的稿子）

**首选 ffmpeg**（会重排序号、保留原始时间戳，已实测可用；注意用绝对路径，见 SKILL.md「已知坑」#1）：

```bash
FF=/opt/homebrew/bin/ffmpeg          # 先 which 确认，沙箱 PATH 可能没有
$FF -y -v error -i subs.srt -ss 00:00:00 -to 00:18:40 parts/transcript_part_01.srt
$FF -y -v error -i subs.srt -ss 00:18:20 -to 00:41:05 parts/transcript_part_02.srt   # 起点回退 20s 做重叠
```

ffmpeg 对 srt 的 `-ss/-to` 支持异常时（老版本、或 vtt 输入），用 python 兜底——按时间区间过滤字幕块，同样保留原始时间戳：

```bash
python3 - <<'PY'
def t2s(t):
    h, m, rest = t.split(':')
    return int(h) * 3600 + int(m) * 60 + float(rest.replace(',', '.'))

def cut(src, dst, s, e):
    blocks = [b for b in open(src, encoding='utf-8').read().strip().split('\n\n') if b.strip()]
    keep = []
    for b in blocks:
        lines = b.split('\n')
        if len(lines) >= 2 and '-->' in lines[1]:
            start = t2s(lines[1].split('-->')[0].strip())
            if s <= start < e:
                keep.append(lines[1:])
    with open(dst, 'w', encoding='utf-8') as f:
        for i, body in enumerate(keep, 1):
            f.write(f"{i}\n" + "\n".join(body) + "\n\n")
    print(f"{dst}: {len(keep)} blocks")

cut('subs.srt', 'parts/transcript_part_01.srt', 0, 1120)
cut('subs.srt', 'parts/transcript_part_02.srt', 1100, 2465)   # 起点回退 20s 做重叠
cut('subs.srt', 'parts/transcript_part_03.srt', 2445, 3780)
PY
```

切片文件里**一定要保留时间戳**——子代理靠它定位视频帧、标注「画面时间」。切完用 `head` 抽查一下第一条和最后一条的时间对得上。

### 4.3 视频帧：按时段搬进各自的目录

把 `times.txt` 里落在本片段时间区间的帧，复制进 `parts/frames_part_XX/`，并**随带一份局部 `times.txt`**——这样子代理不用去翻全量的表，也不可能选到别的时段的帧。

```bash
cd "<outdir>"

# Part 01：0 – 1120 秒（左闭右开，相邻 part 不会重复复制边界帧）
mkdir -p parts/frames_part_01
awk -F'\t' -v s=0    -v e=1120 '$2>=s && $2<e' frames/times.txt > parts/frames_part_01/times.txt
awk -F'\t' '{print $1}' parts/frames_part_01/times.txt | xargs -I{} cp "frames/{}" parts/frames_part_01/

# Part 02：1120 – 2465 秒
mkdir -p parts/frames_part_02
awk -F'\t' -v s=1120 -v e=2465 '$2>=s && $2<e' frames/times.txt > parts/frames_part_02/times.txt
awk -F'\t' '{print $1}' parts/frames_part_02/times.txt | xargs -I{} cp "frames/{}" parts/frames_part_02/

# Part 03：2465 – 3780 秒
mkdir -p parts/frames_part_03
awk -F'\t' -v s=2465 -v e=3780 '$2>=s && $2<e' frames/times.txt > parts/frames_part_03/times.txt
awk -F'\t' '{print $1}' parts/frames_part_03/times.txt | xargs -I{} cp "frames/{}" parts/frames_part_03/
```

一次切完多个片段（片段多时用这个，避免手敲重复命令）：

```bash
python3 - <<'PY'
import os, shutil, subprocess
# (part 号, 起秒, 止秒)
ranges = [(1, 0, 1120), (2, 1120, 2465), (3, 2465, 3780)]
rows = [l.rstrip('\n').split('\t') for l in open('frames/times.txt', encoding='utf-8') if l.strip()]
for idx, s, e in ranges:
    d = f'parts/frames_part_{idx:02d}'
    os.makedirs(d, exist_ok=True)
    sel = [(f, t) for f, t in rows if s <= float(t) < e]
    for f, _ in sel:
        shutil.copy(f'frames/{f}', d)
    with open(f'{d}/times.txt', 'w', encoding='utf-8') as fp:
        fp.write(''.join(f'{f}\t{t}\n' for f, t in sel))
    print(f'{d}: {len(sel)} 帧')
PY
```

自检（三个数字必须一致，且总和 ≈ 全量帧数）：

```bash
wc -l < frames/times.txt
wc -l parts/frames_part_*/times.txt
```

> 没有视频（纯文字稿 + 课件）时跳过这一步，子代理只用课件配图。

### 4.4 课件：不搬动，只标页码

课件**不要**为每个片段另开目录——课件 PDF 是共享素材，复制多份既浪费空间，又容易让页码标注失真。  
主代理要做的只是**在 `outline.md` 里给每个 Part 标出页码区间**，然后在子代理 prompt 里写死。

#### 怎么锁定页码区间

课件常常是**整门课合订的 PDF**（几百页，涵盖十几次课），所以必须先确定本课时用到哪一段页码：

```bash
# ① 有 pdftotext：按关键词粗定位（输出行号 ≈ 页，需要再看图确认）
pdftotext -layout deck.pdf - | grep -n "本讲关键词"

# ② 没有 pdftotext：用多模态抽查幻灯片 PNG——先看目录页/章节分隔页，
#    再每 20–30 页抽一张确认边界
```

主代理通读文字稿时顺手翻一遍课件即可定位，不用单独跑一遍分析。

#### 页码 ↔ 文件名映射

`pdftoppm -png -r 120 deck.pdf slides/slide` 产出的命名规则：

| 页码  | 文件名                    |
| --- | ---------------------- |
| 1   | `slides/slide-01.png`  |
| 9   | `slides/slide-09.png`  |
| 12  | `slides/slide-12.png`  |
| 120 | `slides/slide-120.png` |

即 **数字就是页码**，不足两位补零，超过两位不再补零。在 prompt 里直接写「第 12–38 页，文件名 `slide-012.png` … `slide-038.png`」最清楚。

#### outline.md / prompt 里怎么写

```markdown
- 课件路径：{outdir}/slides/（共 312 页）
- 本片段课件页码：**第 39–92 页**（slide-039.png … slide-092.png）
- ⚠️ 该 PDF 是整门课合订本，本课时只用到第 12–180 页。第 1–11 页是封面目录，
  第 181 页以后属于其他课时，**一律不要使用**。
```

若课件本来就是本课时的（非合订），直接写「全部可用」即可，不用标区间。

---

## 5. 主代理验收 S1 产物

S1 返回后，主代理**亲自**确认一遍再派撰写子代理（不能闭眼收结果）：

```bash
# ① 文字稿切片齐全、有重叠
wc -l parts/transcript_part_*.txt

# ② 帧目录齐全、帧数与 times.txt 对得上、总和 ≈ 全量
wc -l < frames/times.txt; wc -l parts/frames_part_*/times.txt

# ③ outline.md 里每个 Part 都有：稿子锚点 / 帧区间 / 课件页码 / H1 列表
grep -c "课件页码" outline.md     # 应等于 Part 数量（课件非合订时除外）

# ④ 抽查每段切片首尾，确认没切偏、重叠确实存在
for f in parts/transcript_part_*.txt; do echo "== $f"; head -2 "$f"; echo "  ..."; tail -2 "$f"; done
```

- [ ] `outline.md` 中每个 Part 的**稿子锚点、帧区间、课件页码区间**三样都填了
- [ ] 每个 Part 的 H1 列表就是最终笔记要的 H1，数量 1–3 个
- [ ] 每个 Part 目录下 `transcript_part_XX.txt` 与（有视频时）`frames_part_XX/` 都已生成
- [ ] 相邻 Part 的文字稿有重叠，帧区间不重叠

---

## 6. 常见错误

| 错误               | 后果                    | 正确做法                             |
| ---------------- | --------------------- | -------------------------------- |
| 主代理没读稿就让子代理自己定标题 | 各 part 标题重复、粒度不一、顺序错乱 | 大纲必须由主代理通读后定死                    |
| 按「时长均分」而不是按 H1 切 | 一个章节被拦腰截断，汇总出半截 H1    | 沿 H1 边界切，H1 不跨子代理                |
| 一个子代理塞 5 个以上 H1  | 上下文吃紧，后半段质量塌陷         | 每子代理 ≤ 1–3 个 H1                  |
| 把全部帧丢给子代理让它自己筛   | 选到别的时段的帧，配图张冠李戴       | 按时段切进 `frames_part_XX/`，只给本片段的帧  |
| 课件合订 PDF 不标页码    | 子代理用了别的课时的页，配图与内容全错   | outline 与 prompt 里都写死页码区间        |
| 为课件每个片段各复制一份     | 磁盘浪费、页码标注失真           | 课件不搬动，只给路径 + 页码区间                |
| 锚点写「大概第 300 行左右」 | 子代理取错素材，内容错位          | 锚点给确定区间（行号或秒数），切完 `head/tail` 抽查 |
| 为了凑均衡把大主题拆散、小主题合并 | H1 变成「切分块」而不是「课程结构」    | 切分时按真实结构走；真发生了，靠 Phase 6 [`structure-reorder.md`](./structure-reorder.md) 修回来 |
| 委派 S0/S1 素材子代理后不验收 | 抽帧失败/切片越界/页码缺失流到写作阶段，错得难查 | 主代理亲自跑第 5 节验收命令，不闭眼收结果 |

---

## 下一步

素材就绪 → 按 [`subagent-workflow.md`](./subagent-workflow.md) 派发子代理并汇总。
汇总出来的 H1 未必等于课程的真实结构（切分时为均衡工作量会引入失真），所以汇总之后还有 **[Phase 6 结构重排](./structure-reorder.md)**——由主代理对照文字稿重排目录结构，**只改标题行、正文一个字不动**，然后才交付。
