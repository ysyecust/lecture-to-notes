# 双格式讲义的发布约定

## 阅读器

`reader.html?id=<catalog item id>` 只接受目录中的讲义。通过构建校验的条目优先显示网页正文；`&format=pdf` 或格式按钮可打开原版 PDF。PDF-only 条目仍可阅读和下载。

PDF.js 6.3.289 由 npm 锁定安装，站点构建从本地依赖复制浏览器模块、worker、字体和许可文件；不依赖公共 CDN。PDF.js 提供文本层、书签、页码、适宽、搜索和 25%–800% 缩放。高倍率使用有像素预算的画布及可见区域细节渲染。PDF JavaScript 不执行，WebAssembly 和 eval 均不启用。

阅读位置按 PDF SHA-256 保存；HTML 位置还绑定对应的 HTML 哈希。网页记录阅读块与偏移，PDF 记录页码、坐标和缩放。数据仅保存在本机 localStorage；不可用时继续阅读。

## 已归档的三个试点

- 第 1 讲：`content/courses/nju-gse-2026/source/notes.tex`。
- 第 2 讲：`content/courses/nju-gse-2026/source/lecture02/notes.tex`。
- 第 3 讲：`content/courses/nju-gse-2026/source/lecture03/notes.tex`。

第三讲归档的源文件将封面讲次修正为 3，与已发布 PDF 一致；原始工作目录不修改。源文件、对应 PDF 和引用图片的 SHA-256 都固定在课程 manifest 的 `web_source` 中。修改其中任何内容后，必须复核并更新 profile；不能通过自动刷新哈希来绕过内容审阅。

## 组件与转换

`scripts/web_notes.py` 只解析 TeX，不运行 TeX 引擎或 shell 命令。Pandoc 负责通用 AST；项目适配层处理五类提示框以及 `footnotemark`/`footnotetext`、`vtag`/`srcnote` 图注配对。图中时间不得被普通 LaTeX 转换静默丢弃。

统一组件包括章节、阅读块、提示框、图文及时间区间、数学表达、表格、代码。每份通过校验的讲义输出：

- `notes/<id>/article.html`：可重排的正文。
- `notes/<id>/document.json`：章节、组件、阅读块、Pandoc AST 与来源信息。
- `notes/<id>/report.json`：转换版本、源文件/PDF/图片/HTML 哈希和计数。
- `data/web-notes-report.json`：全部候选条目的通过或阻断原因。

目录仅为通过的条目写入 `web` 字段。阻断时清理该条目的网页输出，PDF 继续保留。浏览器也核验 HTML 哈希；资源版本不一致时提供原版 PDF 入口。

## 必须通过的检查

- 已审阅源文件、PDF 和图片哈希一致，路径不得越界或经过符号链接。
- 未知 raw TeX、文件读取/写入命令或执行类命令阻断转换。
- 标题层级、图片、提示框、表格、公式、时间字符串计数符合 profile。
- 所有视频时间字符串保持一致，图注与时间区间一对一；图片存在且格式受支持。
- AST 的文字与代码可在输出正文中找到；MathML 保留原 TeX annotation，无 merror。
- 内部引用有效；输出无脚本、嵌入框架、事件属性或不允许的链接协议。
- 桌面与手机运行目录、图片放大、缩放、搜索、位置恢复和异常回退测试。

以上检查帮助发现内容丢失，不替代数学正确性或讲义事实核查。新增复杂宏必须补充适配和负对照测试；不能把未知片段直接删除以获得通过。

## 构建

本地需要 Pandoc、BeautifulSoup4、ImageMagick 和原有 PDF 工具；Node.js 满足 pdfjs-dist 的版本要求。执行 `npm ci` 后使用 `scripts/build_site.py` 或原有容器构建脚本。CI 的隔离容器内安装转换依赖，保持无网络、只读输入和资源限制。`npm run test:e2e` 覆盖 Chromium 桌面/移动及 WebKit 桌面。

外部 PDF 投稿方式不变。网页转换仅从维护者已纳入课程 manifest 的源材料生成，不新增任意 TeX 在线上传或执行入口。

## 为新讲义准备待审阅 profile

```bash
python3 -m scripts.web_notes --course content/courses/nju-gse-2026/course.json --file nju_gse_2026_03_repository_management_zh.pdf --tex source/lecture03/notes.tex --output .tmp/lecture03-profile-review.json
```

该命令生成 `needs_review` 候选，不写入 manifest，不发布 HTML。维护者对照源文件和 PDF 审阅组件数量、图文与公式后，才将 `web_source` 内容纳入课程 manifest。构建时再次验证哈希与语义检查。
