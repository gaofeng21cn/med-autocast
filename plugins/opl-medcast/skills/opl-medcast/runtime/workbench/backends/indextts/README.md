# IndexTTS 后端

当前 `example_deployment` 部署档案的正式旁白默认在 `configured-workstation` 的 RTX 4090/CUDA 环境生成。通用 IndexTTS 能力定义在 `backends/config/media_backends.yaml`，当前主机和路径在 `profiles/backends/example_deployment.yaml`，不在本目录复制凭据。

`setup_mac.sh` 用于按需重建 Apple Silicon 环境。它固定已验收的 IndexTTS 源码 commit，通过 `INDEXTTS_REMOTE_HOST` 与 `INDEXTTS_REMOTE_MODEL_ROOT` 指定权重源，再经局域网 `rsync` 复制；不内置某位用户的主机地址。使用 `--skip-models` 可只安装运行时。机器路径、缓存位置和测试回执记录在 `docs/local/`，不进入通用能力合同。

本地生成仍需显式选择 `indextts_local_mac`，不会改变 `policy.default_audio=indextts_remote_4090`。
