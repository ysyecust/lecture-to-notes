# 第 5 讲网页阅读源材料

本目录归档《软件工程的来龙去脉》的 TeX、封面、配图、图注时间清单、字幕与生成过程记录，用于 PDF 与 HTML 双格式阅读构建。

- 视频：《软件工程的来龙去脉 [05-Raw/26生成式软件工程/NJU]》，B 站 BV1Nyeq6qEt8，蒋炎岩，约 100 分钟（5999 s），2026-09-20 发布。
- 字幕：视频没有人工或自动字幕轨道（未登录状态下 yt-dlp 报告无字幕）。ocr_hardsubs.py detect 在底部区域报告 has_hardsubs=true（12 帧中 11 帧命中），但查看 f_0100 等帧确认该区域是课件正文与静态水印而非字幕，因此按 Stage 3b 使用本地 ASR：mlx-whisper large-v3-turbo，课程术语表作 initial prompt（whisper_prompt_gse.txt），原始输出 2955 段（audio_raw_whisper.srt）。原始输出在 00:40:41–00:41:14 与 00:51:32–00:51:45 有两处复读幻觉，这两段以 condition_on_previous_text=False 单独重转并拼回，清理空段后 2884 段；check_srt_health.py 通过（coverage 0.99994）。10% / 50% / 90% 抽查与画面一致（Bitter Lesson、软件工程的智慧、Eiffel 契约）。audio_corrected.srt 用 glossary_gse05.json（28 条，60 处命中）做词表修正，例如 JAB→Jev、Humpo→Harmful、Dextra→Dijkstra。screen_text.srt 是整帧 0.2 fps 的 OCR 文本。
- 画面：1280x410 的摄像头加课件复合画面。layout.json 在 1/15 s 密集帧上测得课件区 [548,0,1280,410]、摄像头区 [0,0,548,410]，consistency 1.0，无异常帧。本机这次可以读图（vision=yes），配图经 contact sheet 与全分辨率裁图人工核对。课件配图只保留 main 课件区，向内收 5 px，输出 727x410；另有 1 张板书配图取 left 摄像头区（543x410），记录 traceability 讨论时的板书。figure_manifest.tsv 的 panel 列记录这一选择。bands.json 是 detect 的原始几何输出；由于底部字幕带是误报，裁图没有使用它。
- 配图：43 张（42 张课件区 + 1 张板书区）；figure_verification.txt 记录每个时间点与字幕的对照。
- 数值：numerical_claims.tsv 的 52 条声明全部在正文中出现。
- 校验：verify_notes.txt 以 OVERALL PASS 结束。
