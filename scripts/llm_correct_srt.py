#!/usr/bin/env python3
"""
Whisper SRT 的 LLM + 多模态段级修正（B 方案）

用 Claude Code CLI (`claude -p`) 做后端，**无需 ANTHROPIC_API_KEY**
直接复用你本地的登录态。

方法：
    1. 把 SRT 按时长切段（每段 ~90s，按句号对齐）
    2. 每段选中间时刻的 frame 图（slide 作多模态校准）
    3. 调 `claude -p --model opus --json-schema ... --output-format json`：
       输入 {原 SRT 段 + frame 路径 + 领域上下文}，
       模型用 Read tool 看图后输出修正后的 JSON
    4. 合并回完整 SRT
    5. 每段结果落盘缓存，中断可恢复

用法:
    python3 llm_correct_srt.py \\
        --srt audio.srt \\
        --frames frames/ \\
        --out corrected.srt \\
        --context "南京大学操作系统：链接和加载，讲师 jyy" \\
        [--segment-seconds 90] [--model opus]
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from threading import Lock


@dataclass
class SrtEntry:
    index: int
    start: float
    end: float
    text: str

    def to_block(self) -> str:
        def fmt(t: float) -> str:
            h = int(t // 3600)
            m = int((t % 3600) // 60)
            s = t % 60
            return f"{h:02d}:{m:02d}:{s:06.3f}".replace(".", ",")

        return f"{self.index}\n{fmt(self.start)} --> {fmt(self.end)}\n{self.text}"


def parse_time(s: str) -> float:
    h, m, rest = s.split(":")
    sec, ms = rest.split(",")
    return int(h) * 3600 + int(m) * 60 + int(sec) + int(ms) / 1000.0


def parse_srt(content: str) -> list[SrtEntry]:
    blocks = re.split(r"\n\n+", content.strip())
    entries: list[SrtEntry] = []
    for b in blocks:
        lines = b.strip().splitlines()
        if len(lines) < 3:
            continue
        try:
            idx = int(lines[0])
        except ValueError:
            continue
        m = re.match(r"(\S+)\s*-->\s*(\S+)", lines[1])
        if not m:
            continue
        start, end = parse_time(m.group(1)), parse_time(m.group(2))
        text = "\n".join(lines[2:]).strip()
        entries.append(SrtEntry(idx, start, end, text))
    return entries


def group_into_segments(
    entries: list[SrtEntry],
    segment_seconds: float,
    max_entries: int = 25,
) -> list[list[SrtEntry]]:
    """按时长或条目数兜底切段。
    避免段过大导致 LLM 输出被 4096 token 截断。"""
    groups: list[list[SrtEntry]] = []
    cur: list[SrtEntry] = []
    cur_start: float | None = None
    for e in entries:
        if cur_start is None:
            cur_start = e.start
        cur.append(e)
        elapsed = e.end - cur_start
        ends_with_punc = e.text.rstrip().endswith(
            ("。", "？", "！", ".", "?", "!")
        )
        too_many = len(cur) >= max_entries
        if (elapsed >= segment_seconds and ends_with_punc) or too_many:
            groups.append(cur)
            cur, cur_start = [], None
        elif elapsed >= segment_seconds * 1.6:
            groups.append(cur)
            cur, cur_start = [], None
    if cur:
        groups.append(cur)
    return groups


def pick_frame(frames_dir: Path, t: float) -> Path | None:
    """选择最接近时间 t 的帧。仅支持以 fps=1/15 抽样、命名含数字后缀的 PNG。"""
    pngs = sorted(frames_dir.glob("*.png"))
    if not pngs:
        return None
    # 尝试从文件名提取章节号和帧号：ch2_012.png 或 f_012.png
    best: Path | None = None
    best_diff = 1e18
    for p in pngs:
        m = re.search(r"(?:ch(\d+)_)?0*(\d+)\.png$", p.name)
        if not m:
            continue
        ch = int(m.group(1)) if m.group(1) else 1
        n = int(m.group(2))
        # 粗略估计该帧时间（按 ffmpeg -ss offset 后开始编号）
        # ch1_N 时间 ≈ (N-1)*15；ch2_N 时间 ≈ (N-1)*15（已是 ch2 本地时间）
        # 这里我们不知道 chapter_offset，因此假定 frames_dir 里是整段视频的单一序列
        # 或者 ch1/ch2 时间分别独立。调用方如果传了整段 frames，应保证命名连续。
        # 保守做法：把 ch2 的帧映射到绝对时间（ch1 长度≈2623s）
        CH1_LEN = 2623.0
        nominal = (n - 1) * 15.0 + (CH1_LEN if ch == 2 else 0.0)
        diff = abs(nominal - t)
        if diff < best_diff:
            best_diff = diff
            best = p
    return best


SYSTEM_PROMPT = """你是专业的中英技术讲座字幕修正助手。
任务：修正 Whisper 语音识别产生的 SRT 字幕中的识别错误。

