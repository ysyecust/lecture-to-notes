# 课程图书馆与仓库内 PDF 贡献设计

日期：2026-07-16
状态：待用户书面确认

## 1. 目标

本次改造把现有的“平铺 PDF 卡片 + 弹窗 iframe”升级为两层静态课程图书馆：

1. 首页按课程系列组织资料，支持课程、讲次和主题搜索。
2. 每份讲义拥有独立、可分享的阅读页，提供同课程讲次切换、直接打开、下载和原视频入口。
3. 立即发布 Stanford CS336 Spring 2026 前三讲及 94 页合集。
4. 把当前仓库作为唯一内容仓库。用户通过 fork/PR 只提交 PDF，自动化从 PDF 提取标题、页数和首屏缩略图。
5. 在本地验证通过后合并贡献者的 LaTeX 依赖修复 PR #4，并为后续课程资料贡献留下清晰入口。

## 2. 本轮不做的内容

- 不建设独立素材仓库、submodule、账户系统、对象存储、数据库或公开写入 API。
- PR 未合并前，PDF 不进入生产站点；自动化不会绕过维护者审核或自动合并 PR。
- 不在阅读页引入完整 PDF.js 阅读器；阅读仍使用浏览器原生 PDF 能力。
- 不自动导入 Issue #5 中声称的 CS336 Spring 2025 全 17 讲。其外部仓库当前不可访问，必须等贡献者提供可验证文件或 PR。
- 不改动仓库中已有的用户未跟踪文件。

## 3. 当前约束与依据

- 站点由 GitHub Pages 从 `main/docs` 发布，是纯静态站点，没有接收文件的后端。
- 当前课程和论文元数据硬编码在 `docs/index.html` 的 `DATA` 数组中，内容增长后不利于课程分组、验证和贡献。
- 当前 PDF 在模态框 iframe 中打开，缺少稳定 URL、课程导航、直接打开和清晰的移动端兜底。
- GitHub Pages 证书已批准，但尚未启用强制 HTTPS。
- PR #4 可合并，但分支没有 CI 检查，需要维护者本地验证。
- 仓库当前约 176 MiB，其中 30 份已跟踪 PDF 约 148 MiB。GitHub 网页上传单文件上限为 25 MiB，普通 Git 对大于 50 MiB 的文件发出警告，并阻止超过 100 MiB 的文件；本项目采用更严格的 25 MiB 贡献上限以保持网页 PR 路径可用。

## 4. 信息架构

### 4.1 课程图书馆首页

首页承担发现和导航，不再把每份 PDF 当作无层级的独立卡片。主要区域为：

- 顶部导航：课程、论文、贡献 PDF、GitHub。
- 课程搜索：按课程名、讲次标题、讲师和标签过滤。
- 课程系列卡片：显示学校/来源、学期、讲次数、总页数、更新状态和讲次刻度。
- 课程详情视图：仍在首页应用壳内，通过 URL hash 打开某一课程的讲次列表。
- 论文内容保留独立分类和原有 HTML 链接。

### 4.2 独立阅读页

`reader.html?id=<lecture-id>` 从目录中查找讲义，不接受任意外部 PDF URL。

- 左侧：课程名称、学期、讲次列表和合集入口。
- 主区：浏览器原生 PDF 嵌入。
- 工具栏：当前标题和页数、适合宽度提示、直接打开、下载、原视频。
- 移动端：隐藏固定侧栏，使用讲次选择器；始终显示“直接打开 PDF”和“下载”兜底。
- 无效 ID 或缺失 PDF：显示明确错误、返回课程库和可用讲次，不展示空白 iframe。

## 5. 仓库内内容模型

所有源素材放在当前仓库的 `content/` 下，站点代码仍放在 `docs/` 下。两者通过受信任的构建脚本关联，不使用嵌套仓库或 submodule。

- `content/courses/<course-id>/course.json`：维护者整理的课程名称、机构、学期、简介、标签、排序和可选合集信息。
- `content/courses/<course-id>/*.pdf`：已整理课程讲义。
- `content/inbox/*.pdf`：社区贡献入口；不要求贡献者手写元数据，默认显示在“社区贡献”系列。
- `docs/papers/`：现有论文 HTML 保持不变。

构建时生成 `_site/data/catalog.json`，作为首页、阅读页和统计的运行时数据源。目录包含 `courses` 和 `items` 两类对象；标题、页数、缩略图和稳定 ID 由构建脚本产生，课程维护信息来自受信任的 `course.json`。

约束：

