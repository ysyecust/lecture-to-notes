#!/usr/bin/env python3
"""清理讲义工作目录：只保留交付物（PDF / Markdown 及其引用的图片）。

中间产物（字幕、抽帧、元数据表、编译辅助文件、日志）都是可重跑的，删掉不影响成品；
但**不认识的文件一律保留**——白名单删除，绝不整目录乱删。

    python3 scripts/clean_artifacts.py                # 无参数：扫 content/courses，只报告
    python3 scripts/clean_artifacts.py <workdir>      # 给了路径：直接清理该目录
    python3 scripts/clean_artifacts.py <workdir> --dry-run   # 给了路径但只看清单
    python3 scripts/clean_artifacts.py --apply        # 无参数时也要真删 content/courses
    python3 scripts/clean_artifacts.py <workdir> --drop-tex  # 连 notes.tex 一起删（默认保留）
    python3 scripts/clean_artifacts.py <workdir> --only-md   # 只留 *.md 与 assets/，其余全删

默认**保留 `notes.tex` 与 `figures/`**：网页正文（`web_notes.py`）从 tex 生成、PDF 也靠它重编译，
误删代价高。要彻底只留 PDF/Markdown 才加 `--drop-tex`。

退出码：0 = 正常执行（含「没有可清理的东西」）；参数错误由 argparse 返回 2。
"""
import argparse
import os
import re
import sys

# —— 交付物 ——
DELIVERABLE_EXT = {'.pdf', '.md'}
MD_NOT_DELIVERABLE = {'readme.md', 'outline.md'}

# —— 中间产物（白名单：只有这些会被删）——
DROP_DIRS = {'frames', 'slides', 'parts'}
DROP_DIRS_WITH_TEX = DROP_DIRS | {'figures'}   # --drop-tex 时 figures/ 也没用了
KEEP_SOURCE_DIRS = {'figures'}                  # tex 的输入图：默认保留，不算「未识别」
DROP_IMAGE_DIRS = {'assets'}          # 只有 md 的图片目录会清孤图；figures/ 是 tex 输入
DROP_PATTERNS = [
    r'^(video|audio)\.(mp4|mkv|webm|flv|mov|mp3|wav|m4a|aac|flac)$',
    r'^(video|audio)(\.[\w-]+)?\.txt$',
    r'.*\.(srt|vtt)$',
    r'.*\.tsv$',
    r'.*\.log$',
    r'^metadata\.json$',
    r'^lecture_profile\.json$',
    r'^bands\.json$',
    r'^layout\.json$',
    r'^frame_scores\.json$',
    r'^verify_notes\.txt$',
    r'^verify_figures\.txt$',
    r'^(figure|frame)_verification\.txt$',
    r'^rendered_notes\.txt$',
    r'^transcript.*\.txt$',
    r'^rendered.*\.(aux|log|out|toc|fls|fdb_latexmk)$',
    r'^notes\.(aux|log|out|toc|fls|fdb_latexmk|synctex\.gz)$',
    r'^cover\.jpg$',
]
KEEP_JSON = {'course.json', 'papers.json', 'package.json'}
SKIP_DIRS = {'.git', 'node_modules', '.venv', '__pycache__', '.tmp', '.agents'}
IMAGE_MD = re.compile(r'!\[[^\]]*\]\(\s*<?([^)\s>]+)')
IMAGE_HTML = re.compile(r'<img[^>]+src=["\']([^"\']+)')


def human(n):
    for unit in ('B', 'K', 'M', 'G'):
        if n < 1024 or unit == 'G':
            return f'{n:.0f}{unit}' if unit == 'B' else f'{n:.1f}{unit}'
        n /= 1024


def md_images(md_path):
    """返回 md 里引用的图片绝对路径集合。"""
    try:
        text = open(md_path, encoding='utf-8').read()
    except (OSError, UnicodeDecodeError):
        return set()
    out = set()
    for m in list(IMAGE_MD.finditer(text)) + list(IMAGE_HTML.finditer(text)):
        target = m.group(1)
        if target.startswith(('http://', 'https://', 'data:')):
            continue
        out.add(os.path.normpath(os.path.join(os.path.dirname(md_path), target)))
    return out


