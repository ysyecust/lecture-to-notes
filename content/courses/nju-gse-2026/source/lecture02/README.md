# 第 2 讲源文件与质量证据

本目录对应《生成式软件工程》2026 第 2 讲“提示词工程”。最终 PDF 位于课程目录根部：
`nju_gse_2026_02_prompt_context_engineering_zh.pdf`。

- `notes.tex`：可编辑讲义源文件。
- `audio_x_asr_raw.srt` / `audio_corrected.srt`：本地 X ASR 原始与保守校订字幕；Bilibili 页面未暴露字幕轨。
- `figures/`：从每 15 秒画面中筛选并逐张核对的 39 张证据图。原视频把黑板摄像头和课件拼在同一画面里；v1.0.1 起每张图只保留课件区（`layout.json` 在 1/15s 密集帧上测得 `[546,0,1280,410]`，裁剪向内收 5 px）。图 23 另附同一时刻的板书 `fig_023_context_competes_attention_board.jpg`。
- `figure_manifest.tsv` / `figure_verification.txt`：画面、时间戳与字幕上下文映射；`panel` 列记录每张图保留的区域（`main` 为课件，`left` 为板书）。
- `lecture_profile.json` / `teaching_atoms.tsv` / `numerical_claims.tsv`：密度目标与内容覆盖审计。
- `quality/`：v1.0.1 重新编译后的 37 页视觉联系表与选图联系表。
- `compile_report.json` / `quality_report.json` / `visual_qa_report.json`：编译、内容密度和逐页视觉验收结果，已按 v1.0.1 的 PDF 更新页数。
- `release_report.json`：2026-09-11 首次发布（28 页、配图为完整拼接画面）时的站点构建与测试记录，保留作历史记录。

课程主页可确认课程安排，但制作时尚未提供本讲可独立下载的官方课件或逐字字幕；后续若官方材料发布，应以原视频时间轴和本目录清单进行增量核对。
