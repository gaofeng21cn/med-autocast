# 媒体后端目录

这里保存视频和音频后端的可移植能力定义与可复现部署入口，不保存凭据、模型权重、运行输出或某台机器的私有路径。

## 目录职责

```text
backends/
├── config/media_backends.yaml  # 通用能力与供应商协议目录
├── h3/                         # H3 的 RTX 4090 与 Apple Silicon 部署包
└── voxcpm/                   # VoxCPM2 的平台安装入口
```

- 编排代码合并 `config/media_backends.yaml` 与 `workbench.yaml` 选中的 `profiles/backends/<id>.yaml`；前者持有通用能力，后者持有当前部署实例和默认值。
- `h3/` 和 `voxcpm/` 负责安装与启动实现；镜头职责、医学内容和视觉验收由 `docs/`、`content/` 与 `productions/` 的各自负责人决定。
- VoxCPM2 使用独立 Python 环境与完整权重，统一旁白入口自动选择登记的解释器；准备和验证见 `voxcpm/README.md`。
- endpoint、模型目录和凭据环境变量在部署档案中指定。设备实测、NAS 挂载和临时状态只写入 `docs/local/`。
- 新用户默认本地 JS 动画，未提供授权声线时使用 Edge；授权声线优先 VoxCPM2，模型视频为显式备选。具体部署默认由工作区选择。
- 云视频供应商由用户配置 endpoint 和专用凭据，工作台按供应商真实协议提供调用适配；当前已登记 MiniMax 官方 H3 与 APIYI Seedance 2.5，均不要求经 OPL Gateway 中转。供应商合同和状态见 `docs/08_云视频API接入.md`。

## 标准入口

```bash
python3 scripts/media_backend.py list --pretty
python3 scripts/media_backend.py resolve --media video --pretty
python3 scripts/media_backend.py doctor --pretty
python3 scripts/workbench_config.py validate --pretty
```

能力定义见 `docs/05_多后端本地与远程运行.md`，日常生产顺序见 `docs/06_媒体后端运行SOP.md`，H3 部署细节见 `backends/h3/README.md`。
