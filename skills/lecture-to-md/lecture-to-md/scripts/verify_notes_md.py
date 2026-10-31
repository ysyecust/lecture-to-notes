#!/usr/bin/env python3
"""lecture-to-md 预交付门禁：一次性跑完所有机械检查，末行打印 OVERALL PASS / OVERALL FAIL。

对应上游 lecture-to-notes 的 verify_notes.py（LaTeX 版），检查项按 Markdown 输出重写：
density / sections / summaries / per-section / figures / images / duplicates / manifest /
atoms / claims / structure。

用法：
  python3 verify_notes_md.py --workdir ~/x/nju_os_07_mutex2
  python3 verify_notes_md.py --workdir ... --note nju_os_07_mutex2.md --write-claims

退出码：0 = PASS，1 = FAIL。
"""
import argparse
import json
import os
import re
import sys
from collections import Counter

CJK = re.compile(r'[\u3400-\u4dbf\u4e00-\u9fff]')
FIG_LINE = re.compile(r'^!\[(?P<cap>.*?)\]\((?P<path>[^)]+)\)\s*$')
PROV_LINE = re.compile(r'^>\s*(画面时间|课件第)')
H5PLUS = re.compile(r'^#{5,}\s')
FENCE = re.compile(r'^```([A-Za-z0-9_+-]*)$')

# 写手自造的比喻/框架词：出现在正文行里且该行没有「讲义整理/补充」「老师/课件/视频」等归属标记
# 就说明这是笔记作者自己加的框架，而不是课上讲到的内容。按需扩充。
INVENTED_DEVICES = ('台阶', '路线图', '打个比方', '直观解读', '加速比', '不变式',
                    '降级成', '一句话总结', '本质上是', '底层逻辑')
ATTRIBUTION_MARKERS = ('讲义整理', '讲义补充', '老师', '课件', '视频', '板书', '画面')  # 只认 ASCII 语言标签，CJK 也算粘连

# 每种模式的密度门槛，与上游 LaTeX 版一致（中文正文字数 / 图数）
GATES = {
    'technical-slide': dict(cjk=lambda t: max(5000, round(70 * t)), sec_min=8),
    'mixed': dict(cjk=lambda t: max(3500, round(55 * t)), sec_min=6),
    'conceptual-talk': dict(cjk=lambda t: max(2500, round(45 * t)), sec_min=5),
}


def read(path):
    with open(path, encoding='utf-8') as f:
        return f.read()


def fail(name, msg):
    print(f'FAIL  [{name}] {msg}')
    return 1


def ok(name, msg):
    print(f'PASS  [{name}] {msg}')
    return 0


def warn(name, msg):
    print(f'WARN  [{name}] {msg}')
    return 0


def parse_note(text):
    """切成 (正文行, 图片块, 标题)。图片块 = 图片行 + 紧随的来源行。"""
    lines = text.split('\n')
    heads, figs = [], []
    kept = []
    i, in_code = 0, False
    while i < len(lines):
        line = lines[i]
        if line.startswith('```'):
            in_code = not in_code
        m = FIG_LINE.match(line)
        if m:
            prov = lines[i + 1].strip() if i + 1 < len(lines) else ''
            figs.append(dict(cap=m.group('cap'), path=m.group('path'), prov=prov, line=i + 1))
            i += 2
            continue
        if not in_code and line.startswith('#'):
            heads.append(line)
        kept.append(line)
        i += 1
    return lines, heads, figs, kept


def sections(lines):
    """按一级标题切块：返回 [(title, [行])]，第一个是文档标题块。
    代码围栏内的 `# 注释` 不是标题。"""
    out, cur, in_code = [], ('(preamble)', []), False
    for line in lines:
        if line.startswith('```'):
            in_code = not in_code
        elif not in_code and re.match(r'^# ', line):
            out.append(cur)
            cur = (line, [])
            continue
        cur[1].append(line)
    out.append(cur)
    return out


