# IndexTTS 后端

通用能力定义在 `backends/config/media_backends.yaml`，实际运行时、模型与 Python 路径登记在作者和部署档案。默认本地 JS 画面无需 GPU；有授权参考声线时单独配置本机 IndexTTS，不要求远端 4090。

`setup_mac.sh` 用于按需重建 Apple Silicon 环境。它固定已验收的 IndexTTS 源码 commit，通过 `INDEXTTS_REMOTE_HOST` 与 `INDEXTTS_REMOTE_MODEL_ROOT` 指定权重源，再经局域网 `rsync` 复制；不内置某位用户的主机地址。使用 `--skip-models` 可只安装运行时。机器路径、缓存位置和测试回执记录在 `docs/local/`，不进入通用能力合同。

本地生成需要在部署档案中登记 `indextts_local_mac`，并准备独立 Python/PyTorch 环境和模型权重。作者档案存在授权参考音频时，IndexTTS 是默认优先路径；Edge TTS 只作为没有声线基线时的保底，不替代作者声线。具体选择仍由 `policy.default_audio` 和作者档案共同决定。

## 首次准备与验收

Apple Silicon 可执行 `bash backends/indextts/setup_mac.sh --skip-models`，脚本使用 uv 管理独立 Python 3.11 环境。随后按已锁定上游版本要求准备完整模型与缓存；只有配置了自己可访问的 `INDEXTTS_REMOTE_HOST` / `INDEXTTS_REMOTE_MODEL_ROOT` 时，才去掉 `--skip-models` 进行 LAN 复制。该脚本目前不提供全平台权重一键下载，不能将“运行时安装完成”显示为“语音可用”。

作者档案设置 `voice.reference_audio`、`voice.preferred_backend_definition: indextts_2_5`；有多个同类实例时显式设置 `voice.backend`。部署实例登记 `root`、`model_root`、`python`、设备并将 `policy.default_audio` 指向自己的本机实例。先用同一参考音频和固定情绪参数合成短段，核对解码、时长、医学名词、语气和声音授权，再整篇制作。全篇保持相同参考音频和参数；`audio_baseline` 不能代替完整审听。
