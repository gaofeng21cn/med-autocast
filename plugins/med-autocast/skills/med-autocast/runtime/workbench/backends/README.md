# 媒体后端目录

这里保存视频和音频后端的可移植能力定义与可复现部署入口，不保存凭据、模型权重、运行输出或某台机器的私有路径。

## 目录职责

```text
backends/
├── config/media_backends.yaml  # 通用能力与供应商协议目录
├── h3/                         # H3 的 RTX 4090 与 Apple Silicon 部署包
└── indextts/                   # IndexTTS 的平台安装入口
```

- 编排代码合并 `config/media_backends.yaml` 与 `workbench.yaml` 选中的 `profiles/backends/<id>.yaml`；前者持有通用能力，后者持有当前部署实例和默认值。
- `h3/` 和 `indextts/` 负责安装与启动实现；镜头职责、医学内容和视觉验收由 `docs/`、`content/` 与 `productions/` 的各自负责人决定。
- `indextts/setup_mac.sh` 从显式配置的局域网主机复制权重，避免重复互联网下载；主机与模型目录通过 `INDEXTTS_REMOTE_HOST`、`INDEXTTS_REMOTE_MODEL_ROOT` 指定，`--skip-models` 仅安装运行时。
- endpoint、模型目录和凭据环境变量在部署档案中指定。设备实测、NAS 挂载和临时状态只写入 `docs/local/`。
- 当前 `example_deployment` 部署档案保留 RTX 4090 作为默认视频和音频路径；这是本机实例配置，不是通用能力合同。
- 云视频供应商由用户配置 endpoint 和专用凭据，工作台按供应商真实协议提供调用适配；当前已登记 MiniMax 官方 H3 与 APIYI Seedance 2.5，均不要求经 OPL Gateway 中转。供应商合同和状态见 `docs/08_云视频API接入.md`。

## 标准入口

```bash
python3 scripts/media_backend.py list --pretty
python3 scripts/media_backend.py resolve --media video --pretty
python3 scripts/media_backend.py doctor --pretty
python3 scripts/workbench_config.py validate --pretty
```

能力定义见 `docs/05_多后端本地与远程运行.md`，日常生产顺序见 `docs/06_媒体后端运行SOP.md`，H3 部署细节见 `backends/h3/README.md`。
