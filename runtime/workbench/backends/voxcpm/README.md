# VoxCPM2 旁白后端

授权参考声线的医学科普旁白使用登记的 VoxCPM2；具体计算设备由部署档案登记。模型和 Python 环境由部署档案登记，统一入口是 `scripts/render_narration.py`；MAC 通过 `scripts/environment_check.py` 和 `scripts/media_backend.py doctor` 检查运行时、模型文件和参考音频。

模型根目录、独立 Python、设备和运行参数由部署档案登记。当前推荐 profile 使用 `optimize=false`、`inference_timesteps=10`；具体性能、内存和缓存策略以对应部署实测为准。

VoxCPM2 通过括号式风格指令实现“条理讲解”，同一作者和整篇旁白固定参考音频与指令。上游示例还支持原生音素输入：中文用大括号包住带声调拼音，例如 `{ni3}{hao3}`（见 [官方示例](https://github.com/OpenBMB/VoxCPM/blob/main/app_old.py#L185-L189)）。工作台继续用可读的 `<文字|拼音>` 编辑标记，合成前自动把它转换为 VoxCPM2 的 `model_text`（例如 `<还|HAI2>` → `{hai2}`）；字幕和正文仍使用审定中文。带控制标记的声段会保持 `pronunciation_review: pending` 并要求人工完整听辨，不能用 ASR、输入标签或响度结果替代实际读音验收。

当前统一入口保持 `normalize=false`，以免外部文本正则化破坏大括号音素。`j/q/x` 后的旧式 `v` 会归一化为标准 `u`（如 `XVE4` → `{xue4}`），`lü/nü` 仍用 ASCII `v` 表示 `ü`。拼音格式不合法会在模型启动前拒绝该声段，避免把错误控制静默当作普通中文合成。

每批合成只编码一次参考录音并复用 prompt cache；运行时内存参数在导入推理库前设置，整轨时码按实际采样数计算。缓存绑定 worker 哈希、运行包 metadata、模型配置和权重文件身份，更新后不能复用不匹配的缓存。英文可用 CMU 音素控制（如 `<hello|HH AH0 L OW1>` → `{HH AH0 L OW1}`），也须审听。

数字和单位也可保留正文并标中文读音，如 `<5mg|WU3 HAO2 KE4>`；仍按语境确定读法和人工听辨。