def is_deliverable(name):
    low = name.lower()
    return low.endswith('.pdf') or (low.endswith('.md') and low not in MD_NOT_DELIVERABLE)


def drop_reason(name, drop_tex):
    low = name.lower()
    if low == 'notes.tex':
        return 'tex（PDF 源码，--drop-tex）' if drop_tex else None
    if low.endswith('.json') and low not in KEEP_JSON:
        return '元数据/json'
    for pat in DROP_PATTERNS:
        if re.match(pat, name, re.IGNORECASE):
            return '中间产物'
    return None


def collect(root, drop_tex, clean_images):
    """返回 (待删文件列表[(path, reason)], 保留但未识别的文件列表, 需整体删除的目录列表)。"""
    to_delete, unknown, dirs_to_drop = [], [], []
    keep_images, deliverable_dirs = set(), set()
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for name in filenames:
            if name.lower().endswith('.md'):
                keep_images |= md_images(os.path.join(dirpath, name))
            if is_deliverable(name):
                deliverable_dirs.add(os.path.normpath(dirpath))

    def under_image_dir(dirpath):
        """路径里出现 assets/ figures/ frames/ … → 属于图片产物目录。"""
        cur = os.path.normpath(dirpath)
        rootn = os.path.normpath(root)
        while True:
            if os.path.basename(cur) in DROP_IMAGE_DIRS:
                return True
            if cur in deliverable_dirs or cur == rootn or os.path.dirname(cur) == cur:
                return False
            cur = os.path.dirname(cur)

    def in_workdir(dirpath):
        """自己或任一祖先目录里有交付物 → 属于某个讲义工作目录。"""
        cur = os.path.normpath(dirpath)
        rootn = os.path.normpath(root)
        while True:
            if cur in deliverable_dirs:
                return True
            if cur == rootn or os.path.dirname(cur) == cur:
                return False
            cur = os.path.dirname(cur)

    for dirpath, dirnames, filenames in os.walk(root, topdown=False):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        base = os.path.basename(dirpath)
        referenced = any(os.path.normpath(os.path.join(dirpath, n)) in keep_images for n in filenames)

        drop_dirs = DROP_DIRS_WITH_TEX if drop_tex else DROP_DIRS
        if base in drop_dirs and not referenced:
            dirs_to_drop.append(dirpath)
            continue

        for name in filenames:
            path = os.path.join(dirpath, name)
            if path in keep_images or is_deliverable(name):
                continue
            reason = drop_reason(name, drop_tex)
            if reason:
                to_delete.append((path, reason))
                continue
            if clean_images and under_image_dir(dirpath) and in_workdir(dirpath) \
                    and name.lower().endswith(('.png', '.jpg', '.jpeg', '.webp', '.gif')):
                to_delete.append((path, '未被讲义引用的图片'))
                continue
            if name == 'notes.tex' or base in KEEP_SOURCE_DIRS:
                continue                      # 按设计保留，不是「未识别」
            if not name.startswith('.'):
                unknown.append(path)
    return to_delete, unknown, dirs_to_drop


def dir_size(path):
    total = 0
    for dirpath, _, filenames in os.walk(path):
        for name in filenames:
            try:
                total += os.path.getsize(os.path.join(dirpath, name))
            except OSError:
                pass
    return total