- ID 全局唯一且稳定，使用课程 ID、文件名规范化结果和内容哈希前缀生成。
- 发布 PDF 必须位于仓库内 `content/`，构建产物统一映射到 `_site/pdfs/`。
- 页数由受信任构建脚本读取，不接受贡献者手写覆盖。
- 来源 URL 只允许 `https`，现有历史链接在迁移时单独报告。
- 首页统计全部从构建目录实时计算，不保留手写数字。
- 旧的 `/pdfs/<name>.pdf` 公开 URL 在迁移后保持可用。

现有 `DATA` 内容将完整迁移到目录，现有已跟踪 PDF 和论文页面不改名。CS336 新文件采用：

- `stanford_cs336_2026_01_overview_tokenization_zh.pdf`
- `stanford_cs336_2026_02_pytorch_resource_accounting_zh.pdf`
- `stanford_cs336_2026_03_architectures_zh.pdf`
- `stanford_cs336_2026_01_03_bundle_zh.pdf`

## 6. GitHub PR 上传与自动解析

### 6.1 用户流程

1. 网站“贡献 PDF”按钮打开当前仓库 `content/inbox/` 的 GitHub 上传入口。
2. GitHub 自动为无写权限用户创建 fork/分支；用户上传 PDF、勾选权利声明并创建 PR。
3. PR 检查确认改动只新增允许路径内的 PDF，并在受限环境中提取标题、页数和首屏缩略图。
4. 检查摘要展示解析结果、安全结果和站点预览 artifact；贡献者不需要编辑目录 JSON。
5. 维护者审核并合并后，主分支构建重新扫描 `content/`，生成目录和站点并部署。未合并 PR 永远不会上线。

GitHub 网页上传路径接受每份不超过 25 MiB 的 PDF；每个 PR 最多 10 份、合计不超过 100 MiB。更大的资料不走自动贡献路径，由维护者单独评估。

### 6.2 自动解析

受信任脚本对每份 PDF 生成：

- 页数：读取 PDF 文档页数。
- 标题优先级：PDF metadata `Title` → 第一页上半区的高字号文本块 → 清洗后的文件名。
- 标题候选：合并同一基线附近的文本，过滤页码、孤立标点和过短内容，并在检查摘要中标注来源和置信度。
- 首屏缩略图：将第一页按受限尺寸渲染为 WebP；原 PDF 不转换、不改写。
- 稳定 ID：规范化标题或文件名加内容哈希前缀，避免重名覆盖。
- 社区归类：未提供受信任 `course.json` 的文件进入“社区贡献”系列；维护者之后可移动到正式课程目录。

### 6.3 PR 安全边界

- 只使用 `pull_request` 触发器；禁止用 `pull_request_target` 或 `workflow_run` 检出未受信任 PR 内容。
- PR 工作流显式设置 `contents: read`，不接收 secrets，不使用自托管 runner，不保留 Git 凭据。
- 工作流和校验器从 base/main 单独检出；PR 内容只挂载为只读输入，不能修改或替换校验逻辑。
- 所有第三方 Actions 固定到完整 commit SHA。
- PDF 解析在无网络、无特权、只读文件系统的临时容器中运行，并限制 CPU、内存和执行时间。
- 先执行路径 allowlist、文件数量、大小、PDF 签名和 `qpdf --check`；拒绝 JavaScript、Launch action、嵌入文件、OpenAction、RichMedia 等主动内容。
- 标题、文件名和解析错误只作为纯文本处理，禁止拼接到 shell、HTML 或 GitHub Actions 表达式。
- 首次外部贡献者的 workflow 必须由维护者检查文件差异后手动批准运行。

### 6.4 主分支发布

- GitHub Pages 从 legacy `main/docs` 切换为 GitHub Actions 自定义发布源。
- 主分支 build job 从 `docs/` 复制页面壳，扫描 `content/`，生成目录、缩略图和 PDF 映射到 `_site/`。
- deploy job 是唯一拥有 `pages: write` 与 `id-token: write` 的任务，并受 `github-pages` environment 保护。
- 构建产物通过 Pages artifact 发布；不让机器人把生成文件回写主分支，也不自动创建或批准 PR。

## 7. 视觉语言

已确认方向为 **Technical Study Desk**：

