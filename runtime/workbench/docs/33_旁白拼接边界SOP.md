# 旁白拼接边界 SOP

分段配音的每一段都是独立 take。TTS 输出常带不等量的前导静音，直接按固定偏移首尾相接，会把这段静音叠在设计好的停顿上。结果是每次切段之后观众听到一段不该有的空白，随后第一个字已经过去——听起来就像“丢了两个字”。

## 真实故障

2026-10-12，11 个系列 172 个工程中 137 个受影响，且每集的每一个 beat 都中招。这不是个别 take 的问题，是拼接方式的系统缺陷。

`render_narration.py` 原来这样拼：

```python
cursor = 0.65
for b in records:
    b["start"] = cursor
    cursor = b["end"] + 0.65
    pcm.extend([data, b"\0" * round(rate * 0.65) * 2])
```

固定 0.65 秒 + take 自带 0.3–0.5 秒前导静音 = 实际 0.95–1.15 秒空白。垂体瘤 09 的 B03 实测前导静音 0.37 秒，频谱图显示 0.78 秒近全静音后才出现语音，且首字没有爆破音渐入，说明“经”“具”这类清辅音开头被完全吞掉。

## 修复

`scripts/narration_splice.py` 按实测语音边界拼接：

1. 逐 take 计算 10ms 窗 RMS 包络，用峰值 6% 作阈值定位真实语音起止。
2. 裁掉前导与尾部静音，但**保留 40ms 前沿与 90ms 尾部**：切到能量边缘会削掉爆破音的瞬态，那是同一个缺陷的另一个方向。
3. 拼接时把裁掉的静音还给停顿，并按 `total_seconds` 精确配平，保证成片时长不变。

关键约束：**修复不能改变成片时长**。第一次尝试直接把停顿缩到 260ms，音轨短了约 10 秒，字幕和镜头全部错位——137 个集音画失配。这比原缺陷更严重，已回滚。

现在的做法是：`available = total_seconds - speech_total - overhead`，平均分给每个间隙。校验 175 个工程，音画时长误差全部小于 0.5 秒。

## 工具

```sh
# 扫描：哪些集的前导静音超过阈值
python3 scripts/scan_narration_boundaries.py --root productions

# 修复：重拼 narration.wav 与 narration-normalized.wav
python3 scripts/scan_narration_boundaries.py --root productions --apply
python3 scripts/scan_narration_boundaries.py --root productions --repair-normalized

# 重渲染受影响的集（retime → build → mix → render，可中断续跑）
python3 scripts/rerender_spliced_episodes.py --workspace . --minutes 25
```

`rerender_spliced_episodes.py` 依据旁白指纹判断是否已是当前版本；只做音频改动时必须依次重跑 retime、build、mix、render，缺一步会被现有门拦下。

## 为什么机器检查此前没有发现

时长对、响度对、LUFS 对、解码正常。一个晚 0.4 秒开始的 take 完全满足这些检查。

检测必须看**语音起点**，不是看文件起点：测 take 的 head silence，或看拼接后音轨里每个 beat 起点前后的能量。`scan_narration_boundaries.py` 输出的 `head_silence` 与 `splice.takes` 就是这个证据。

## 检查清单

- 每段 take 的前导静音是否在听辨可接受的范围内（中文短句建议 < 0.08 秒）。
- 拼接后停顿是否听得见完整首字，特别是以“经”“具”“特”“此”开头的中文。
- 修复后成片总时长是否与 score 一致；不一致先 retime 再 mix。
- 修音轨不动字幕断句；重配音才动字幕。

机器测量只证明边界在哪里。是否听得自然仍需完整听辨，`pronunciation-review.json` 的 `full_listening` 保持 pending 直到实际听过。
