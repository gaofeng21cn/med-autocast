# 安装与环境准备

0.1.0 通过 GitHub Release分发源码与 Codex 插件。市场名称与插件名称均为 opl-medcast，选择器固定为 opl-medcast@opl-medcast。需要支持插件市场的 Codex CLI。

```bash
codex plugin marketplace add gaofeng21cn/opl-medcast --ref v0.1.0 --json
codex plugin add opl-medcast@opl-medcast --json
```

也可以下载 opl-medcast-0.1.0-codex-plugin.zip，解压后在含有 .agents 和 plugins 的目录执行：

```bash
codex plugin marketplace add "$(pwd -P)" --json
codex plugin add opl-medcast@opl-medcast --json
```

两种方式使用同一个市场名称，选择一种即可。插件方法在新任务中加载。此安装不会登记 OPL 托管领域、触发媒体生成或导入私人素材。完整软件包资格与激活状态见[版本状态](status.md)。

## 辅助程序

只读辅助程序需要 Python 3.10 或更新版本及 PyYAML。建议为源码副本建立独立环境：

```bash
python3 -m venv .venv
.venv/bin/python -m pip install 'PyYAML>=6,<7'
.venv/bin/python runtime/native_helpers/medcast.py --help
```

下载包中的辅助程序位于 plugins/opl-medcast/skills/opl-medcast/runtime/native_helpers/medcast.py；源码包中的路径为 runtime/native_helpers/medcast.py。使用与安装依赖相同的 Python 解释器，并显式传入制作工作区绝对路径。辅助程序不依赖维护者的 Framework 快照。

## 包完整性

SHA256SUMS 列出本版本两个下载包的校验值。在同一下载目录执行 shasum -a 256 -c SHA256SUMS。原始媒体、本机后端配置、凭据和恢复记录不随包分发。
