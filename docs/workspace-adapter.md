# 工作台工具与原合同接入

## Mini App 任务与媒体入口

Package 在根目录 `opl-package.json` 的 `ui.declarative` 与 `provides.contribution_handler`
声明 `med-autocast.workspace.status`、`med-autocast.workspace.media` 等共享视图并直连随包 `runtime/native_helpers/app_contribution.py`，
工作区只从 Framework 验证后注入的 `OPL_PROFILE_WORKSPACE` 取得。空输入列出全部登记单集；
`series_id`、`episode_id` 定位一集，`shot_id` 进一步聚焦 Score 中的镜头。不存在的身份返回诊断，不改选其他集或旧版本。

返回的媒体与材料使用精确 `artifact_ref`，镜头保留原始 `start/end`；当前视频、
交付清单及其中的 `reviews`、`quality_debt` 分别显示。读取不会播放、渲染、调用后端或写工作区。
缺少成片时仍可查看已存在的工程和镜头，不把资料完整性当作启动门。

Studio 通过共享产物链接在当前对话工作区内预览媒体，镜头入口跳到 `start` 并在 `end` 停止。
制作目录须位于该对话工作区内；Framework 登记制作工作区本身不扩大 Host 的文件读取范围。

“记录审看意见”接收选定单集、可选镜头和文字。它要求当前返回的 `revision`，将意见原文及
对应媒体引用保存到工程 `qa/miniapp-notes/<request_id>.json`，并回读确认。相同 request ID
重试返回同一材料；相同 ID 不同输入拒绝覆盖。刷新候选后需针对新 revision 重新提交。
revision 包含当前媒体的实际 SHA-256，替换视频但保留文件时间和大小仍会使旧意见请求失效。
意见以完整 JSON 原子落盘；候选或镜头后来变化不会改写已记录的原意见。
调用结果未知或关闭 UI 后，先用 `status`/`media` 传同一 `series_id`、`episode_id` 和
`request_id` 回查 `requested_note`，结果为 `recorded` 或 `not_found`。`recorded` 同时给出
原意见、产物引用和是否仍匹配当前 revision；不需要重新提交，也不要求原镜头仍存在。
动作成功结果的 `readback` 提供相同读取入口与输入。撤销工作台中的单集登记后，旧选择不能再读写该单集。
此动作不改 `reviews`、不批准医学或音画质量，也不自动启动制作；接着使用当前 OPL 任务
动作把该意见引用交给 Visual Review 或返修阶段，复用已有 Task/StageRun。

本地只读入口（制作工作区替换为自己的目录）：

```sh
OPL_PROFILE_WORKSPACE=/absolute/workspace python3 runtime/native_helpers/app_contribution.py status <<'JSON'
{}
JSON
```

MCP 请求由 Framework 处理确认与工作区身份；业务意见、媒体与专业审查仍由 MAC 工作区保管。

独立媒体审看未收到已验证的 profile 环境时，从 `opl workspace list --json` 读取 Med Auto Cast 的当前工作区，
通过 `opld` 公开 `app.contribution.read` / `app.action.execute` 调用原领域入口。显式 `workspace_path` 每次由 Framework
核对登记和目录状态；未登记时提示接入，不猜测源码目录。页面显示当前工作区，并在切换单集、
刷新、记录意见和恢复最近位置时保留这一引用。没有第二份工作区注册表。


制作工作区持有 workbench.yaml、作者/后端档案、系列、媒体、制作单和审核记录；Med Auto Cast 随包提供完整专业方法、模板及通用工作台工具。先按系列解析作者覆盖，再继承活动作者；设备、模型、字体和凭据来源由工作区配置决定。

主入口中的路径相对已加载的 Skill 根。以下以该根为当前目录，`/absolute/workspace` 替换为制作工作区；Python 选用该工作区核心环境，VoxCPM2、Whisper 和视频模型使用各自登记环境。