def body_chars(block):
    """去掉图片行、来源行、代码围栏内容后的中文字数（与总字数同一口径）。"""
    return len(CJK.findall('\n'.join(strip_code_and_figs(block))))


def strip_code_and_figs(block):
    out, in_code = [], False
    for l in block:
        if l.startswith('```'):
            in_code = not in_code
            out.append(l)
            continue
        if in_code:
            continue
        if FIG_LINE.match(l) or PROV_LINE.match(l):
            continue
        out.append(l)
    return out


def count_blocks(block):
    """统计公式块、代码块、表格、判断框（非图片来源的引用块）。"""
    math = code = table = box = 0
    in_code = False
    in_math = False
    prev_box = False
    for l in block:
        if l.startswith('```'):
            in_code = not in_code
            if in_code:
                code += 1
            prev_box = False
            continue
        if in_code:
            continue
        if l.strip() == '$$':
            in_math = not in_math
            if not in_math:
                math += 1
            prev_box = False
            continue
        if in_math:
            continue
        if re.match(r'^\s*\|.*\|\s*$', l):
            table += 1
            prev_box = False
            continue
        is_box = l.startswith('>') and not PROV_LINE.match(l)
        if is_box and not prev_box:
            box += 1
        prev_box = is_box
    table = 1 if table else 0
    return dict(math=math, code=code, table=table, box=box)


def image_size(path):
    """读 PNG / JPEG 的像素尺寸，返回 (w, h)；读不出返回 None。"""
    try:
        with open(path, 'rb') as f:
            head = f.read(26)
            if head[:8] == b'\x89PNG\r\n\x1a\n' and len(head) >= 24:
                return int.from_bytes(head[16:20], 'big'), int.from_bytes(head[20:24], 'big')
            if head[:2] != b'\xff\xd8':
                return None
            f.seek(2)                       # JPEG：扫 SOF 段取高宽
            while True:
                byte = f.read(1)
                while byte and byte != b'\xff':
                    byte = f.read(1)
                marker = f.read(1)
                while marker == b'\xff':
                    marker = f.read(1)
                if not marker:
                    return None
                if marker[0] in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7,
                                 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
                    f.read(3)               # 段长(2) + 精度(1)
                    h = int.from_bytes(f.read(2), 'big')
                    w = int.from_bytes(f.read(2), 'big')
                    return (w, h) if w and h else None
                seg = f.read(2)
                if len(seg) < 2:
                    return None
                f.seek(int.from_bytes(seg, 'big') - 2, os.SEEK_CUR)
    except OSError:
        return None


