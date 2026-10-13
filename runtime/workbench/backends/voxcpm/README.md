# VoxCPM2 本机旁白后端

授权参考声线的医学科普旁白使用登记的 VoxCPM2；本机 Apple Silicon 部署可使用 MPS。模型和 Python 环境由部署档案登记，统一入口是 `scripts/render_narration.py`；Mac 智能体通过 `scripts/environment_check.py` 和 `scripts/media_backend.py doctor` 检查运行时、模型文件和参考音频。

本机默认路径为 `$HOME/ai/voxcpm-test`，解释器为 `.venv/bin/python`，模型目录为 `models/VoxCPM2`。也可以通过 `VOXCPM_ROOT`、`VOXCPM_PYTHON` 和 `VOXCPM_MODEL_ROOT` 覆盖。运行时使用 MPS、`load_denoiser=false`、`optimize=false`、`inference_timesteps=10`，每段生成后释放 MPS 缓存，避免长批次把前一段的显存占用带入下一段。

VoxCPM2 通过括号式风格指令实现“条理讲解”，同一作者和整篇旁白固定参考音频与指令。上游示例还支持原生音素输入：中文用大括号包住带声调拼音，例如 `{ni3}{hao3}`（见 [官方示例](https://github.com/OpenBMB/VoxCPM/blob/main/app_old.py#L185-L189)）。工作台继续用可读的 `<文字|拼音>` 编辑标记，合成前自动把它转换为 VoxCPM2 的 `model_text`（例如 `<还|HAI2>` → `{hai2}`）；字幕和正文仍使用审定中文。带控制标记的声段会保持 `pronunciation_review: pending` 并要求人工完整听辨，不能用 ASR、输入标签或响度结果替代实际读音验收。

当前统一入口保持 `normalize=false`，以免外部文本正则化破坏大括号音素。`j/q/x` 后的旧式 `v` 会归一化为标准 `u`（如 `XVE4` → `{xue4}`），`lü/nü` 仍用 ASCII `v` 表示 `ü`。拼音格式不合法会在模型启动前拒绝该声段，避免把错误控制静默当作普通中文合成。

VoxCPM2 已从当前能力目录、部署档案和 Mac 智能体生产路径移除。旧交付物中的 VoxCPM2 文件和回执只作为历史事实保留。

每批合成只编码一次参考录音并复用官方 prompt cache，MPS 水位参数在导入 Torch 前设置；整轨时码按实际 24kHz 采样数计算。缓存绑定 worker 哈希、运行包 metadata、模型配置和权重文件身份，更新后不能复用不匹配的缓存。英文可用 CMU 音素控制（如 `<hello|HH AH0 L OW1>` → `{HH AH0 L OW1}`），也须审听。

数字和单位也可保留正文并标中文读音，如 `<5mg|WU3 HAO2 KE4>`；仍按语境确定读法和人工听辨。
