# 第 6 讲网页阅读源材料

本目录归档《需求和架构（一）》的 TeX、封面、配图、图注时间清单、字幕与生成过程记录，用于 PDF 与 HTML 双格式阅读构建。

- 视频：《需求和架构 (1)》，B 站 BV1Rch76WEfQ，蒋炎岩，约 97 分钟（5810 s），2026-09-22 发布。
- 字幕：视频没有人工或自动字幕轨道。ocr_hardsubs.py detect 报告 has_hardsubs=true，但查看画面后确认底部区域是课件正文与板书而非字幕（误报，与第 4 讲相同），因此按 Stage 3b 使用本地 ASR：mlx-whisper large-v3-turbo 加课程术语提示（whisper_prompt_gse.txt），原始输出 2875 段（audio_raw_whisper.srt）。fix_asr_loops.py 修复了两处重复循环：00:07:00–00:07:24 的 12 条重复句用 410–450 s 片段重新转写（condition_on_previous_text=False）替换；01:36:50 之后超出音频结尾的重复句删除；同时去掉空段。最终 2760 段，check_srt_health.py 通过（coverage 1.0，health.txt）。10% / 50% / 90% 语义抽查（09:41、48:25、1:27:09）与画面课件内容一致。screen_text.srt 是整帧 0.2 fps 的 OCR 文本，仅作检索用。
- 画面：1280x410 的摄像头加课件复合画面。layout.json 在 1/15 s 密集帧上测得课件区 main [546,0,1280,410]、摄像头区 left [0,0,546,410]，consistency 1.0，无异常帧。本讲主机可读图（vision=yes），逐帧看过候选画面。与第 4 讲不同，本讲的黑板板书补充了课件内容，因此 5 张图把课件区（729x410）与同时刻或相邻时刻的板书区（541x410）上下叠放；其余配图只保留 main 课件区。figure_manifest.tsv 的 panel 列逐行记录选择。由于 bands.json 的字幕带是误报，裁图没有应用底部裁切。
- 配图：45 个图像文件（40 张课件区 + 5 张板书区），figure_verification.txt 记录每个时间点与字幕的对照。
- 数值：numerical_claims.tsv 的 25 条声明全部在正文中出现。
- 校验：verify_notes.txt 以 OVERALL PASS 结束。
