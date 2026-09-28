# 安装与环境准备

通过已支持此软件包的 OPL Framework 安装：

```bash
opl packages install med-autocast --json
opl packages status --package-id med-autocast --json
```

OPL 通过 `ghcr.io/gaofeng21cn/one-person-lab-packages/med-autocast:latest-stable` 解析当前版本，校验发布内容，并交给原生插件管理器安装。插件选择器为 med-autocast@med-autocast。安装后在新任务中使用 Med Auto Cast。

软件包发布以 OCI 为准，GitHub Release 页面不是安装前提。源码仓库和版本标签用于开发与追溯；常规安装不需要手动下载 ZIP、添加 Git 市场或执行本仓打包脚本。

## 首次准备

插件安装和媒体运行环境分别准备。向 Med Auto Cast 说“在指定目录准备本地医学视频工作台”即可让智能体使用随包入口；不需要用户自行组织模板和依赖。下面的命令相对 Med Auto Cast 源码根或安装后的 Skill 根，制作目录必须是新目录或空目录：

```bash
# macOS 首次缺少系统工具时安装；已有工具可跳过
brew install python node ffmpeg imagemagick
bash runtime/workbench/scripts/setup_workbench.sh --workspace "$HOME/MedAutoCastWorkspace"
```

脚本初始化通用代码和有效配置，在制作目录创建独立 `.venv`，安装核心 Python 包、锁定版本的 Playwright 与 Chromium，并实际启动浏览器检查 Canvas。中文字体优先使用配置，再发现系统中文字体；缺字体时会给出修复提示。不会安装到插件缓存，不覆盖已有作品和专用代码，不下载 IndexTTS/H3 权重，不修改已登记作者声线。

新工作区使用“尚未设定身份、不露脸、无头像”的技术初始档案，视觉默认 hand-drawn collage。它不冒充任何医生，作者基线各项保持 pending。开始正式制作前，智能体先确定医生/作者形象与声音：有授权参考音频用登记的 IndexTTS；未提供声线或主动选择跳过时使用 Edge XiaoyiNeural。已有声线但 IndexTTS 不可用时明确报缺项，不静默改用 Edge。用户主动跳过时执行 `.venv/bin/python scripts/configure_voice.py --mode edge`，保留参考音频；恢复时用 `--mode reference`。

## 最小需求与可选能力

| 范围 | 需求 | 是否联网 |
| --- | --- | --- |
| 默认 JS 制作核心 | Python 3.11+、PyYAML、Pillow、Node.js 20+（推荐 LTS）、FFmpeg/ffprobe、ImageMagick、Playwright Chromium、中文字体 | 首次安装下载；素材齐备后本机渲染可离线 |
| 无专用声线的保底 | 安装脚本包含 edge-tts；默认 zh-CN-XiaoyiNeural | 合成需要微软在线服务，安装成功不证明服务可用 |
| 自有声线／Dr.咩 | 授权参考音频、独立 IndexTTS 环境与模型、固定表达参数 | 权重齐备后可在本机推理；首次须短音频实测 |
| 自动字幕对齐 | requirements-alignment.txt、Whisper 模型 | 模型首次下载；随后本机执行 |
| 新插画素材 | 会话 ImageGen 能力或授权网络资源；透明底分层素材 | 按来源需要联网，也可复用本地已审资产 |
| 视频模型、NAS、远端 GPU | 显式选用时配置 | 均不属于核心安装条件 |

JS 渲染不要求独显或 4090。建议从 16 GB 内存、SSD、至少 20 GB 空闲空间起步；这是工程建议而非已验证的硬件下限，不含可选模型与大量逐帧 PNG。IndexTTS 内存与速度取决于设备、模型和句长，不能用 JS 的最低需求替代推理实测。macOS 有自动化安装验证；Linux 需自行安装对应系统包、中文字体和 Chromium 系统库。Windows 建议使用 WSL2，尚未做本轮端到端验收。

## 检查与真实短链路验收

在制作目录执行：

```bash
bash scripts/setup_workbench.sh --check
# 不生成媒体的 JSON 报告；--strict 让未就绪时返回失败码
.venv/bin/python scripts/environment_check.py --workspace . --pretty --strict
# 2 秒静音技术片，验证 Canvas 定帧、编码和解码，不代表医学样片
node scripts/smoke_local_animation.mjs
```

检查报告列出缺项、实际解释器、浏览器启动结果和对应修复命令；未选中的模型缺失不阻断核心安装。`selected_narration` 单独报告当前声音依赖：选了 Edge 就检查 edge-tts，选了 IndexTTS 就检查运行时、模型配置和参考音频路径；缺项时整体返回 `needs_setup`，仍保留独立的 `core_ready`。`ready` 仅表示环境和配置通过，不代表模型完整或合成成功，`production_ready` 始终为 false。语气稳定性、素材与医学关系、整片视听、发布资格必须按制作 SOP 另行验收。

已有工作台先用其原安装脚本或随包 `environment_check --workspace <目录>` 检查。旧工作区缺新入口时由智能体比较后增量更新，不整目录覆盖；新建隔离工作区也是可选路径。具体工具调用见[工作台接入](workspace-adapter.md)，IndexTTS 见[后端说明](../runtime/workbench/backends/indextts/README.md)。

首片创作、分层素材、字幕与固定表达的默认方法见[新用户首片 SOP](../runtime/workbench/docs/14_新用户首片SOP.md)。

维护者可用已初始化的隔离工作区运行真实渲染回归：设置 `MED_AUTOCAST_TEST_WORKSPACE=<工作区绝对路径>`，再用该工作区 `.venv/bin/python -B -m unittest discover -s tests -v`。测试使用临时非医学素材和静音音轨，验证共享 HTML 定帧、编码、缺资源拦截及旧 render/mux 接口，不下载模型、不播放声音、不改真实作品。未设置该变量时会明确跳过此项，不能计作真实渲染验收。
