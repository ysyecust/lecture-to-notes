"""clean_artifacts.py：只留 PDF / Markdown 交付物，中间产物白名单删除，陌生文件保留。"""

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "clean_artifacts.py"


def touch(path, data=b"x"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


class CleanArtifactsTest(unittest.TestCase):
    def run_clean(self, root, *args):
        return subprocess.run([sys.executable, str(SCRIPT), str(root), *args],
                              capture_output=True, text=True)

    def make_tree(self, tmp):
        """一个 PDF 工作目录（带 tex/字幕/抽帧/图/陌生文件）+ 一个 md 工作目录。"""
        base = Path(tmp) / "courses"
        pdf_dir = base / "course_a" / "source" / "lecture01"
        touch(pdf_dir / "notes.pdf", b"%PDF-1.4")
        touch(pdf_dir / "notes.tex", b"\\documentclass{article}")
        touch(pdf_dir / "audio.srt", b"1")
        touch(pdf_dir / "metadata.json", b"{}")
        touch(pdf_dir / "metadata.tsv", b"a")
        touch(pdf_dir / "verify_notes.txt", b"PASS")
        touch(pdf_dir / "cover.jpg", b"jpg")
        touch(pdf_dir / "notes.aux", b"aux")
        touch(pdf_dir / "dl.log", b"log")
        touch(pdf_dir / "figures" / "fig_01.png", b"png")
        touch(pdf_dir / "frames" / "f_00001.png", b"png")
        touch(pdf_dir / "handwritten-notes.txt", b"keep me")      # 陌生文件
        touch(base / "course_a" / "course.json", b"{}")            # 课程清单要留

        md_dir = base / "md_work"
        touch(md_dir / "note.md", b"# t\n\n![a](assets/t/a.png)\n")
        touch(md_dir / "assets" / "t" / "a.png", b"png")
        touch(md_dir / "assets" / "t" / "b.png", b"png")           # 未被引用（孤图）
        touch(md_dir / "video.mp4", b"mp4")
        touch(md_dir / "frames" / "f_00001.png", b"png")
        touch(md_dir / "transcript.txt", b"text")
        touch(md_dir / "video.txt", b"asr txt")
        touch(md_dir / "audio.mp3", b"mp3")
        touch(md_dir / "teaching_atoms.tsv", b"atom")
        return base, pdf_dir, md_dir

    def test_keeps_deliverables_and_drops_intermediates(self):
        with tempfile.TemporaryDirectory() as tmp:
            base, pdf_dir, md_dir = self.make_tree(tmp)
            r = self.run_clean(base)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

            self.assertTrue((pdf_dir / "notes.pdf").exists())
            self.assertTrue((pdf_dir / "notes.tex").exists(), "tex 是网页正文源，默认必须保留")
            self.assertTrue((pdf_dir / "figures" / "fig_01.png").exists(), "figures/ 是 tex 输入")
            self.assertFalse((pdf_dir / "audio.srt").exists())
            self.assertFalse((pdf_dir / "metadata.json").exists())
            self.assertFalse((pdf_dir / "verify_notes.txt").exists())
            self.assertFalse((pdf_dir / "notes.aux").exists())
            self.assertFalse((pdf_dir / "dl.log").exists())
            self.assertFalse((pdf_dir / "frames").exists())
            self.assertTrue((pdf_dir / "handwritten-notes.txt").exists(), "陌生文件不能删")
            self.assertTrue((base / "course_a" / "course.json").exists())

            self.assertTrue((md_dir / "note.md").exists())
            self.assertTrue((md_dir / "assets" / "t" / "a.png").exists(), "被引用的图要留")
            self.assertFalse((md_dir / "assets" / "t" / "b.png").exists(), "孤图要删")
            self.assertFalse((md_dir / "video.mp4").exists())
            self.assertFalse((md_dir / "frames").exists())
            self.assertFalse((md_dir / "transcript.txt").exists())
            self.assertFalse((md_dir / "video.txt").exists(), "ASR 纯文本输出也是中间产物")
            self.assertFalse((md_dir / "audio.mp3").exists())
            self.assertFalse((md_dir / "teaching_atoms.tsv").exists())

    def test_explicit_path_cleans_without_apply(self):
        """给了目录就是明确意图：不用 --apply 也真删。"""
        with tempfile.TemporaryDirectory() as tmp:
            base, pdf_dir, md_dir = self.make_tree(tmp)
            r = self.run_clean(base)
            self.assertEqual(r.returncode, 0)
            self.assertFalse((pdf_dir / "audio.srt").exists())
            self.assertFalse((md_dir / "video.mp4").exists())

    def test_dry_run_flag_still_only_reports(self):
        with tempfile.TemporaryDirectory() as tmp:
            base, pdf_dir, md_dir = self.make_tree(tmp)
            r = self.run_clean(base, "--dry-run")
            self.assertEqual(r.returncode, 0)
            self.assertIn("未改动任何文件", r.stdout)
            self.assertTrue((pdf_dir / "audio.srt").exists())
            self.assertTrue((md_dir / "video.mp4").exists())
            self.assertTrue((pdf_dir / "audio.srt").exists())
            self.assertTrue((pdf_dir / "frames").exists())
            self.assertTrue((md_dir / "video.mp4").exists())

    def test_drop_tex_opt_in(self):
        with tempfile.TemporaryDirectory() as tmp:
            base, pdf_dir, _ = self.make_tree(tmp)
            r = self.run_clean(base, "--drop-tex")
            self.assertEqual(r.returncode, 0)
            self.assertFalse((pdf_dir / "notes.tex").exists(), "--drop-tex 才删 tex")
            self.assertFalse((pdf_dir / "figures").exists(), "--drop-tex 时 figures/ 也没有用了")
            self.assertFalse((pdf_dir / "notes.aux").exists())

    def test_tex_only_dir_keeps_its_source(self):
        """真实布局：source/lectureNN 只有 notes.tex，PDF 在课程目录下。"""
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp) / "courses"
            src = base / "course_b" / "source" / "lecture09"
            touch(src / "notes.tex", b"\\documentclass{article}")
            touch(src / "figures" / "fig_01.png", b"png")
            touch(src / "audio.srt", b"1")
            touch(src / "verify_notes.txt", b"PASS")
            touch(base / "course_b" / "course_b_09_x.pdf", b"%PDF-1.4")
            r = self.run_clean(base)
            self.assertEqual(r.returncode, 0, r.stdout)
            self.assertTrue((src / "notes.tex").exists(), "web_notes.py 要读它")
            self.assertTrue((src / "figures" / "fig_01.png").exists())
            self.assertFalse((src / "audio.srt").exists())

    def test_no_unreferenced_images_flag(self):
        with tempfile.TemporaryDirectory() as tmp:
            base, _, md_dir = self.make_tree(tmp)
            r = self.run_clean(base, "--no-unreferenced-images")
            self.assertEqual(r.returncode, 0)
            self.assertTrue((md_dir / "assets" / "t" / "b.png").exists())

    def test_only_md_keeps_md_and_assets_only(self):
        """--only-md：只留 *.md 与 assets/，tex / figures / 证据表 / 陌生文件全删。"""
        with tempfile.TemporaryDirectory() as tmp:
            base, pdf_dir, md_dir = self.make_tree(tmp)
            r = self.run_clean(md_dir, "--only-md")
            self.assertEqual(r.returncode, 0, r.stdout)
            left = sorted(p.name for p in md_dir.iterdir())
            self.assertEqual(left, ["assets", "note.md"])
            self.assertTrue((md_dir / "assets" / "t" / "a.png").exists())

    def test_only_md_dry_run_keeps_everything(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, _, md_dir = self.make_tree(tmp)
            r = self.run_clean(md_dir, "--only-md", "--dry-run")
            self.assertEqual(r.returncode, 0)
            self.assertTrue((md_dir / "video.mp4").exists())
            self.assertTrue((md_dir / "teaching_atoms.tsv").exists())

    def test_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            base, _, _ = self.make_tree(tmp)
            self.run_clean(base)
            r = self.run_clean(base)
            self.assertEqual(r.returncode, 0)
            self.assertIn("没有可清理的中间产物", r.stdout)


if __name__ == "__main__":
    unittest.main()
