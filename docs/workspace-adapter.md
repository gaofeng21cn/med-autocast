# 工作台工具与原合同接入

制作工作区持有 workbench.yaml、作者/后端档案、系列、媒体、制作单和审核记录；OMC 随包提供完整专业方法、模板及通用工作台工具。先按系列解析作者覆盖，再继承活动作者；设备、模型、字体和凭据来源由工作区配置决定。

主入口中的路径相对已加载的 Skill 根。以下以该根为当前目录，`/absolute/workspace` 替换为制作工作区；Python 选用该工作区核心环境，IndexTTS、Whisper 和视频模型使用各自登记环境。

```sh
python3 runtime/native_helpers/medcast.py inspect --workspace /absolute/workspace
python3 runtime/native_helpers/medcast.py tools --workspace /absolute/workspace
python3 runtime/native_helpers/medcast.py assets --workspace /absolute/workspace --category 05
python3 runtime/native_helpers/workbench_tool.py --workspace /absolute/workspace --name workbench_config -- validate --series SERIES --pretty
python3 runtime/native_helpers/workbench_tool.py --workspace /absolute/workspace --name media_backend -- resolve --media video --pretty
```

`inspect`、`tools`、`assets` 和预检只读。`workbench_tool.py` 同步调用一个明确工具，不创建队列或调度器；其效果与原工具一致。所有调用的 cwd 都是制作工作区，默认优先原 `scripts/`；缺少通用脚本才使用随包版本。`--bundled` 显式选择随包版本。工具接收的剩余参数原样传递；生成、下载、合成、检查输出和打包需处于本次授权范围。

| 工作 | 工具名称 | 使用边界 |
| --- | --- | --- |
| 配置、作者、目录、字体 | workbench_config | validate；show 可能含本机信息，不回显敏感配置 |
| 后端选择、诊断 | media_backend | resolve；确需服务诊断才 doctor，不生成媒体 |
| 配音、ASR、字幕与节拍 | render_series_tts、transcribe_series_whisper、build_episode_timelines | 审定旁白为权威；ASR 不改医学文字；依赖独立模型环境 |
| H3 提交、批量调用、输出下载 | queue_h3_shots、render_series_h3、fetch_h3_receipt | 官方提示直通、原任务恢复、回执绑定；不重复提交 |
| 合成和系列构建 | build_episode_video、build_series_videos | 前者是通用合成器；后者仅用于匹配的根制作单/final 合同，支持 --episode |
| 技术和时间轴检查 | qa_series_videos、build_timeline_review | 后台输出；QA 支持 --episode，范围不得扩读为全季或完整听感 |
| 背景音乐 | generate_gentle_bgm | 由作者档案决定使用、音量和淡入淡出 |
| 单集审看修订交付 | package_review | 显式 --series、--episode、--plan、--master、--review；可附 --technical-qa 和 --source-review。保留旧包，更新本集并回读，不重渲染 |
| 正式 final 交付 | build_release_packages | 原合同、双平台 TXT；整季入口无 --episode，单集使用原公开函数或匹配的专用包器 |
| 关键帧库投影 | build_keyframe_library | 先由专业判断决定入库；脚本校验并生成页面、CSV、缩略图 |

审看修订优先使用当前工作区登记或当前任务确认的专用包器，先读其参数、制作单与母版路径。现有目录采用 medical_video_review_package/v1 或尚未建包，且没有适用的专用包器时，随包 package_review 直接接收原制作单、当前母版和原审看记录，按原文案格式生成本集交付，更新系列清单并逐字节回读。正式 v2 清单继续使用原匹配包器，不能在同一清单中混写审看包字段。不能用通用 final 包器覆盖 review 修订。OPL 三个公开动作仍由 StageRun 加载专业 Skill，不是同名 Python 命令。

## 直接读取原制作单和交付包

```sh
python3 runtime/native_helpers/medcast.py preflight-workbench --workspace /absolute/workspace --series SERIES --episode EPISODE --plan productions/SERIES/EPISODE/review/REVISION/production_plan.yaml --master productions/SERIES/EPISODE/review/REVISION/video.mp4
```

`--plan` 和 `--master` 来自当前任务确认的独立输入；不从待验证交付清单反推“当前版本”，不按前缀或修改时间猜测。支持制作单 video_production_plan/v2、v3 和交付 medical_video_review_package/v1、medical_video_series_delivery/v2，原文件原地读取，**不要求生成另一套 OMC 制作单**。默认从登记 publish_root 读 manifest；可用 --delivery 指定精确清单、--source-review 指定原源片审查记录。

预检核对集号、实际路径、镜头区间、母版复制字节、可用时的审看记录与字幕、两份 TXT 和登记 release_catalog 全文。拒用状态优先于残留区间；源 ID 缺少真实文件映射时保留缺证据，不能猜测批准。原复核声明原样返回，不升格为新的质量批准。工具不解码成片、不判医学正确性、不授权上传；原 animation_gate、技术 QA 和专业复核仍须按任务范围执行。

工作台根外的 NAS/挂载资产通过 --allow-root 显式登记允许读取的根，不默默放宽路径范围。旧的 `preflight --current --delivery --source-review` 仅兼容已经采用 OMC v1 JSON 的调用者，不作为新任务的默认入口。

## 新工作区与迁移

按[安装与迁移](../runtime/workbench/docs/10_安装与迁移.md)初始化核心环境，并从随包 runtime/workbench/templates 复制作者、后端及系列模板。`runtime/workbench` 是通用核心来源，不含私人档案、媒体或权重；新工作区可复制核心 scripts、backends、templates、依赖清单，再登记自己的 workbench.yaml。已有工作区不整体覆盖，先保留并核对本机改动。

核心依赖 PyYAML、Pillow、FFmpeg/ffprobe、ImageMagick 与配置字体；Python 3.11 以上。GPU、IndexTTS、Whisper、MLX/CUDA 的环境与模型保持独立。随包部署脚本只在明确安装/迁移任务中运行，不因一次检查自动安装模型或重启服务。
