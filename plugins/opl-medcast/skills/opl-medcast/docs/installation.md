# 安装与环境准备

通过已支持此软件包的 OPL Framework 安装：

```bash
opl packages install opl-medcast --json
opl packages status --package-id opl-medcast --json
```

OPL 通过 `ghcr.io/gaofeng21cn/one-person-lab-packages/opl-medcast:latest-stable` 解析当前版本，校验发布内容，并交给原生插件管理器安装。插件选择器为 opl-medcast@opl-medcast。安装后在新任务中使用 OPL Med Cast。

软件包发布以 OCI 为准，GitHub Release 页面不是安装前提。源码仓库和版本标签用于开发与追溯；常规安装不需要手动下载 ZIP、添加 Git 市场或执行本仓打包脚本。

## 运行环境

只读辅助程序需要 Python 3.10 或更新版本及 PyYAML。为源码开发建立独立环境的示例：

```bash
python3 -m venv .venv
.venv/bin/python -m pip install 'PyYAML>=6,<7'
.venv/bin/python runtime/native_helpers/medcast.py --help
```

随包辅助程序位于技能目录中的 runtime/native_helpers/medcast.py。实际视频生成、剪辑和打包需要已配置的制作工作区及可用媒体后端。原始媒体、后端凭据和本机恢复档案留在制作工作区。

安装、运行可用性、完整视听与医学复核分别验收，具体边界见[版本状态](status.md)。