```sh
python3 runtime/native_helpers/med_autocast.py inspect --workspace /absolute/workspace
python3 runtime/native_helpers/med_autocast.py tools --workspace /absolute/workspace
python3 runtime/native_helpers/med_autocast.py assets --workspace /absolute/workspace --category 05
python3 runtime/native_helpers/med_autocast.py assets --workspace /absolute/workspace --library animation --query 信封
python3 runtime/native_helpers/workbench_tool.py --workspace /absolute/workspace --name workbench_config -- validate --series SERIES --pretty
python3 runtime/native_helpers/workbench_tool.py --workspace /absolute/workspace --name media_backend -- resolve --media video --pretty
python3 runtime/native_helpers/workbench_tool.py --workspace /absolute/workspace --name environment_check -- --pretty
```

`inspect`、`tools`、`assets` 和预检只读。`workbench_tool.py` 同步调用一个明确工具，不创建队列或调度器；其效果与原工具一致。所有调用的 cwd 都是制作工作区；paper_project、render_narration、render_javascript_animation、audit_pronunciation 固定使用随包实现，其他旧制作单工具优先原 scripts，缺少时使用随包版本。核心解释器自动选工作区 .venv；工具清单显示真实执行路径与解释器。`--bundled` 显式选择随包版本。工具接收的剩余参数原样传递；生成、下载、合成、检查输出和打包需处于本次授权范围。

阶段推荐顺序由 `agent/stages/manifest.json` 和 `contracts/stage_capability_bundle.json` 共同说明：`visual-review` 后进入独立 `meta-review`，再到 `review-handoff`；交付后按需进入 `asset-curation` 集中沉淀。素材策展专业能力同时供导演准备和制作中调用；欠项不阻断已有交付。Meta Review 读取精确候选和已有 Review 判断最早返修职责，不创建第二 writer，不替代医学或发布负责人。

OPL 阶段输出以可引用产物为中心：返回真实 `artifact_refs` 与可选来源/当前性 envelope；同时记录 `stage_run_ref`、质量债务和建议下一步。交付目标、候选、Review 范围与交付包可以像 RedCube 的 deliverable/review/export surfaces 一样分开说明，但 Med Auto Cast 只把它们作为适应工作区的建议，不强制固定目录或字段。需要转交责任、权限或恢复上下文时，只引用真实存在的 owner receipt、typed blocker、human gate、route-back 或 memory ref。引用可以缺省，产物仍可继续进入下一 Stage；不得编造回执或把结构字段缺失变成流程硬停。

领域 `route_analysis` 是给人和下游模型读的去向理由。OPL 终局 Attempt 的 `route_impact.stage_route_decision` 才是实际 Stage 转换；非终局 Attempt 使用 `route_impact.stage_route_recommendation`。路由 ABI 缺失或被拒绝只形成路由质量债，OPL 会保留可消费产物并沿合同声明的默认推进继续。不要用一个领域 JSON 文件或本地脚本替代 OPL 的语义路由。

| 工作 | 工具名称 | 使用边界 |
| --- | --- | --- |
| 配置、作者、目录、字体 | workbench_config | validate；show 可能含本机信息，不回显敏感配置 |
| 后端选择、诊断 | media_backend | resolve；确需服务诊断才 doctor，不生成媒体 |
| 作者声音选择 | configure_voice | 用户明确选择 reference 或 edge，保留参考音频、重置声音待审 |
| 本机环境诊断 | environment_check | 区分核心依赖、JS 渲染、VoxCPM2、Edge fallback 和 Whisper；只读 |
| 配音、ASR、字幕与节拍 | render_series_tts、transcribe_series_whisper、build_episode_timelines | 审定旁白为权威；ASR 不改医学文字；依赖独立模型环境 |
| H3 提交、批量调用、输出下载 | queue_h3_shots、render_series_h3、fetch_h3_receipt | 官方提示直通、原任务恢复、回执绑定；不重复提交 |
| 合成和系列构建 | build_episode_video、build_series_videos | 前者是通用合成器；后者仅用于匹配的根制作单/final 合同，支持 --episode |
| 技术和时间轴检查 | qa_series_videos、build_timeline_review | 后台输出；QA 支持 --episode，范围不得扩读为全季或完整听感 |
| 背景音乐 | generate_gentle_bgm | 由作者档案决定使用、音量和淡入淡出 |
| 单集审看修订交付 | package_review | 显式 --series、--episode、--plan、--master、--review；可附 --technical-qa 和 --source-review。保留旧包，更新本集并回读，不重渲染 |
| 正式 final 交付 | build_release_packages | 原合同、双平台 TXT；整季入口无 --episode，单集使用原公开函数或匹配的专用包器 |
| 关键帧库投影 | build_keyframe_library | 先由专业判断决定入库；脚本校验并生成页面、CSV、缩略图 |
| 可复用素材版本库 | paper_project library | 查询只读；显式归档原件/证据、代码/动作/声音包、完整看图库与精确版本复制。新镜头审核重置，源码由开发者显式接入 |