规则：
- **输入有 N 条 SRT 条目，输出也必须包含全部 N 条，一条不少**
- 若某条完全正确，也要原样复制回输出（不要省略任何 index）
- 保留每条原 index，只修正文本
- 专业术语用英文正式拼写（fork, execve, mmap, ELF, PLT, GOT 等）
- 中文同音/近音错误按上下文修正
- 保留讲者的口语填充词和自然停顿
- 绝不意译、改写、合并或拆分条目
- 画面可能提供术语参考；若画面与文本冲突以画面为准

输出：JSON 对象 {"corrections": [{"index": int, "text": str}, ...]}
数组长度必须等于输入条目数 N。不要解释，不要代码块。"""


def build_user_prompt(
    segment: list[SrtEntry],
    frame: Path | None,
    context: str,
) -> str:
    n = len(segment)
    lines = [
        f"课程领域上下文：{context}",
        "",
        f"下面有 **{n}** 条 SRT 条目，你的输出 corrections 数组长度必须等于 {n}：",
    ]
    for e in segment:
        lines.append(f"[{e.index}] {e.text}")
    if frame is not None:
        lines.append("")
        lines.append(f"该时段课件画面路径：{frame}")
        lines.append("请用 Read 工具查看这张图，把它作为修正的参考（专业术语、slide 标题）。")
    lines.append("")
    lines.append(
        f"按要求输出修正后的 JSON 对象。再次强调：corrections 数组必须有 {n} 项，"
        f"覆盖每一条 index（即使文本无需修改也要原样返回）。"
    )
    return "\n".join(lines)


SCHEMA = {
    "type": "object",
    "properties": {
        "corrections": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "index": {"type": "integer"},
                    "text": {"type": "string"},
                },
                "required": ["index", "text"],
            },
        }
    },
    "required": ["corrections"],
}


def call_claude_cli(prompt: str, model: str, timeout: int = 300) -> str:
    cmd = [
        "claude",
        "-p",
        "--model",
        model,
        "--output-format",
        "json",
        "--json-schema",
        json.dumps(SCHEMA),
        "--no-session-persistence",
        "--append-system-prompt",
        SYSTEM_PROMPT,
        prompt,
    ]
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if result.returncode != 0:
        raise RuntimeError(f"claude CLI 失败 rc={result.returncode}: {result.stderr[:400]}")
    return result.stdout


def parse_model_output(s: str) -> tuple[dict[int, str], float]:
    """CLI --output-format=json 返回一个事件数组，最后一个 event.type='result'
    里面有 structured_output 字段（因为我们用了 --json-schema）
    和 total_cost_usd 字段。"""
    s = s.strip()
    if not s:
        return {}, 0.0
    try:
        events = json.loads(s)
    except json.JSONDecodeError:
        return {}, 0.0
    cost = 0.0
    inner: dict | None = None
    if isinstance(events, list):
        for ev in events:
            if isinstance(ev, dict) and ev.get("type") == "result":
                cost = float(ev.get("total_cost_usd") or 0.0)
                inner = ev.get("structured_output")
                if inner is None:
                    # 回退：某些情况下 structured_output 可能放在 result 字符串里
                    r = ev.get("result")
                    if isinstance(r, str) and r.strip().startswith("{"):
                        try:
                            inner = json.loads(r)
                        except json.JSONDecodeError:
                            inner = None
                break
    if inner is None:
        return {}, cost
    arr = inner.get("corrections") if isinstance(inner, dict) else None
    if not isinstance(arr, list):
        return {}, cost
    out: dict[int, str] = {}
    for item in arr:
        if isinstance(item, dict) and "index" in item and "text" in item:
            out[int(item["index"])] = str(item["text"])
    return out, cost


def correct_segment(segment, frames_dir, context, cache_dir, model):
    mid = (segment[0].start + segment[-1].end) / 2
    frame = pick_frame(frames_dir, mid) if frames_dir else None
    cache_key = f"seg_{segment[0].index:05d}_{segment[-1].index:05d}.json"
    cache_path = cache_dir / cache_key
    if cache_path.exists():
        blob = json.loads(cache_path.read_text(encoding="utf-8"))
        # JSON 读出的 key 是 str，需转回 int
        corrs = {int(k): v for k, v in blob["corrections"].items()}
        return corrs, frame, True, 0.0
    prompt = build_user_prompt(segment, frame, context)
    last_err = None
    for attempt in range(3):
        try:
            raw = call_claude_cli(prompt, model)
            parsed, cost = parse_model_output(raw)
            if len(parsed) >= max(1, len(segment) // 2):
                cache_path.write_text(
                    json.dumps({"corrections": parsed, "cost_usd": cost}, ensure_ascii=False),
                    encoding="utf-8",
                )
                return parsed, frame, False, cost
            last_err = f"只解析到 {len(parsed)} / {len(segment)} 条"
        except subprocess.TimeoutExpired:
            last_err = "超时"
        except Exception as e:  # noqa: BLE001
            last_err = str(e)[:200]
        time.sleep(2 + attempt * 2)
    print(
        f"  [seg {segment[0].index}-{segment[-1].index}] 失败: {last_err}",
        file=sys.stderr,
    )
    return {}, frame, False, 0.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--srt", required=True, help="输入 SRT")
    ap.add_argument("--frames", help="帧目录")
    ap.add_argument("--out", required=True, help="输出 SRT")
    ap.add_argument("--context", required=True, help="课程领域上下文（简短）")
    ap.add_argument("--segment-seconds", type=float, default=90.0)
    ap.add_argument("--model", default="opus")
    ap.add_argument("--cache", default=None)
    ap.add_argument("--limit", type=int, default=0, help="只处理前 N 段（调试用）")
    ap.add_argument("--parallel", type=int, default=1, help="并行段数")
    args = ap.parse_args()

    srt_path = Path(args.srt)
    entries = parse_srt(srt_path.read_text(encoding="utf-8"))
    frames_dir = Path(args.frames) if args.frames else None
    cache_dir = Path(args.cache) if args.cache else srt_path.with_suffix(".llm_cache")
    cache_dir.mkdir(parents=True, exist_ok=True)

    segments = group_into_segments(entries, args.segment_seconds)
    if args.limit > 0:
        segments = segments[: args.limit]
    print(f"总条目：{len(entries)}，分段：{len(segments)}，模型：{args.model}")

    index_to_text: dict[int, str] = {e.index: e.text for e in entries}
    cached = changed = 0
    total_cost = 0.0
    lock = Lock()
    done = 0

    def worker(seg):
        t0 = time.time()
        corrections, frame, was_cached, cost = correct_segment(
            seg, frames_dir, args.context, cache_dir, args.model
        )
        return seg, corrections, frame, was_cached, cost, time.time() - t0

    ex = ThreadPoolExecutor(max_workers=max(1, args.parallel))
    if args.parallel <= 1:
        iterator = (worker(seg) for seg in segments)
    else:
        futures = [ex.submit(worker, seg) for seg in segments]
        iterator = (f.result() for f in as_completed(futures))

    for seg, corrections, frame, was_cached, cost, elapsed in iterator:
        with lock:
            done += 1
            i = done
            for idx, new_text in corrections.items():
                if index_to_text.get(idx) != new_text:
                    changed += 1
                index_to_text[idx] = new_text
            if was_cached:
                cached += 1
            total_cost += cost
        print(
            f"  [{i:3d}/{len(segments)}] idx {seg[0].index}-{seg[-1].index} "
            f"({len(seg)} entries, frame={frame.name if frame else '-'}) "
            f"{elapsed:.1f}s → {len(corrections)} 修正 ${cost:.3f}"
            f"{' (cache)' if was_cached else ''}",
            flush=True,
        )
    ex.shutdown()

    out_entries = [
        SrtEntry(e.index, e.start, e.end, index_to_text[e.index]) for e in entries
    ]
    Path(args.out).write_text(
        "\n\n".join(e.to_block() for e in out_entries) + "\n", encoding="utf-8"
    )
    print(f"\n输出：{args.out}")
    print(f"缓存命中：{cached}/{len(segments)}；文本变化条目：{changed}；总成本 ${total_cost:.2f}")


if __name__ == "__main__":
    main()
