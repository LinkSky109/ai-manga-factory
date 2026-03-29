# 图生视频冒烟验证

- 时间：2026-03-19 23:12:34 +08:00
- 适配包：`dpcq_ch1_20`
- 关键帧来源：`job_21/chapter_01/images/keyframe_01.png`
- 输出视频：`data/provider_test_i2v.mp4`
- 提供方：Ark
- 模型：`doubao-seedance-1-5-pro-251215`
- 内容模式：`image_to_video_first_frame`
- 时长：`5s`
- 比例：`16:9`
- 分辨率：`720p`
- `return_last_frame`：`true`
- `generate_audio`：`false`
- `completion_tokens`：`108900`

结论：这次实测确认章节关键帧已经可以按“首帧图生视频”方式发给 Ark，而不是退回文本生视频。