def load_tsv(path):
    rows = []
    if not os.path.exists(path):
        return None
    with open(path, encoding='utf-8') as f:
        head = f.readline().rstrip('\n').split('\t')
        for line in f:
            if not line.strip():
                continue
            rows.append(dict(zip(head, line.rstrip('\n').split('\t'))))
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--workdir', required=True)
    ap.add_argument('--note', default=None, help='默认取 workdir 下唯一的 *.md（排除 outline.md / README）')
    ap.add_argument('--profile', default='lecture_profile.json')
    ap.add_argument('--duration', type=float, default=None, help='秒；缺省读 metadata.json')
    ap.add_argument('--write-claims', action='store_true', help='回写 numerical_claims.tsv 的 in_notes 列')
    ap.add_argument('--min-section-chars', type=int, default=300)
    args = ap.parse_args()

    wd = os.path.abspath(args.workdir)
    rc = 0

    # ---------- 0. 定位文件 ----------
    if args.note:
        note_path = os.path.join(wd, args.note)
    else:
        cands = [f for f in sorted(os.listdir(wd))
                 if f.endswith('.md') and f not in ('outline.md', 'README.md')]
        if len(cands) != 1:
            print(f'FAIL  [artifacts] 无法唯一确定讲义文件（候选：{cands}），请用 --note 指定')
            print('\nOVERALL FAIL')
            return 1
        note_path = os.path.join(wd, cands[0])
    if not os.path.exists(note_path):
        print(f'FAIL  [artifacts] 讲义不存在：{note_path}')
        print('\nOVERALL FAIL')
        return 1

    text = read(note_path)
    lines, heads, figs, kept = parse_note(text)

    # ---------- 1. 时长 ----------
    duration = args.duration
    if duration is None:
        meta = os.path.join(wd, 'metadata.json')
        if os.path.exists(meta):
            try:
                duration = float(json.load(open(meta, encoding='utf-8'))['duration'])
            except Exception:
                duration = None
    minutes = (duration or 0) / 60.0

    # ---------- 2. profile ----------
    profile = {}
    prof_path = os.path.join(wd, args.profile)
    if not os.path.exists(prof_path):
        rc |= fail('artifacts', f'缺 {args.profile}（模式/读者产出/原子数；见 SKILL.md Phase 2.4）')
    else:
        try:
            profile = json.load(open(prof_path, encoding='utf-8'))
        except Exception as e:
            rc |= fail('artifacts', f'{args.profile} 解析失败：{e}')
        need = ['mode', 'audience', 'central_question', 'reader_outcome',
                'visual_teaching_atoms', 'formula_teaching_atoms']
        missing = [k for k in need if k not in profile]
        if missing:
            rc |= fail('artifacts', f'{args.profile} 缺字段：{missing}')
        elif profile['mode'] not in GATES:
            rc |= fail('artifacts', f'mode 非法：{profile["mode"]}（可选 {list(GATES)}）')

    mode = profile.get('mode', 'technical-slide')
    gate = GATES.get(mode, GATES['technical-slide'])

    # ---------- 3. 必备产物 ----------
    for name, hint in [('transcript.txt', '文字稿'), ('teaching_atoms.tsv', '教学原子表'),
                       ('numerical_claims.tsv', '数字声明表'), ('figure_manifest.tsv', '配图表')]:
        p = os.path.join(wd, name)
        if not os.path.exists(p):
            rc |= fail('artifacts', f'缺 {name}（{hint}）')
        elif name.endswith('.tsv') and os.path.getsize(p) == 0:
            rc |= fail('artifacts', f'{name} 为空')
    frames_times = os.path.join(wd, 'frames', 'times.txt')
    if os.path.exists(frames_times):
        n_png = len([f for f in os.listdir(os.path.join(wd, 'frames')) if f.endswith('.png')])
        n_t = len(open(frames_times, encoding='utf-8').read().strip().split('\n'))
        if n_png != n_t:
            rc |= fail('artifacts', f'frames/times.txt {n_t} 行 != {n_png} 张帧')
        else:
            ok('artifacts', f'frames/times.txt 与 {n_png} 张帧一致')

    # ---------- 4. 密度 ----------
    blocks = sections(lines)
    h1 = [b for b in blocks if b[0].startswith('# ') and not b[0].startswith('## ')]
    chapters = h1[1:]
    cjk_total = len(CJK.findall('\n'.join(strip_code_and_figs(kept))))
    gate_cjk = gate['cjk'](minutes) if minutes else None
    if gate_cjk is None:
        rc |= warn('density', '无法确定视频时长，跳过字数门槛')
    elif cjk_total < gate_cjk:
        rc |= fail('density', f'中文正文 {cjk_total} 字 < 门槛 {gate_cjk}（mode={mode}, T={minutes:.1f}min）')
    else:
        ok('density', f'中文正文 {cjk_total} 字 >= 门槛 {gate_cjk}（mode={mode}, T={minutes:.1f}min）')

    # ---------- 5. 章节结构 ----------
    if len(chapters) > 10:
        rc |= fail('sections', f'一级标题 {len(chapters)} > 10')
    elif minutes >= 60 and len(chapters) < gate['sec_min']:
        rc |= fail('sections', f'一级标题 {len(chapters)} < {gate["sec_min"]}（T={minutes:.1f}min, mode={mode}）')
    else:
        ok('sections', f'一级标题 {len(chapters)} 个（正文，不含文档标题）')

    per_h2 = [(c[0], len([l for l in c[1] if l.startswith('## ')])) for c in chapters]
    bad_h2 = [t for t, n in per_h2 if n > 10]
    if bad_h2:
        rc |= fail('sections', f'这些章的小节数 > 10：{bad_h2}')
    else:
        ok('sections', '每章二级标题 <= 10')

    # ---------- 6. 每章小结 + 每章下限 ----------
    no_sum, thin = [], []
    for title, block in chapters:
        subs = [l for l in block if l.startswith('## ')]
        if not any('小结' in s for s in subs):
            no_sum.append(title.strip('# ').strip())
        chars = body_chars(block)
        cb = count_blocks(block)
        has_extra = cb['math'] or cb['code'] or cb['table'] or cb['box'] >= 2
        floor = max(args.min_section_chars, round(0.7 * cjk_total / max(1, len(chapters))))
        if chars < floor or not has_extra:
            thin.append(f'{title.strip("# ")[:18]}({chars}字,公式{cb["math"]}/代码{cb["code"]}/表{cb["table"]}/框{cb["box"]})')
    if no_sum:
        rc |= fail('summaries', f'{len(no_sum)} 章缺「本章小结」小节：{no_sum}')
    else:
        ok('summaries', f'{len(chapters)}/{len(chapters)} 章都有本章小结')
    if thin:
        rc |= fail('per-section', f'{len(thin)} 章未达下限（字数或公式/代码/表格/两个判断框）：{thin}')
    else:
        ok('per-section', f'{len(chapters)}/{len(chapters)} 章满足下限')

    # ---------- 7. 配图 ----------
    cap = max(20, round(minutes / 3.5)) if minutes else None
    visual_atoms = int(profile.get('visual_teaching_atoms', 0) or 0)
    need_figs = min(visual_atoms, cap) if cap else visual_atoms
    if cap and len(figs) > cap:
        rc |= warn('figures', f'配图 {len(figs)} 张 > 目标上限 {cap}（不算失败，但每张都要挣到版面）')
    if visual_atoms and len(figs) < need_figs:
        rc |= fail('figures', f'配图 {len(figs)} 张 < 需要 {need_figs}（视觉原子 {visual_atoms}，上限 {cap}）')
    else:
        ok('figures', f'配图 {len(figs)} 张（视觉原子 {visual_atoms}，上限 {cap}）')

    miss_file, miss_prov, dup = [], [], []
    seen = Counter(os.path.basename(f['path']) for f in figs)
    dup = [k for k, v in seen.items() if v > 1]
    for f in figs:
        p = os.path.join(wd, f['path'])
        if not os.path.exists(p):
            miss_file.append(f['path'])
        if not PROV_LINE.match(f['prov']):
            miss_prov.append(f"{os.path.basename(f['path'])}@行{f['line']}")
    if miss_file:
        rc |= fail('images', f'{len(miss_file)} 张图文件不存在：{miss_file}')
    if miss_prov:
        rc |= fail('images', f'{len(miss_prov)} 张图缺「> 画面时间」/「> 课件第 N 页」：{miss_prov}')
    if dup:
        rc |= fail('duplicates', f'同一张图被引用多次：{dup}')
    if not (miss_file or miss_prov or dup):
        ok('images', f'{len(figs)} 张图文件存在且都有来源标注，无重复引用')

    # ---------- 8. figure_manifest 对账 ----------
    manifest = load_tsv(os.path.join(wd, 'figure_manifest.tsv'))
    if manifest is None:
        rc |= fail('manifest', '缺 figure_manifest.tsv')
    else:
        m_files = {os.path.basename(r.get('figure', '')) for r in manifest if r.get('figure')}
        n_files = set(seen)
        only_md = n_files - m_files
        only_tsv = m_files - n_files
        if only_md or only_tsv:
            rc |= fail('manifest', f'与讲义不一致：仅讲义有 {sorted(only_md)}；仅表里有 {sorted(only_tsv)}')
        else:
            bad_time = [r['figure'] for r in manifest
                        if not re.match(r'^\d{1,2}:\d{2}(:\d{2})?$', (r.get('start') or '').strip())]
            if bad_time:
                rc |= fail('manifest', f'这些图缺合法 start 时间：{bad_time}')
            else:
                ok('manifest', f'{len(manifest)} 张图与讲义一一对应')

    # ---------- 9. teaching atoms ----------
    atoms = load_tsv(os.path.join(wd, 'teaching_atoms.tsv'))
    if atoms is None:
        rc |= fail('atoms', '缺 teaching_atoms.tsv')
    else:
        n = len(atoms)
        low = 15 if mode == 'technical-slide' else 10
        bad = [a.get('atom', '?') for a in atoms if (a.get('status') or '').strip().lower() != 'ok']
        if n < low:
            rc |= fail('atoms', f'只有 {n} 条原子（mode={mode} 要求 >= {low}）')
        elif bad:
            rc |= fail('atoms', f'{len(bad)} 条原子未标 ok：{bad[:5]}')
        else:
            ok('atoms', f'{n} 条教学原子全部 ok')

    # ---------- 10. numerical claims ----------
    claims = load_tsv(os.path.join(wd, 'numerical_claims.tsv'))
    if claims is None:
        rc |= fail('claims', '缺 numerical_claims.tsv')
    elif not claims:
        ok('claims', '表内无数字声明（header-only）')
    else:
        flat = re.sub(r'\s', '', text)
        rows, missing = [], []
        for r in claims:
            val = re.sub(r'\s', '', (r.get('value') or '').strip())
            hit = bool(val) and val in flat
            r = dict(r)
            r['in_notes'] = 'yes' if hit else 'no'
            rows.append(r)
            if not hit:
                missing.append(f"{r.get('claim', '?')}={val}")
        header = list(claims[0].keys()) if claims else ['claim', 'value', 'source_time', 'in_notes']
        if 'in_notes' not in header:
            header.append('in_notes')
        if args.write_claims:                 # 保留原表头，只更新 in_notes 一列
            with open(os.path.join(wd, 'numerical_claims.tsv'), 'w', encoding='utf-8') as f:
                f.write('\t'.join(header) + '\n')
                for r in rows:
                    f.write('\t'.join((r.get(k) or '') for k in header) + '\n')
        if missing:
            rc |= fail('claims', f'{len(missing)}/{len(rows)} 条数字没进正文：{missing}')
        else:
            ok('claims', f'{len(rows)} 条数字声明全部出现在正文')

    # ---------- 11. 结构卫生 ----------
    thin_sec, empty_h1, h5 = [], [], [l for l in heads if H5PLUS.match(l)]
    for title, block in blocks:
        if not title.startswith('#'):
            continue
        if title.startswith('## ') and body_chars(block) < 60:
            thin_sec.append(title.strip('# ')[:20])
    for title, block in chapters:
        if body_chars(block) == 0:
            empty_h1.append(title.strip('# ')[:20])
    if h5:
        rc |= fail('structure', f'出现五级及以下标题：{h5[:3]}')
    if thin_sec:
        rc |= fail('structure', f'这些小节正文 < 60 字（疑似只有图或提纲）：{thin_sec}')
    if empty_h1:
        rc |= fail('structure', f'这些章没有正文：{empty_h1}')
    if not (h5 or thin_sec or empty_h1):
        ok('structure', '无空章、无只有图的小节、无五级标题')

    # ---------- 13/14. 配图尺寸：与 manifest 的 panel 对账 + 是否整帧原图 ----------
    fig_mode = (profile.get('figure_mode') or 'full').lower()

    def find_figure(name):
        for root, _, files in os.walk(wd):
            if name in files:
                return os.path.join(root, name)
        return None

    bad_crop, cropped, unreadable, checked = [], [], [], 0
    for r in (manifest or []):
        fig, frame = r.get('figure') or '', r.get('frame') or ''
        box = re.match(r'^(\d+),(\d+),(\d+),(\d+)$', (r.get('panel') or '').strip())
        path = find_figure(fig) if fig else None
        if not path:
            continue                       # 缺文件已在 [images] 里报过
        size = image_size(path)
        if size is None:
            unreadable.append(fig)         # 读不出尺寸不再静默跳过
            continue
        if box:
            checked += 1
            want = (int(box.group(3)), int(box.group(4)))
            if abs(size[0] - want[0]) > 2 or abs(size[1] - want[1]) > 2:
                bad_crop.append(f'{fig} 实际 {size[0]}x{size[1]} != 登记 {want[0]}x{want[1]}')
        if fig_mode == 'full' and frame:
            fsize = image_size(os.path.join(wd, frame))
            if fsize and fsize != size:
                cropped.append(f'{fig} {size[0]}x{size[1]} != 原帧 {fsize[0]}x{fsize[1]}')

    if unreadable:
        rc |= fail('crop', f'{len(unreadable)} 张图读不出尺寸（不是 PNG/JPEG，或文件损坏）：{unreadable[:4]}')
    if bad_crop:
        rc |= fail('crop', f'{len(bad_crop)} 张图尺寸与 manifest 的 panel 框不符（可能截掉了内容）：{bad_crop[:4]}')
    elif checked and not unreadable:
        ok('crop', f'{checked} 张图尺寸与 manifest 的 panel 框一致')
    elif not checked and not unreadable:
        print('SKIP  [crop] manifest 里没有可对账的 panel 框，本项未检查')
    if cropped:
        rc |= fail('figure-mode', f'{len(cropped)} 张图不是整帧原图（figure_mode=full）：{cropped[:3]}')
    elif fig_mode == 'full' and manifest:
        ok('figure-mode', 'figure_mode=full：所有配图与原帧同尺寸，未裁切')

    # ---------- 15. 不许自造比喻/框架 ----------
    transcript = os.path.join(wd, 'transcript.txt')
    source_words = read(transcript) if os.path.exists(transcript) else ''
    invented = []
    in_code = False
    for i, line in enumerate(lines):
        if line.startswith('```'):
            in_code = not in_code
            continue
        if in_code or not line.strip():
            continue
        if not any(w in line for w in INVENTED_DEVICES):
            continue
        for sentence in re.split(r'(?<=[。！？；])', line):
            hits = [w for w in INVENTED_DEVICES if w in sentence and w not in source_words]
            if hits and not any(m in sentence for m in ATTRIBUTION_MARKERS):
                invented.append(f'行{i + 1}: {sentence.strip()[:40]}')
    if invented:
        rc |= fail('voice', '这些句子出现写手自造的框架/比喻且没标归属（讲稿里也没有）：' + '; '.join(invented[:3]))
    else:
        ok('voice', '未发现未标注的自造框架/比喻')

    # ---------- 12. Markdown 格式（围栏与空行） ----------
    fmt = []
    n_fence = 0
    in_code = False
    for i, line in enumerate(lines):
        if line.startswith('```'):
            n_fence += 1
            if not FENCE.match(line):
                fmt.append(f'行{i + 1} 围栏行不合法（围栏后面粘了正文？）：{line[:30]}')
            in_code = not in_code
            continue
        if in_code:
            continue
        if line.startswith('#') and i > 0 and lines[i - 1].strip() != '':
            fmt.append(f'行{i + 1} 标题前缺空行')
        if line.startswith('![') and i > 0 and lines[i - 1].strip() != '':
            fmt.append(f'行{i + 1} 图片前缺空行')
    if n_fence % 2:
        fmt.append(f'代码围栏 {n_fence} 个（奇数，有未闭合的代码块）')
    if fmt:
        rc |= fail('format', '; '.join(fmt[:5]))
    else:
        ok('format', f'围栏 {n_fence // 2} 对均合法，标题/图片前都有空行')

    print('\nOVERALL ' + ('FAIL' if rc else 'PASS'))
    return 1 if rc else 0


if __name__ == '__main__':
    sys.exit(main())