风格与渲染器通过工作区作者档案或工作流输入的 `style_selection.style_id`、`style_selection.renderer` 指定；缺省为 `paper_collage` + `canvas2d`。未知选择保留用户意图并记录质量债务，不能因为注册表暂缺就阻断故事或 Review。

审看修订优先使用当前工作区登记或当前任务确认的专用包器，先读其参数、制作单与母版路径。现有目录采用 medical_video_review_package/v1 或尚未建包，且没有适用的专用包器时，随包 package_review 直接接收原制作单、当前母版和原审看记录，按原文案格式生成本集交付，更新系列清单并逐字节回读。正式 v2 清单继续使用原匹配包器，不能在同一清单中混写审看包字段。不能用通用 final 包器覆盖 review 修订。OPL 三个公开动作仍由 StageRun 加载专业 Skill，不是同名 Python 命令。

本地工具源码与已安装缓存分别生效。当前任务修订工具但尚未安装新版时，按[本地工具修订的显式验证入口](../runtime/workbench/docs/20_纸剧场单集工具与局部返修.md#本地工具修订的显式验证入口)选择已核对的工作台源码，并回读同根 renderer/检查器和实际预览；不改旧缓存，也不把源码修复当作安装完成。默认随包路由保持不变。

## 直接读取原制作单和交付包

```sh
python3 runtime/native_helpers/med_autocast.py preflight-workbench --workspace /absolute/workspace --series SERIES --episode EPISODE --plan productions/SERIES/EPISODE/review/REVISION/production_plan.yaml --master productions/SERIES/EPISODE/review/REVISION/video.mp4
```

`--plan` 和 `--master` 来自当前任务确认的独立输入；不从待验证交付清单反推“当前版本”，不按前缀或修改时间猜测。支持制作单 video_production_plan/v2、v3 和交付 medical_video_review_package/v1、medical_video_series_delivery/v2，原文件原地读取，**不要求生成另一套 Med Auto Cast 制作单**。默认读内部 deliveries 系列清单，旧工作区兼容读取 publish_root 的历史 manifest；可用 --delivery 指定精确清单、--source-review 指定原源片审查记录。

代码纸剧场的 `--plan` 可以是 `project.json`，但 `--master` 必须来自该项目的 `out/current.json`；`--delivery` 必须是内部 `deliveries/<series>/<episode>/manifest.json` 文件。预检成功只证明当前性、引用和字节一致，不批准连续动态、完整听感、医学质量或公开发布。全季交付后的逐集审计、归档路径和文档回读见[全季交付回读与经验沉淀](../runtime/workbench/docs/25_全季交付回读与经验沉淀.md)。

预检核对集号、实际路径、镜头区间、母版复制字节、可用时的审看记录与字幕、两份 TXT 和登记 release_catalog 全文。拒用状态优先于残留区间；源 ID 缺少真实文件映射时保留缺证据，不能猜测批准。原复核声明原样返回，不升格为新的质量批准。工具不解码成片、不判医学正确性、不授权上传；原 animation_gate、技术 QA 和专业复核仍须按任务范围执行。

工作台根外的 NAS/挂载资产通过 --allow-root 显式登记允许读取的根，不默默放宽路径范围。旧的 `preflight --current --delivery --source-review` 仅兼容已经采用 Med Auto Cast v1 JSON 的调用者，不作为新任务的默认入口。

## 新工作区与迁移

### 单集知识登记

批量 OPL 动作使用工作区授权的用户或团队、主题知识；单集私有知识由 direct Skill 明确选集后读取。先运行只读定位：

```sh
python3 runtime/native_helpers/med_autocast.py project-knowledge-locator \
  --workspace /absolute/workspace --series SERIES --episode EPISODE
```

定位同时核对 `workbench.yaml`、真实工程 `project.json` 与 OPL 的 `workspace_index.json.projects`。`ready` 返回已登记的 `project_id` 和 `knowledge_project_args`；`missing` 明确表示尚无项目知识范围。工具不会猜项目 ID、修改登记或读取知识正文。

若单集尚未登记，使用定位结果的真实 `project_root`，为该集指定稳定项目 ID，由 Framework 既有工作区入口接入：

```sh
opl workspace init --workspace /absolute/workspace \
  --project-id EXPLICIT_PROJECT_ID --project-root /absolute/workspace/productions/SERIES/EPISODE --json
```

`--project-root` 必须来自实际定位结果，不要求与示例目录同名。Framework 维护唯一正式项目 inventory，保留已有其他集，不搬动媒体或覆盖制作原件；MAC 不另写一份 inventory。接入后重新运行定位，确认身份和目录一致，再消费这一集：

```sh
opl workspace sources list --workspace <workspace-id> --json
opl workspace snapshot --workspace <workspace-id> --stage-run <stage-run-id> --json
```

正文来源、知识 ID、归属和授权仍须先按 Framework 的[知识来源接口](https://github.com/gaofeng21cn/one-person-lab/blob/main/docs/specs/knowledge-sources.md)登记；项目接入只建立身份映射，不产生知识读取授权。两集分别 prepare，输出使用各自新的 binding 文件。身份不一致时停止项目知识召回，独立制作工作仍可按现有范围继续。

### 制作工作台初始化

按[安装与迁移](../runtime/workbench/docs/10_安装与迁移.md)初始化核心环境，并从随包 runtime/workbench/templates 复制作者、后端及系列模板。`runtime/workbench` 是通用核心来源，不含私人档案、媒体或权重；新工作区可复制核心 scripts、backends、templates、依赖清单，再登记自己的 workbench.yaml；推荐直接执行 `bash runtime/workbench/scripts/setup_workbench.sh --workspace <新建空目录>` 自动完成初始化、标准目录和依赖安装。初始化会生成 `workspace.manifest.json` 与 `WORKSPACE.md`，两者只描述目录职责，不声称质量或发布状态。

已有工作区不整体覆盖。若工作区缺少新目录或初始化入口，先执行：

```sh
python3 runtime/workbench/scripts/init_workbench.py \
  --workspace /absolute/workspace --upgrade
```

或用该工作区的 `scripts/setup_workbench.sh`；升级只补齐缺失目录和入口标记。`med_autocast.py inspect` 与 `environment_check.py` 会回报 `workspace_layout` 的 `ready/partial` 状态，`partial` 是可修复诊断，不是 Stage 硬门，也不覆盖旧生产路径。

核心依赖 PyYAML、Pillow、FFmpeg/ffprobe、ImageMagick 与配置字体；Python 3.11 以上。环境依赖规格在 `contracts/pack_doctor.json` 声明；工作台脚本通过 `runtime/workbench/scripts/_opl_framework_bootstrap.py` 与 `_opl_file_hash.py` 复用 Framework helper，独立工作区无需另装 Framework。GPU、VoxCPM2、Whisper、MLX/CUDA 的环境与模型保持独立。随包部署脚本只在明确安装/迁移任务中运行，不因一次检查自动安装模型或重启服务。

## JS 动画与旁白基线入口

JS 与纸剧场统一使用随包渲染器；预览和正式编码不再因 --preview 而选择不同实现。单集默认使用 paper_project 串联实际工具，Edge 仅是联网保底。

输入字段和质量边界见 [素材准入与配音基线](../runtime/workbench/docs/13_素材准入与配音基线.md)。JS 制作单以 `animation.asset_manifest` 关联清单（相对制作单目录）；`preflight-workbench` 对 JS 制作单也执行素材准入。`tone_consistency` 与 `full_listening` 分开保留，响度通过不能批准语气。


## 模块化纸剧场入口

新集复制 `runtime/workbench/templates/animation/paper_theatre`（不复制 node_modules），在单集目录运行 `npm ci && npm run build`；Node 22.18+ 或 24 可运行 `npm test`。构建是本地文件写入，npm ci 需要首次依赖下载；最终 dist/film.js 不依赖 CDN。素材和品牌仍由工作区输入。`scripts/mix_audio.py` 接收 `--project --voice --output`，可选互斥的 `--music` 或 `--music-plan`；只混合已有音轨、真实旁白侧链与事件音效，不调用 TTS。使用 `score.json` 的命名事件避免音画双份时码。构建后的 index.html 兼容已有 render_javascript_animation 入口；无需新增 OPL 动作或平行任务状态。操作细节见[模板说明](../runtime/workbench/templates/animation/paper_theatre/README.md)。

完整操作见[单集工具与局部返修](../runtime/workbench/docs/20_纸剧场单集工具与局部返修.md)。纸剧场预检的 --plan 为 project.json，当前单集从 workbench.yaml.series 的 episodes 中发现，交付指针在 deliveries/SERIES/EPISODE.json。

`animation_lab` 是随包优先的代码动画能力入口：`list` 查询七个风格方法；`create --project <新空目录> --complete` 创建并构建原创样例、音效、预览和 MP4；失败后从 build/audio/preview/render 继续。通过 `workbench_tool.py --workspace <工作台> --name animation_lab -- ...` 调用。样例不含人物、品牌、医学解剖或旁白；实际单集继续用 `paper_project`。细节见 `runtime/workbench/docs/26_代码动画技法与风格工作流.md`。

面向用户的 `publish/` 单一最新版交付规范、归档边界与 `publish_catalog` 维护流程见[成片与双平台交付](delivery-sop.md#面向用户的单一最新版交付)；外挂 `mac-media-assets` 的只读查询与按需取用见[独立 MAC 媒体库接入](media-assets-integration.md)。

`audit_pronunciation --workspace W --series SERIES --output work/SERIES/pronunciation-audit.json` 从登记当前工程读取每个词的注音覆盖与真实原音状态。它可在配音前发现遗漏、配音后定位听辨范围，只写定位报告，未合成也可使用，不批准实际读音。

音频防复发工具：`audit_narration_samples --workspace W --output work/narration-samples.json` 逐段检查 source take 与原始 narration PCM 的精确采样包含关系；`audit_audio_freshness --workspace W --output work/audio-freshness.json` 核对 source/timing/mix/render/publish 的当前 SHA 绑定。两者只生成定位诊断，不批准读音、语气、完整听感、动画表意或医学含义。发现失配先修最早断点，再只更新受影响下游；其他可消费 Stage 继续。

## 媒体文件生命周期

`plan_workspace_retention` 先读取当前工程、显式保护的在制修订和独立问题引用，输出必要性清单；`apply` 校验整份选集后清理派生物，对保留项做无损压缩。规范见[媒体文件生命周期](../runtime/workbench/docs/50_媒体文件生命周期与存储治理规范.md)。当前工作台有独立实现时从其同根脚本调用；随包可通过 `workbench_tool.py --workspace <工作区> --name plan_workspace_retention -- plan --workspace <工作区> --policy <本次策略.json> --output <清单.json>` 调用。`apply --plan <清单.json> --parts review_frame audio render_temporary --output <回执.json>` 才执行写入。清单和回执不批准视觉、声音或医学质量；发布视频不重编码。

`compact_workspace_media.py plan` 只有格式库存，不再允许直接全量 apply。恢复仍可用原库存和同目录无损回执；历史源声恢复时使用回执中的 `flac -d --keep-foreign-metadata` 命令并核对 WAV SHA。源码与随包载体通过不代表已安装插件完成更新。
