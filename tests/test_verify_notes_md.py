"""verify_notes_md.py 的门禁行为测试：好样本必须 PASS，坏样本必须 FAIL。"""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills" / "lecture-to-md" / "lecture-to-md" / "scripts" / "verify_notes_md.py"

PNG_4x4 = bytes.fromhex(
    "89504e470d0a1a0a0000000d494844520000000400000004080200000026930929"
    "0000000f4944415408d763f8cf0000030101000018dd8db10000000049454e44ae426082")

PNG_8x8 = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000080000000808020000004b6d29dc"
    "0000000f4944415408d763f8cfc00000030101000018dd8db10000000049454e44ae426082")

BODY = (
    "这一小节说明机制如何运作，为什么需要它，以及什么时候会失效。"
    "我们把老师讲过的条件、代价和边界都写清楚，让第一次读的人也能顺着推下来。" * 12
    + "实测耗时 133ms。"
)

NOTE_OK = f"""# 测试课程

# 一、第一章

## 小节甲

![图甲的说明](assets/t/a.png)
> 画面时间 00:01:30

{BODY}

```c
int x = 1;   // 代码块
```

## 本章小结

小结第一段，回答本章问题。{BODY}

# 二、第二章

## 小节乙

![图乙的说明](assets/t/b.png)
> 画面时间 00:02:30

{BODY}

| 方案 | 代价 |
| --- | --- |
| 甲 | 小 |

## 本章小结

小结第二段，交给下一章。{BODY}
"""


def write_workdir(tmp, *, note=NOTE_OK, atoms=20, claims_value="133ms", dup=False):
    wd = Path(tmp)
    (wd / "assets" / "t").mkdir(parents=True)
    for name in ("a", "b"):
        (wd / "assets" / "t" / f"{name}.png").write_bytes(PNG_8x8)
    (wd / "frames").mkdir()
    (wd / "frames" / "f_00001.png").write_bytes(PNG_8x8)
    (wd / "frames" / "times.txt").write_text("f_00001.png\t0\n", encoding="utf-8")
    (wd / "transcript.txt").write_text("文字稿" * 100, encoding="utf-8")
    (wd / "metadata.json").write_text(json.dumps({"duration": 300}), encoding="utf-8")
    (wd / "lecture_profile.json").write_text(json.dumps({
        "mode": "conceptual-talk", "audience": "读者", "central_question": "问",
        "reader_outcome": "答", "visual_teaching_atoms": 2, "formula_teaching_atoms": 0,
    }), encoding="utf-8")
    (wd / "teaching_atoms.tsv").write_text(
        "atom\tstatus\tevidence\n" + "".join(f"原子{i}\tok\t小节甲\n" for i in range(atoms)),
        encoding="utf-8")
    (wd / "numerical_claims.tsv").write_text(
        f"claim\tvalue\tsource_time\tin_notes\n耗时\t{claims_value}\t01:00\t\n", encoding="utf-8")
    rows = "".join(f"{n}.png\tframes/f_00001.png\t00:0{i}:30\t00:0{i}:35\ttopic\t0,0,8,8\n"
                   for i, n in enumerate(["a", "b"], start=1))
    (wd / "figure_manifest.tsv").write_text("figure\tframe\tstart\tend\ttopic\tpanel\n" + rows,
                                            encoding="utf-8")
    text = note
    if dup:
        text = text.replace(
            "![图乙的说明](assets/t/b.png)", "![图甲的说明](assets/t/a.png)")
    (wd / "note.md").write_text(text, encoding="utf-8")
    return wd


