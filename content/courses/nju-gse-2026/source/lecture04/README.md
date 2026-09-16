# 第 4 讲网页阅读源材料

本目录归档《软件仓库管理（二）》的 TeX、封面、配图、图注时间清单、字幕与生成过程记录，用于 PDF 与 HTML 双格式阅读构建。

- 视频：《软件仓库管理 (2)》，B 站 BV1Q6en6NEUo，蒋炎岩，约 98 分钟，2026-09-15 发布。
- 字幕：视频没有人工或自动字幕轨道。ocr_hardsubs.py detect 在底部区域报告 has_hardsubs=true，但抽查显示该区域是课件正文与静态水印而非字幕，10% / 50% / 90% 语义核对无法与语音对齐，因此按 Stage 3b 使用本地 ASR：mlx-whisper large-v3-turbo，2943 段，清理空段与超出时长的尾段后 2911 段，check_srt_health.py 通过（coverage 1.0）。screen_text.srt 是整帧 0.2 fps 的 OCR 文本，供无图像输入的主机选图使用。
- 画面：1280x410 的摄像头加课件复合画面。layout.json 在 1/15 s 密集帧上测得课件区 [548,0,1280,410]、摄像头区 [0,0,548,410]，consistency 1.0，无异常帧。按 v1.0.1 范式，每张配图只保留 main 课件区，向内收 5 px，输出 727x410；figure_manifest.tsv 的 panel 列记录这一选择。摄像头区没有可判读的板书增补，且本机 vision=no，因此没有为配图附加板书面板。
- 配图：35 张，全部来自课件区；figure_verification.txt 记录每个时间点与字幕的对照。
- 数值：numerical_claims.tsv 的 20 条声明全部在正文中出现。
- 校验：verify_notes.txt 以 OVERALL PASS 结束。
