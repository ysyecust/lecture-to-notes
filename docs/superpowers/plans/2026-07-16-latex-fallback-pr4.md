# LaTeX Fallback PR #4 Implementation Plan

> **Execution note:** Run this plan inline, task by task, unless the user explicitly authorizes delegated agents. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Verify contributor PR #4 in full-TeX and no-`ctex` environments, merge it with attribution, and retain regression coverage on the feature branch.

**Architecture:** Treat the contributor branch as untrusted input and test a local merge candidate before changing GitHub state. Static unit tests assert the dependency-check and template contracts; a disposable Debian/TeX container proves the fallback compiles without `ctex`. After the remote PR is merged, rebase the course-library branch and add the same regression tests as a maintainer follow-up.

**Tech Stack:** Git worktrees, GitHub CLI, Python `unittest`, XeLaTeX, Docker, TeX Live

---

### Task 1: Freeze and inspect the PR candidate

**Files:**
- Read: `skills/lecture-to-notes/SKILL.md`
- Read: `skills/lecture-to-notes/assets/notes-template.tex`
- Read: `tests/test_x_support_docs.py`
- Create temporarily: `/Users/shaoyiyang/.config/superpowers/worktrees/lecture-to-notes/pr4-review/`

- [ ] **Step 1: Fetch the exact PR head and record metadata**

Run:

```bash
git fetch origin main pull/4/head:refs/heads/review/pr-4
gh pr view 4 --repo ysyecust/lecture-to-notes \
  --json number,title,author,baseRefOid,headRefOid,mergeable,mergeStateStatus,files,url
```

Expected: head SHA `6a8607f3fbb79c5ac5c15aa3ab13e4361212b92d`, base SHA `41add956b043c3e9c59ae60cfb547715dc58a764`, two changed files, and `MERGEABLE/CLEAN`.

- [ ] **Step 2: Create a disposable review worktree**

Run:

```bash
git worktree add /Users/shaoyiyang/.config/superpowers/worktrees/lecture-to-notes/pr4-review review/pr-4
git -C /Users/shaoyiyang/.config/superpowers/worktrees/lecture-to-notes/pr4-review status --short --branch
```

Expected: clean `review/pr-4` worktree at the recorded PR head.

- [ ] **Step 3: Inspect only the declared patch and active Unicode controls**

Run:

```bash
git -C /Users/shaoyiyang/.config/superpowers/worktrees/lecture-to-notes/pr4-review \
  diff --check origin/main...HEAD
git -C /Users/shaoyiyang/.config/superpowers/worktrees/lecture-to-notes/pr4-review \
  diff --name-only origin/main...HEAD
python3 - <<'PY'
from pathlib import Path
root = Path('/Users/shaoyiyang/.config/superpowers/worktrees/lecture-to-notes/pr4-review')
for relative in (
    'skills/lecture-to-notes/SKILL.md',
    'skills/lecture-to-notes/assets/notes-template.tex',
):
    text = (root / relative).read_text(encoding='utf-8')
    bad = [(index, hex(ord(char))) for index, char in enumerate(text)
           if ord(char) in range(0x202A, 0x202F) or ord(char) in range(0x2066, 0x206A)]
    assert not bad, (relative, bad)
print('unicode-controls: clean')
PY
```

Expected: only `skills/lecture-to-notes/SKILL.md` and `skills/lecture-to-notes/assets/notes-template.tex`; no whitespace errors or bidirectional controls.

### Task 2: Add regression tests to the local candidate

**Files:**
- Create temporarily: `/Users/shaoyiyang/.config/superpowers/worktrees/lecture-to-notes/pr4-review/tests/test_latex_fallback.py`
- Test: `tests/test_latex_fallback.py`

- [ ] **Step 1: Write the contract test**

Create `tests/test_latex_fallback.py` in the review worktree with:

```python
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILL = (ROOT / "skills/lecture-to-notes/SKILL.md").read_text(encoding="utf-8")
TEMPLATE = (
    ROOT / "skills/lecture-to-notes/assets/notes-template.tex"
).read_text(encoding="utf-8")


class LatexFallbackTests(unittest.TestCase):
    def test_skill_checks_every_template_package(self):
        checked = set(re.findall(r"for pkg in ([^;]+); do", SKILL)[0].split())
        required = {
            "ctex", "tcolorbox", "environ", "trimspaces", "listings",
            "hyperref", "booktabs", "float", "subcaption", "etoolbox",
        }
        self.assertTrue(required <= checked, required - checked)

    def test_template_prefers_ctex_and_has_native_xetex_fallback(self):
        self.assertIn(r"\IfFileExists{ctex.sty}", TEMPLATE)
        self.assertIn(r"\usepackage[fontset=fandol]{ctex}", TEMPLATE)
        self.assertIn(r"\XeTeXlinebreaklocale \"zh\"", TEMPLATE)
        self.assertIn("Songti SC", TEMPLATE)
        self.assertIn("Noto Serif CJK SC", TEMPLATE)
        self.assertLess(
            TEMPLATE.index(r"\IfFileExists{ctex.sty}"),
            TEMPLATE.index(r"\usepackage{amsmath, amssymb}"),
        )

    def test_install_guidance_names_every_non_core_package(self):
        install_line = next(
            line for line in SKILL.splitlines() if "tlmgr install ctex" in line
        )
        for package in ("ctex", "tcolorbox", "environ", "trimspaces", "etoolbox"):
            self.assertIn(package, install_line)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the test against the PR head**

Run:

```bash
cd /Users/shaoyiyang/.config/superpowers/worktrees/lecture-to-notes/pr4-review
PYTHONPATH=tests python3 -m unittest test_latex_fallback -v
```

Expected: all three tests pass. If the install-guidance test fails because a checked package is missing from the installation command, request a PR correction rather than weakening the assertion.

- [ ] **Step 3: Run the existing suite and classify only known baseline drift**

Run:

```bash
python3 -m unittest discover -s tests -v
```

Expected on the unmodified PR branch: the existing stale phrase assertion may be the only failure. Any other failure blocks merge. The main feature branch already fixes that stale assertion in commit `9cde695`.

### Task 3: Compile both template branches

**Files:**
- Read: `skills/lecture-to-notes/assets/notes-template.tex`
- Create temporarily: `/tmp/lecture-to-notes-pr4-full/notes.tex`
- Create temporarily: `/tmp/lecture-to-notes-pr4-minimal/Dockerfile`

- [ ] **Step 1: Compile with the host TeX distribution where `ctex` exists**

Run:

```bash
test -n "$(kpsewhich ctex.sty)"
rm -rf /tmp/lecture-to-notes-pr4-full
mkdir -p /tmp/lecture-to-notes-pr4-full
cp skills/lecture-to-notes/assets/notes-template.tex /tmp/lecture-to-notes-pr4-full/notes.tex
cd /tmp/lecture-to-notes-pr4-full
xelatex -halt-on-error -interaction=nonstopmode notes.tex
xelatex -halt-on-error -interaction=nonstopmode notes.tex
pdfinfo notes.pdf | sed -n '1,12p'
```

Expected: two successful XeLaTeX passes and a non-empty PDF.

- [ ] **Step 2: Build a disposable TeX image without the Chinese language bundle**

Create `/tmp/lecture-to-notes-pr4-minimal/Dockerfile` with:

```dockerfile
FROM debian:bookworm-slim
RUN apt-get update \
 && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
      fonts-noto-cjk texlive-latex-extra texlive-pictures texlive-xetex \
 && rm -rf /var/lib/apt/lists/*
WORKDIR /work
```

Run:

```bash
docker build -t lecture-to-notes-pr4-minimal /tmp/lecture-to-notes-pr4-minimal
docker run --rm lecture-to-notes-pr4-minimal sh -lc \
  'test -z "$(kpsewhich ctex.sty)" && kpsewhich tcolorbox.sty && kpsewhich environ.sty'
```

Expected: `ctex.sty` is absent while the box dependencies are present.

- [ ] **Step 3: Compile the fallback branch in the restricted container**

Run:

```bash
rm -rf /tmp/lecture-to-notes-pr4-minimal/output
mkdir -p /tmp/lecture-to-notes-pr4-minimal/output
cp skills/lecture-to-notes/assets/notes-template.tex \
  /tmp/lecture-to-notes-pr4-minimal/output/notes.tex
docker run --rm --network none --read-only --cap-drop ALL \
  --security-opt no-new-privileges --memory 1g --cpus 2 --pids-limit 256 \
  --tmpfs /tmp:rw,size=256m \
  -v /tmp/lecture-to-notes-pr4-minimal/output:/work:rw \
  lecture-to-notes-pr4-minimal \
  sh -lc 'xelatex -halt-on-error -interaction=nonstopmode notes.tex && xelatex -halt-on-error -interaction=nonstopmode notes.tex'
pdfinfo /tmp/lecture-to-notes-pr4-minimal/output/notes.pdf | sed -n '1,12p'
```

Expected: the log takes the fallback path, contains no missing-character storm for the template's Chinese labels, and produces a PDF.

### Task 4: Merge the contributor PR and retain coverage

**Files:**
- Create: `tests/test_latex_fallback.py`
- Modify: `RELEASE_NOTES.md`

- [ ] **Step 1: Approve and merge only after Tasks 1–3 pass**

Run:

```bash
gh pr review 4 --repo ysyecust/lecture-to-notes --approve \
  --body "Verified package-contract tests, full ctex compilation, and a no-ctex XeTeX fallback compile."
gh pr merge 4 --repo ysyecust/lecture-to-notes --merge --delete-branch
gh pr view 4 --repo ysyecust/lecture-to-notes \
  --json state,mergedAt,mergeCommit,url
```

Expected: PR state `MERGED`, Issue #3 closed, and a merge commit recorded.

- [ ] **Step 2: Rebase the course-library branch on the merged main**

Run:

```bash
git fetch origin main
git rebase origin/main
python3 -m unittest discover -s tests -v
```

Expected: 43/43 existing tests pass after rebase.

- [ ] **Step 3: Add the verified regression test to the feature branch**

Copy the already-tested contract file from the still-mounted disposable review worktree, then verify byte-for-byte identity:

```bash
cp /Users/shaoyiyang/.config/superpowers/worktrees/lecture-to-notes/pr4-review/tests/test_latex_fallback.py \
  tests/test_latex_fallback.py
test "$(shasum -a 256 tests/test_latex_fallback.py | cut -d' ' -f1)" = \
  "$(shasum -a 256 /Users/shaoyiyang/.config/superpowers/worktrees/lecture-to-notes/pr4-review/tests/test_latex_fallback.py | cut -d' ' -f1)"
```

Then run:

```bash
PYTHONPATH=tests python3 -m unittest test_latex_fallback -v
python3 -m unittest discover -s tests -v
```

Expected: 46 tests pass.

- [ ] **Step 4: Document the contributor-visible change**

Append this entry under the newest release heading in `RELEASE_NOTES.md`:

```markdown
- Accept lecture-note compilation on minimal XeTeX installations by checking required
  LaTeX packages explicitly and falling back to native CJK line breaking when `ctex`
  is unavailable. Contribution: @liyuankui in PR #4.
```

Run:

```bash
python3 -m unittest discover -s tests -v
git diff --check
```

Expected: all tests pass and the diff is clean.

- [ ] **Step 5: Commit the maintainer follow-up**

Run:

```bash
git add tests/test_latex_fallback.py RELEASE_NOTES.md
git commit -m "test: cover minimal LaTeX fallback"
```

Expected: one focused commit after the contributor merge.

### Task 5: Remove review-only state

**Files:**
- Remove worktree: `/Users/shaoyiyang/.config/superpowers/worktrees/lecture-to-notes/pr4-review/`

- [ ] **Step 1: Remove the disposable worktree and branch**

Run:

```bash
git worktree remove /Users/shaoyiyang/.config/superpowers/worktrees/lecture-to-notes/pr4-review
git branch -D review/pr-4
git worktree list
```

Expected: only the main and course-library worktrees remain.

- [ ] **Step 2: Record the verified frontier**

Run:

```bash
git status --short --branch
git log --oneline -5
python3 -m unittest discover -s tests -v
```

Expected: clean feature worktree and all tests green before beginning the site plan.