- Lab Paper `#F7FAFB`
- Blueprint `#173A50`
- Ink Blue `#2F6BFF`
- Annotation `#FF6B5B`
- Grid Line `#CCD8E0`
- 标题：Sora；中文正文与控件：Noto Sans SC；课次和页码：IBM Plex Mono。
- 唯一标志性元素：课程书脊与讲次刻度。
- 删除通用紫色渐变、巨型统计数字和分散动画；只保留一次课程进入阅读页的过渡，并尊重 `prefers-reduced-motion`。

## 8. 可访问性与响应式

- 所有导航和动作使用语义化链接或按钮，不使用仅靠点击的 `div`。
- 提供清晰焦点、跳至正文链接、键盘可用的搜索和讲次切换。
- 颜色对比达到 WCAG AA；信息不只依赖颜色。
- 贡献页说明 fork/PR 流程、25 MiB 上限和审核边界，并提供直达 `content/inbox/` 的 GitHub 按钮。
- 桌面、平板和手机使用同一目录数据；手机阅读页优先提供直接打开 PDF。

## 9. 贡献者 PR 与 Issues

### PR #4

在独立检出中运行现有测试，并验证：

- 有 `ctex` 时模板保持原行为。
- 缺少 `ctex` 时条件分支语法和字体 fallback 可用。
- 依赖检查列出的宏包与安装建议一致。

验证通过后保留贡献者提交和署名合并；若发现边界问题，先给出最小修正或在合并后追加维护者修复。Issue #3 随 PR 关闭。

### Issue #5

新增简短贡献说明，明确贡献者只需向 `content/inbox/` 提交 PDF，无需手写目录记录。由于对方提供的仓库链接当前为 404，Issue 保持开放，并请贡献者提交实际 PDF PR 或新的可访问地址。

## 10. 验证门

### 数据与文件

- 目录 JSON 可解析、ID 唯一、引用文件存在。
- `pdfinfo` 页数与目录一致，PDF 文件签名有效。
- 所有站内链接和来源 URL 通过检查。
- 首页统计值与目录聚合一致。
- 每次主分支构建报告仓库与 PDF 总体积；达到 750 MiB 时发出维护警告，但不自动迁移到其他仓库。

### 贡献 PR

- 用 fork 模拟只新增一份 CS336 PDF 的贡献 PR，核对标题、页数、缩略图、稳定 ID 和预览 artifact。
- 覆盖损坏 PDF、加密 PDF、非 PDF、超限文件、重名文件、超过数量限制和主动内容。
- 验证修改工作流/脚本、添加可执行文件或越过 `content/inbox/` 的 PR 会失败。
- 验证 fork PR 没有 secrets、token 只读，未批准运行和未合并内容均不会部署。

### 页面

- 桌面与手机截图审查首页、课程详情、阅读页和贡献页。
- 键盘导航、焦点、减弱动画和空搜索状态。
- GitHub Pages 部署后探测首页、目录、阅读页和四份 CS336 PDF。
- 线上验证通过后启用 HTTPS 强制跳转并再次探测。

## 11. 发布顺序

1. 合并并验证 PR #4。
2. 建立 `content/` 内容区并迁移现有 PDF，保留旧公开 URL。
3. 加入 CS336 三讲和合集。
4. 实现课程图书馆首页与独立阅读页。
5. 实现仓库内 PDF 贡献目录、fork-PR 校验与自动解析。
6. 实现 GitHub Actions Pages 构建和部署，增加目录/PDF/页面测试与贡献说明。
7. 创建站点改造 PR，完成安全、截图和测试审查后合并。
8. 验证 GitHub Pages 与 HTTPS。
9. 由维护者通过真实 fork/PR 上传一份 CS336 PDF，确认贡献、合并和部署闭环。

## 12. 已确认决策

- 采用“课程图书馆 + 专用阅读页”，不继续扩展模态框。
- 采用 Technical Study Desk 视觉语言。
- 当前 `lecture-to-notes` 仓库同时保存代码和全部内容素材，不建立独立素材仓库。
- GitHub fork/PR 是上传入口和审核队列；贡献者只需提交 PDF，未合并内容不发布。
- 自动解析聚焦标题，同时提供页数、首屏缩略图和主动内容检查。
- GitHub Actions 只在主分支合并后构建并部署，不持有公开写入接口或长期仓库密钥。

## 13. 官方依据

- [GitHub 大文件限制](https://docs.github.com/en/repositories/working-with-files/managing-large-files/about-large-files-on-github)
- [从 fork 运行 workflow 的权限与审批](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows)
- [GitHub Actions 安全使用参考](https://docs.github.com/en/actions/reference/security/secure-use)
- [GitHub Pages 自定义 Actions 发布](https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages)
