# 双格式讲义的发布约定

## 阅读器

`reader.html?id=<catalog item id>` 只加载目录中的讲义。通过构建校验的条目默认显示网页正文，可通过工具栏或 `&format=pdf` 切换到原版 PDF；仅发布 PDF 的条目直接显示 PDF。

PDF.js 由 `package.json` 锁定版本并随站点本地打包，不依赖公共 CDN；支持文本层搜索、书签、页码、适宽与 25%–800% 缩放，禁用 PDF 内置 JavaScript。阅读位置保存在浏览器 `localStorage` 中（按文件 SHA-256 区分）。

## 已归档的源材料

每讲的 `web_source.tex` 指向课程目录下的归档源文件：

- **南京大学《生成式软件工程》**（`content/courses/nju-gse-2026/`）：`source/notes.tex`（第 1 讲）及 `source/lecture02/notes.tex` 至 `source/lecture10/notes.tex`（第 2–10 讲）。
- **CMU 11-768 AI Agents**（`content/courses/cmu-ai-agents/`）：`source/lecture01/notes.tex` 至 `source/lecture04/notes.tex`（第 1–4 讲）。
- **技术与研究分享**（`content/courses/technical-talks/`）：`source/jascha_anthropocene_investigator/notes.tex` 与 `source/lauren_tan_trust_coding_agents/notes.tex`。

源文件、对应 PDF 和引用图片的 SHA-256 固定在课程 manifest 的 `web_source` 中。修改其中任何内容后，必须复核并更新 profile，不能通过自动刷新哈希绕过内容审阅。

## 组件与转换

`scripts/web_notes.py` 仅解析 TeX 源码（借助 Pandoc AST 与项目适配层处理提示框、`vtag`/`srcnote` 图注与时间区间），不运行 TeX 引擎或 shell 命令。每份通过校验的讲义生成：

- `notes/<id>/article.html`：可重排的网页正文
- `notes/<id>/document.json`：章节、阅读块与来源元数据
- `notes/<id>/report.json`：源文件/PDF/图片/HTML 哈希与组件计数
- `data/web-notes-report.json`：全部候选条目的通过或阻断原因

## 必须通过的检查

- 源文件、PDF 和图片哈希一致，路径不得越界或经过符号链接。
- 未知 raw TeX、文件读写或执行类命令直接阻断转换。
- 章节、图片、提示框、表格、公式、时间字符串计数与 manifest 的 `expected` 一致。
- 图注与时间区间一对一对应，AST 文字与代码完整保留在输出正文中，MathML 无 `merror`。
- 输出无脚本、内嵌框架、事件属性或非法链接协议。

任一检查未通过时，清理该讲的网页输出，仅保留原版 PDF。

## 为新讲义生成待审阅 profile

```bash
python3 -m scripts.web_notes \
  --course content/courses/nju-gse-2026/course.json \
  --file nju_gse_2026_03_repository_management_zh.pdf \
  --tex source/lecture03/notes.tex \
  --output .tmp/lecture03-profile-review.json
```

该命令生成 `needs_review` 候选供维护者对照源文件和 PDF 审阅；确认无误后再将 `web_source` 写入课程 `course.json`。