class VerifyNotesMdTest(unittest.TestCase):
    def run_gate(self, wd):
        return subprocess.run(
            [sys.executable, str(SCRIPT), "--workdir", str(wd), "--note", "note.md"],
            capture_output=True, text=True)

    def test_good_note_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            wd = write_workdir(tmp)
            r = self.run_gate(wd)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertIn("OVERALL PASS", r.stdout)

    def test_missing_artifacts_fail(self):
        with tempfile.TemporaryDirectory() as tmp:
            wd = write_workdir(tmp)
            (wd / "teaching_atoms.tsv").unlink()
            r = self.run_gate(wd)
            self.assertEqual(r.returncode, 1)
            self.assertIn("teaching_atoms.tsv", r.stdout)
            self.assertIn("OVERALL FAIL", r.stdout)

    def test_duplicate_figure_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            wd = write_workdir(tmp, dup=True)
            r = self.run_gate(wd)
            self.assertEqual(r.returncode, 1)
            self.assertIn("[duplicates]", r.stdout)

    def test_claim_not_in_body_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            wd = write_workdir(tmp, claims_value="999ms")
            r = self.run_gate(wd)
            self.assertEqual(r.returncode, 1)
            self.assertIn("[claims]", r.stdout)

    def test_fence_glued_to_text_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            note = NOTE_OK + "\n```text\n散落的代码块\n```这一行粘在围栏上了\n"
            wd = write_workdir(tmp, note=note)
            r = self.run_gate(wd)
            self.assertEqual(r.returncode, 1)
            self.assertIn("[format]", r.stdout)

    def test_crop_size_mismatch_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            wd = write_workdir(tmp)
            # 图实际 4x4，manifest 登记 8x8 → 尺寸不符
            (wd / "assets" / "t" / "a.png").write_bytes(PNG_4x4)
            r = self.run_gate(wd)
            self.assertEqual(r.returncode, 1)
            self.assertIn("[crop]", r.stdout)

    def test_comment_inside_code_fence_is_not_a_heading(self):
        """shell/C 代码块里行首 `# 注释` 不能算成章节。"""
        with tempfile.TemporaryDirectory() as tmp:
            note = NOTE_OK.replace(
                "```c\nint x = 1;   // 代码块\n```",
                "```bash\n# 启动虚拟机并等待就绪\nqemu-system-x86_64 -hda disk.img\n```")
            wd = write_workdir(tmp, note=note)
            r = self.run_gate(wd)
            self.assertIn("一级标题 2 个", r.stdout)
            self.assertIn("2/2 章都有本章小结", r.stdout)
            self.assertEqual(r.returncode, 0, r.stdout)

    def test_invented_framing_fails(self):
        """自己造的框架/比喻（课上没这么说）必须被抓出来。"""
        with tempfile.TemporaryDirectory() as tmp:
            note = NOTE_OK.replace("## 本章小结\n\n小结第一段",
                                   "## 本章小结\n\n这一讲可以分成四个台阶：\n\n小结第一段")
            wd = write_workdir(tmp, note=note)
            r = self.run_gate(wd)
            self.assertEqual(r.returncode, 1)
            self.assertIn("[voice]", r.stdout)

    def test_marked_supplement_passes_voice(self):
        with tempfile.TemporaryDirectory() as tmp:
            note = NOTE_OK.replace("## 本章小结\n\n小结第一段",
                                   "## 本章小结\n\n> **补充（讲义整理）**：教材里把这两个动作叫 acquire / release。\n\n小结第一段")
            wd = write_workdir(tmp, note=note)
            r = self.run_gate(wd)
            self.assertNotIn("FAIL  [voice]", r.stdout)

    def test_cropped_figure_fails_when_full_required(self):
        with tempfile.TemporaryDirectory() as tmp:
            wd = write_workdir(tmp)
            (wd / "frames" / "f_00001.png").write_bytes(PNG_8x8)          # 原帧 8x8
            (wd / "assets" / "t" / "a.png").write_bytes(PNG_4x4)          # 裁成 4x4
            (wd / "assets" / "t" / "b.png").write_bytes(PNG_8x8)
            (wd / "figure_manifest.tsv").write_text(
                "figure\tframe\tstart\tend\ttopic\tpanel\n"
                "a.png\tframes/f_00001.png\t00:01:30\t00:01:35\tt\t0,0,4,4\n"
                "b.png\tframes/f_00001.png\t00:02:30\t00:02:35\tt\t0,0,8,8\n",
                encoding="utf-8")
            r = self.run_gate(wd)
            self.assertEqual(r.returncode, 1)
            self.assertIn("[figure-mode]", r.stdout)

    def test_teacher_wording_passes_voice(self):
        """讲稿里出现过的词（老师原话）不能被判成自造框架。"""
        with tempfile.TemporaryDirectory() as tmp:
            note = NOTE_OK.replace("## 本章小结\n\n小结第一段",
                                   "## 本章小结\n\n打个比方，我们有两个共享变量。\n\n小结第一段")
            wd = write_workdir(tmp, note=note)
            (wd / "transcript.txt").write_text("老师：打个比方，我们有两个共享变量。" * 5,
                                               encoding="utf-8")
            r = self.run_gate(wd)
            self.assertNotIn("FAIL  [voice]", r.stdout)

    def test_invented_word_in_marked_paragraph_fails(self):
        """同一段里只要出现归属词就放过——现在要按句判。"""
        with tempfile.TemporaryDirectory() as tmp:
            note = NOTE_OK.replace("## 本章小结\n\n小结第一段",
                                   "## 本章小结\n\n老师说这很重要。我们把全讲分成四个台阶。\n\n小结第一段")
            wd = write_workdir(tmp, note=note)
            r = self.run_gate(wd)
            self.assertEqual(r.returncode, 1)
            self.assertIn("[voice]", r.stdout)

    def test_cropped_jpeg_fails(self):
        """JPEG 图也要能读出尺寸，裁过就必须 FAIL。"""
        try:
            from PIL import Image
        except ImportError:
            self.skipTest("Pillow 不可用")
        with tempfile.TemporaryDirectory() as tmp:
            wd = write_workdir(tmp)
            Image.new("RGB", (4, 4)).save(wd / "assets" / "t" / "a.jpg")
            (wd / "assets" / "t" / "a.png").unlink()
            md = (wd / "note.md").read_text(encoding="utf-8").replace("a.png", "a.jpg")
            (wd / "note.md").write_text(md, encoding="utf-8")
            manifest = (wd / "figure_manifest.tsv").read_text(encoding="utf-8")
            (wd / "figure_manifest.tsv").write_text(
                manifest.replace("a.png", "a.jpg").replace("0,0,8,8", "0,0,4,4", 1),
                encoding="utf-8")
            r = self.run_gate(wd)
            self.assertEqual(r.returncode, 1)
            self.assertIn("[figure-mode]", r.stdout)

    def test_claims_extra_column_preserved(self):
        """--write-claims 只改 in_notes，不丢别的列。"""
        with tempfile.TemporaryDirectory() as tmp:
            wd = write_workdir(tmp)
            (wd / "numerical_claims.tsv").write_text(
                "claim\tvalue\tsource_time\tin_notes\tnote\n耗时\t133ms\t01:00\t\t人工补写\n",
                encoding="utf-8")
            subprocess.run([sys.executable, str(SCRIPT), "--workdir", str(wd),
                            "--note", "note.md", "--write-claims"],
                           capture_output=True, text=True)
            head, row = (wd / "numerical_claims.tsv").read_text(encoding="utf-8").split("\n")[:2]
            self.assertIn("note", head)
            self.assertIn("人工补写", row)
            self.assertTrue(row.endswith("yes\t人工补写"))

    def test_missing_summary_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            note = NOTE_OK.replace("## 本章小结\n\n小结第二段，交给下一章。", "## 别的标题\n\n不是小结。")
            wd = write_workdir(tmp, note=note)
            r = self.run_gate(wd)
            self.assertEqual(r.returncode, 1)
            self.assertIn("[summaries]", r.stdout)


if __name__ == "__main__":
    unittest.main()
