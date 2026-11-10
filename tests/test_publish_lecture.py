import json
import shutil
import tempfile
import unittest
from pathlib import Path

from scripts.publish_lecture import manifest_stats, publish_workdir, sync_readme_stats
from tests.pdf_factory import write_pdf


ROOT = Path(__file__).resolve().parents[1]


class PublishLectureTests(unittest.TestCase):
    def test_live_readme_stats_match_course_manifests(self):
        stats = sync_readme_stats(ROOT, check_only=True)
        self.assertGreaterEqual(stats["course_count"], 9)
        self.assertGreaterEqual(stats["lecture_count"], 103)
        self.assertGreaterEqual(stats["page_count"], 2543)

    def test_sync_readme_updates_stale_counts_and_publish_archives_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            course_dir = root / "content/courses/demo"
            course_dir.mkdir(parents=True)
            write_pdf(course_dir / "lec01.pdf")
            (course_dir / "course.json").write_text(
                json.dumps(
                    {
                        "id": "demo",
                        "title": "Demo Course",
                        "institution": "Test U",
                        "term": "2026",
                        "items": [
                            {
                                "file": "lec01.pdf",
                                "title": "Lecture 1",
                                "order": 1,
                                "expected_pages": 1,
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            (root / "README.md").write_text(
                "介绍（当前共 1 门课程与专题、1 讲、1 页正课讲义）。\n",
                encoding="utf-8",
            )
            (root / "README.en.md").write_text(
                "Intro — currently 1 courses and collections, 1 lectures, and 1 lecture pages).\n",
                encoding="utf-8",
            )

            workdir = root / "workspace/lec02"
            (workdir / "figures").mkdir(parents=True)
            write_pdf(workdir / "notes.pdf")
            (workdir / "metadata.json").write_text(
                json.dumps({"duration": 2400, "webpage_url": "https://www.bilibili.com/video/BVdemo/"}),
                encoding="utf-8",
            )
            (workdir / "notes.tex").write_text(
                r"\documentclass{article}\begin{document}\section{一}正文\end{document}",
                encoding="utf-8",
            )

            has_pandoc = shutil.which("pandoc") is not None
            result = publish_workdir(
                root,
                workdir,
                course_dir / "course.json",
                "lec02.pdf",
                "lecture02",
                "Lecture 2",
                instructor="Prof. X",
                include_web_source=has_pandoc,
            )
            self.assertEqual(result["stats"], {"course_count": 1, "lecture_count": 2, "page_count": 2})
            self.assertTrue((course_dir / "lec02.pdf").is_file())
            if has_pandoc:
                self.assertTrue((course_dir / "source/lecture02/notes.tex").is_file())
                self.assertIn("web_source", result["entry"])
            self.assertIn("当前共 1 门课程与专题、2 讲、2 页正课讲义", (root / "README.md").read_text(encoding="utf-8"))
            self.assertIn("currently 1 courses and collections, 2 lectures, and 2 lecture pages", (root / "README.en.md").read_text(encoding="utf-8"))
            self.assertEqual(manifest_stats(root), {"course_count": 1, "lecture_count": 2, "page_count": 2})


if __name__ == "__main__":
    unittest.main()
