# 第 1 讲网页阅读源材料

本目录归档 CMU 11-768《AI Agents》第 1 讲 *What are Agents and How Do They Work?* 的 TeX、封面、配图、图注时间清单与视频元数据，用于双格式阅读构建。

- 源视频：https://www.youtube.com/watch?v=UwfjzyLnvMg （Graham Neubig / Daniel Fried，68 分钟）
- 发布版 PDF：课程根目录 `cmu_aiagents_2026_01_what_are_agents_zh.pdf`（37 页）
- 生成方式：官方自动字幕（去重后 1614 条，覆盖率 1.0）+ 1/15s 密集抽帧 + 33 张时间可溯源配图
- 配图版面（v1.0.1）：原视频把课件和摄像头拼在同一画面里。`layout.json` 由 `frame_filter.py layout` 在 1/15s 密集帧上测得课件区 `[0,120,1280,840]`；33 张配图都只保留课件区（向内收 5 px；`fig_14` 的底边不内收，保留录屏左下角浏览器的链接提示），`figure_manifest.tsv` 的 `panel` 列记为 `main`。
- 图片、TeX 与 PDF 的版本对应关系固定在课程 `course.json` 的 `web_source` 中；改动其中任何文件都必须重新审阅并更新 profile。
