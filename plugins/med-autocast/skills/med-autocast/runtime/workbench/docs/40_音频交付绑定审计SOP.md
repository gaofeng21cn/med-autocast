# 音频交付绑定审计 SOP

## 目的

旁白声段修复后，必须确认修复后的声音实际进入混音、渲染和用户交付。`scripts/audit_audio_delivery_binding.py` 是只读诊断工具，按集输出五层绑定状态：

1. `source.bound`：声段文件、无损拼接整轨及 `narration_splice/v2` 回执一致。
2. `timing_bound`：字幕/镜头时间回执同时绑定当前旁白与当前 Score。
3. `mix_bound`：混音回执同时绑定当前旁白、Score 和 `audio.wav`。
4. `render_bound`：`out/current.json` 绑定当前 bundle、Score、音频和实际 MP4。
5. `publish_bound`：用户目录 `video.mp4` 与当前渲染 MP4 字节一致。

`stale_publish=true` 表示用户交付仍是旧 MP4、缺失或与当前渲染不一致。它是返修信号，不是旁白发音或段首丢字的结论。

## 使用

```bash
python scripts/audit_audio_delivery_binding.py \
  --workspace . \
  --output work/audio-delivery-binding.json
```

可以用 `--series` 和 `--episode` 缩小范围。输出中的 `issues` 保留具体断点；工具只读，不修改项目、不阻断后续 Stage。

## 修复顺序

对于 `source` 已更新但下游未绑定的集，按实际项目执行：

```text
retime -> build -> mix -> render -> package -> publish readback
```

每一步完成后重新读取对应回执；不可用旧的 `audio.wav`、旧 `current.json` 或旧发布 MP4 代替当前输入。对源声段的完整性，使用 `audit_narration_lineage.py` 的局部多锚点审计；它只能证明波形血缘，不能代替正常速度完整听辨、术语发音、语气一致性或医学终审。

## 状态边界

`publish_fresh` 只表示结构和字节绑定新鲜，不表示可公开发布。`attention_required` 记录可继续推进的质量债，不把机器检查写成语义通过。正式发布仍需独立完成视觉连续观看、完整听感、发音/语气审听和医学审核。