def main(argv=None):
    ap = argparse.ArgumentParser(description='清理讲义工作目录，只保留 PDF / Markdown 交付物')
    ap.add_argument('paths', nargs='*', default=None,
                    help='要清理的目录（默认 content/courses；不存在则退回当前目录）')
    ap.add_argument('--apply', action='store_true',
                    help='无参数（扫 content/courses）时也真删；给了路径本来就真删')
    ap.add_argument('--dry-run', action='store_true', help='强制只报告，不删任何文件')
    ap.add_argument('--drop-tex', action='store_true',
                    help='连 notes.tex 一起删（默认保留：网页正文与 PDF 重编译都要它）')
    ap.add_argument('--only-md', action='store_true',
                    help='只保留 *.md 与 assets/，其余文件（含未知文件、tex、证据表）全部删除')
    ap.add_argument('--no-unreferenced-images', action='store_true',
                    help='不清理未被 md 引用的图片（默认清理 assets/ 下的孤图）')
    args = ap.parse_args(argv)
    # 给了具体目录 = 明确意图，默认真删；没给参数扫全库时才需要 --apply 确认
    apply = not args.dry_run and (args.apply or bool(args.paths))

    roots = args.paths or ['content/courses']
    roots = [r for r in roots if os.path.isdir(r)] or ['.']

    total_files, total_bytes = 0, 0
    for root in roots:
        clean_images = not args.no_unreferenced_images
        to_delete, unknown, dirs_to_drop = collect(root, args.drop_tex, clean_images)

        freed = sum(os.path.getsize(p) for p, _ in to_delete if os.path.exists(p))
        freed += sum(dir_size(d) for d in dirs_to_drop)
        n_files = len(to_delete) + sum(
            len(files) for d in dirs_to_drop if os.path.isdir(d)
            for _, _, files in os.walk(d))

        if to_delete or dirs_to_drop:
            print(f'\n{root}：删除 {len(to_delete)} 个文件 + {len(dirs_to_drop)} 个目录，'
                  f'释放约 {human(freed)}')
            for path, reason in sorted(to_delete)[:40]:
                print(f'  - {os.path.relpath(path, root)}  ({reason})')
            if len(to_delete) > 40:
                print(f'  … 另有 {len(to_delete) - 40} 个文件')
            for d in sorted(dirs_to_drop)[:20]:
                print(f'  - {os.path.relpath(d, root)}/  (整个目录：抽帧/切分/课件图)')
        else:
            print(f'\n{root}：没有可清理的中间产物')

        if args.only_md:
            keep_prefix = os.path.join(os.path.abspath(root), 'assets')
            already = {os.path.abspath(x) for x, _ in to_delete}
            extra = []
            for dirpath, dirnames, filenames in os.walk(root, topdown=False):
                if os.path.abspath(dirpath) == keep_prefix or \
                        os.path.abspath(dirpath).startswith(keep_prefix + os.sep):
                    continue
                dirnames[:] = [d for d in dirnames
                               if os.path.abspath(os.path.join(dirpath, d)) != keep_prefix]
                for name in filenames:
                    path = os.path.join(dirpath, name)
                    if name.lower().endswith('.md') or os.path.abspath(path) in already \
                            or not os.path.exists(path):
                        continue
                    extra.append((path, '--only-md 只留 md 与 assets'))
                if not os.listdir(dirpath) and os.path.abspath(dirpath) != os.path.abspath(root):
                    try:
                        os.rmdir(dirpath)
                    except OSError:
                        pass
            if extra:
                freed += sum(os.path.getsize(x) for x, _ in extra if os.path.exists(x))
                n_files += len(extra)
                print(f'  严格模式额外删除 {len(extra)} 个文件（tex/证据表/未识别文件）')
                if apply:
                    for path, _ in extra:
                        try:
                            os.remove(path)
                        except OSError as e:
                            print(f'  ! 删除失败 {path}: {e}')
                unknown = []

        if unknown:
            print(f'  保留 {len(unknown)} 个未识别文件（不认识的绝不删）')
            for path in sorted(unknown)[:5]:
                print(f'    · {os.path.relpath(path, root)}')

        if apply:
            for path, _ in to_delete:
                try:
                    os.remove(path)
                except OSError as e:
                    print(f'  ! 删除失败 {path}: {e}')
            for d in dirs_to_drop:
                try:
                    for dirpath, dirnames, filenames in os.walk(d, topdown=False):
                        for name in filenames:
                            os.remove(os.path.join(dirpath, name))
                        for name in dirnames:
                            os.rmdir(os.path.join(dirpath, name))
                    os.rmdir(d)
                except OSError as e:
                    print(f'  ! 删除失败 {d}: {e}')
            for dirpath, _, filenames in os.walk(root, topdown=False):
                if not filenames and not os.listdir(dirpath) and dirpath != root:
                    try:
                        os.rmdir(dirpath)
                    except OSError:
                        pass

        total_files += n_files
        total_bytes += freed

    verb = '已删除' if apply else '将删除'
    print(f'\n合计{verb} {total_files} 个文件，约 {human(total_bytes)}')
    if not apply:
        print('（只报告，未改动任何文件：加 --apply 或直接给目录路径才会真删）')
    return 0


if __name__ == '__main__':
    sys.exit(main())
