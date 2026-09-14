# 第 2 讲网页阅读源材料

本目录归档 CMU 11-768《AI Agents》第 2 讲 *Tool Use for Language Model Agents* 的 TeX、封面、配图、图注时间清单与视频元数据，用于双格式阅读构建。

- 源视频：https://www.youtube.com/watch?v=jXChFB4JSyw （Graham Neubig，57 分钟）
- 发布版 PDF：课程根目录 `cmu_aiagents_2026_02_tool_use_zh.pdf`（34 页）
- 生成方式：官方自动字幕（去重后 1302 条，覆盖率 1.0）+ 1/15s 密集抽帧 + 33 张时间可溯源配图
- 配图版面（v1.0.1）：原视频把课件和摄像头拼在同一画面里。重新下载视频时 YouTube 连续 4 次返回 HTTP 403，因此 `layout.json` 改在已发布的 33 张完整画面上测得（先补回裁掉的底部 120 px 黑边）：课件区 `[0,120,1280,840]`，与第 1、3、4 讲在密集帧上测得的位置相同。33 张配图都只保留课件区（向内收 5 px），`figure_manifest.tsv` 的 `panel` 列记为 `main`。
- 图片、TeX 与 PDF 的版本对应关系固定在课程 `course.json` 的 `web_source` 中；改动其中任何文件都必须重新审阅并更新 profile。
