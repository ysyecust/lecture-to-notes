# Contributing PDFs

The course library accepts PDF-only pull requests. A contribution is not published
until a maintainer reviews and merges it into the trusted `main` branch.

## Upload in a browser

1. Fork this repository on GitHub.
2. In your fork, open `content/inbox/` and choose **Add file → Upload files**.
3. Add lowercase `.pdf` files directly to that directory. Do not change code,
   manifests, or existing files in the same pull request.
4. Open a pull request using the **PDF contribution** template and check the rights
   declaration exactly as written.

GitHub may ask you to create a fork automatically when you start from the
[upload page](https://github.com/ysyecust/lecture-to-notes/upload/main/content/inbox).

## Upload from the command line

```bash
git clone https://github.com/<your-account>/lecture-to-notes.git
cd lecture-to-notes
git switch -c contribute/my-course-pdfs
cp /path/to/lecture.pdf content/inbox/
git add content/inbox/lecture.pdf
git commit -m "content: contribute my course lecture"
git push -u origin contribute/my-course-pdfs
```

Then open a pull request against `ysyecust/lecture-to-notes:main` and complete the
PDF contribution template.

## What automation does

The pull-request check compares the complete base and submission trees, then runs
the submitted PDFs in an isolated, unprivileged container. It verifies PDF
structure, rejects active-content features, extracts a title and page count,
computes a SHA-256 digest, and creates a WebP first-page preview. Generated reports
are review artifacts only; unmerged content is never deployed.

After review, a maintainer may normalize titles, move PDFs from the inbox into a
course directory, and update the trusted course manifest. The Pages site is built
only from merged `main` content.

## Submission envelope

- Add 1–10 PDFs per pull request.
- Each PDF must be no larger than 25 MiB.
- The combined PDF size must be no larger than 100 MiB.
- Use a lowercase `.pdf` extension and add files directly under `content/inbox/`.
- Do not submit symlinks, archives, scripts, or edits to existing files.
- Only submit material you have the right to share for educational use.

These bounds keep external pull-request scanning predictable. They are not limits
on the course library or on maintainer-managed releases.
