---
name: med-autocast
description: 使用 Med Auto Cast 规划、制作、修订和审查医学科普动画，交付审看包并保管可复用图像、组件、动作与声音。
---

# Med Auto Cast

用当前请求确定系列、单集、工作区与交付范围。此智能体提供医学视频专业语义；OPL负责执行、状态、评测和包生命周期。

主 Skill 与专业 Skill 是通用制作方法，不内置具体医生品牌。品牌名称、人物母版、参考声线和系列露出规则属于目标工作区的作者/系列档案；运行时读取并保持系列一致。示例作者不得成为新作者的默认身份。用户显式跳过人物形象或专用声线时分别记录，不从另一项推断。

品牌露出与人物出镜独立：固定图形印记、字体、材质、位置或片尾动作也能建立系列识别，不能把品牌一致性解释成每集必须出现医生人物。人物是否进入画面由该集叙事和作者档案决定。

优先从主机已登记的 OPL 入口调用 `plan-series`、`produce-episodes` 或 `review-delivery`。公开合同见 `contracts/action_catalog.json`；如果还未安装/登记，就在当前获授权会话中使用专业 Skill 与本地辅助程序，说明这不构成 OPL 托管运行或资格通过。

首次准备本地环境由智能体按`docs/installation.md`调用随包 `runtime/workbench/scripts/setup_workbench.sh --workspace <新目录>`；先检查已有工作区，不能覆盖其专用实现。环境就绪、作者基线、真实语音/成片验收分开；可选模型不阻断核心安装。

1. 以 `workspace_root` 定位制作工作台，读取 workbench.yaml、`runtime/workbench/docs/17_工作台目录结构与资产生命周期.md` 与当前选集制作单。用仓库的 `runtime/native_helpers/med_autocast.py inspect --workspace <绝对路径>` 只读检查可用路径；不要把当前 cwd 当作制作工作区。
2. 新作者或新系列先由 `medical-video-series-producer` 核对作者表达基线、系列登记与完整样片依据；执行原 `workbench_config validate --series`。选题与证据交 `agent/professional_skills/medical-video-content-planner/SKILL.md`；故事、画面解释与时间轴交 `medical-video-director`；真实媒体缺口交 `medical-video-backends`。具体路径见 `agent/stages/manifest.json`。
3. S07/S08 由导演、后端与 `medical-video-release-packager` 共同完成配音、字幕、选段、品牌、混音和合成；具体工具见 `docs/workspace-adapter.md`。成片和候选交 `medical-video-visual-qa`，交付交 `medical-video-release-packager`，跨阶段恢复与资产沉淀交 `medical-video-series-producer`，均位于 `agent/professional_skills/`。
4. 先复用已审资产和未变音轨。精简恢复原任务，保留单一 writer。每项通过状态必须对应真实证据；技术、静态、连续动态、完整听感、医学与上传分开。交付到 publish 表示审看入口，不能据此宣称已上传或可公开发布。

新视频先执行作者/医生基线：确定作者档案、医生形象是否露脸、参考声线、表达方向和医疗身份边界，再进入内容和导演阶段。默认视频走本地 JS 动画与叙事性手绘拼贴，视频模型为显式备选；先用 `check_animation_assets` 检查正确且可分层的素材，再通过 `render_javascript_animation` 预览和渲染。有授权参考声线时使用作者档案登记的本地 IndexTTS 或等效后端；无专用声线或用户明确跳过时，才使用 Edge TTS `zh-CN-XiaoyiNeural` 保底。ImageGen 素材由当前会话的 ImageGen Skill 生成并登记，网上素材须保留来源许可；`audio_baseline` 的响度结果不能代替完整语气审听。具体输入见 `runtime/workbench/docs/13_素材准入与配音基线.md`。

专业 Skill 及 SOP 可按当前任务选择加载，不要求用户重复批准已授权的本地工作。部署、生产媒体生成与发布须符合当前请求范围。详见 `docs/production-sop.md`、`docs/workspace-adapter.md`。

默认纸剧场先把医学素材转为患者问题地图，再规划系列故事圣经和每集 `episode_blueprint`。blueprint 是创意交接，不是机器表单：推荐先写视觉处理稿、风格帧和带声音事件的分镜，再做完整粗动态分镜；低保真代码预览、独立镜头、声音准备和安全替代可以并行推进。这个顺序提高初稿质量，不是阶段启动门；信息不足或质量检查未通过时，保留可消费候选/诊断与质量债，继续不依赖该缺口的工作。被拒绝的医学素材不得进入渲染；没有安全替代时省略受影响镜头，不臆造解剖。新系列使用 `content/<topic>/` 与 `productions/<series>/<episode>/` 的分层结构；`work/`、`output/`、`deliveries/` 和 `archive/` 分别承担运行态、批量输出、交接记录和历史只读用途，不能互相充当制作权威。预览联系表和每镜固定 12 姿态 strip 是导演的定位证据，不是机器质量门；透明素材出现图册残片时应回到单件生成或合法素材准入，不能靠遮挡卡片掩盖。可用 HyperFrames storyboard/Studio 或本地 HTML 预览做导演审片面；静帧、联系表和代码检查只辅助定位故障，不定义视频质量。方法见 `runtime/workbench/docs/15_纸剧场系列策划与制作.md`、`runtime/workbench/docs/16_纸剧场前置策划与质量门.md`、`runtime/workbench/docs/17_工作台目录结构与资产生命周期.md`。

从 Video Shotcraft 吸收的镜头配方卡、单镜主运动、`prepare -> action -> reaction -> settle -> hold/rest` 动作弧、首帧/连续动作 strip/邻镜/整片的多轮审片，以及旁白、BGM、拟音分轨方法，见 `docs/video-shotcraft方法适配.md`。这里的 `shot_recipe` 是自然语言导演交接材料，不是阻断 Stage 的脚本 DSL；固定 seed、显式时间和 `window.__seek(t)` 只用于可复现预览。Remotion、HyperFrames 等可以辅助预览或作为替换渲染器，但不改变本地 Canvas 2D 纸剧场默认路线。

八个交接点的推荐顺序和返修优先级见 `runtime/workbench/docs/18_纸剧场导演流程与质量框架.md`：通常先收敛患者任务、故事卡、处理稿和 animatic，再准入透明单件并写逐镜 JS；Stage 可以按用户目标与已有产物跳转、并行或回退。去文字审片、视觉负担预算和线段/色带物理来源用于判断候选成熟度；未达标时继续返修或交接质量债，不阻止其他可消费进度。不能用脚本复杂度、标签堆叠或随机抖动补足没有视觉事件的镜头，也不能把欠项候选称为通过或 ready。

六阶段与原十阶段职责映射见 `docs/production-sop.md`。完整专业方法、模板和通用工具随包存于 `runtime/workbench/`；旧制作单保留原入口；纸剧场统一使用随包 paper_project，避免预览和正式渲染调用不同版本。默认交付预检使用 `med_autocast.py preflight-workbench`，直接读取原制作单和交付清单，不另外维护 Med Auto Cast 制作状态。

新用户只需提供主题、受众与大致时长；其余由智能体完成。首步默认建立品牌识别、医生形象和授权声线基线；已有系列复用其作者档案中的人物、声线与品牌出场方式。人物基线不要求每集出镜；某集仅用固定品牌印记仍属于该系列，不记录为跳过形象。用户也可显式跳过人物基线或专用声线，制作通用纸剧场；只有无专用声线或明确跳过时才用 Edge，记录 `voice.mode: edge` 并重置声音待审。不得因专用声线后端故障静默切换。工具入口为 `configure_voice --mode edge|reference`。按 `runtime/workbench/docs/14_新用户首片SOP.md` 完成首片。


新建或重构代码动画采用 `runtime/workbench/templates/animation/paper_theatre/` 的 TypeScript/Canvas 镜头模块，方法见 `runtime/workbench/docs/19_纸剧场模块架构与镜头打磨.md`。先做导演与 animatic，再准入透明素材；素材清单持有路径和连接点，score 持有事件时间，镜头持有构图与相机，播放器只装配。独立镜头预览、动作样本与版本对照用于持续打磨，不把复用解释为固定构图或故事。保持单集版本冻结和自定义镜头出口；通用模板不含医生、疾病和品牌。

纸剧场实际操作统一走 `paper_project`，按 `runtime/workbench/docs/20_纸剧场单集工具与局部返修.md` 执行初始化/接入、素材台、精确声段配音、真实时码、ASR 辅助字幕、邻镜预览、混音、导出和审看交付。用 `library` 查询跨集纸件；医生品牌来自工作区。新工具减少搬运，不代替导演判断或视觉探索。

风格选择遵循 `style_id`（艺术语言）与 `renderer`（执行后端）分离。优先保留用户 workflow input 的单集选择；通过 `paper_project` 的 `init` 或 `adopt` 子命令将其写入本集 `score.json`，不改全局作者档案。预览/渲染回执区分用户请求、实际 renderer 和实现方声明的 `appliedStyleId`；元数据不能替代视觉 Review。未知风格或未激活 renderer 记录质量债务并继续可消费工作，不因字段或注册表缺项停住。

## Stage 定位与 Progress First

纸片尺寸按实际内容、认知关系和构图平衡判断，区分独立物件、纸上插画与比喻装置，不统一图片外框或强求实物等比例。导演规划主次与局部缩放，Review 核对动作和邻镜；比例数值属于单集，通用方法不设固定比值或启动门。

纸剧场的视觉丰富度与配乐先从导演阶段联合设计，方法见 `runtime/workbench/docs/22_纸面舞台与声音导演.md`。完整环境板建立纸面空间，透明主体负责可见事件，前景提供真实遮挡；通用 scene 模块控制层序与布局，镜头保留创作自由。音乐支持曲库、明确许可的生成或本地原创演奏，现有 `paper_project mix --music-plan` 可混分轨并按实际旁白压低音乐。素材、声音与邻镜状态的 Review 持续进行，不增加脚本启动门；品牌动机、医生形象和声线仍从工作区读取。

Manifest 的六阶段路线是 `evidence-plan -> story-directing -> media-production -> visual-review -> meta-review -> review-handoff`；`asset-curation` 是交付后的可选集中沉淀，素材策展能力也贯穿制作。导演准备先查库并看实际原件/动作，制作中独立保存有价值的纸件、组件、声音与来源；清理前保全。由 `medical-video-asset-curator` 使用 `paper_project library` 的只读查询、独立版本包、看图库和精确版本复用；作者/声线母版仍在作者档案，医学、动态和听感状态不因入库升级。方法见 `runtime/workbench/docs/23_可复用素材保管与策展.md`。每个 Stage 的 prompt、专业 Skill、quality gate、工具和推荐产物可由 `contracts/stage_capability_bundle.json` 查询，动画风格与渲染器可由 `contracts/animation_style_registry.json` 查询。

能力包、`requires`、artifact envelope 和风格注册表是定位与交接建议，不是阻断流程的脚本 DSL。模型输出不完整、字段缺失、未列出的可消费材料或工具能力不足，优先保留已有结果、记录 `quality_debt`、`route_back` 或工具 blocker 并继续推进。工具失败时保留部分结果并物化可读诊断；OPL 可将诊断作为进度按默认路由继续。不能仅凭退出码、质量预算耗尽或材料不完整结束流程；只有连可读诊断都无法形成，或命中权限、身份/当前性、执行器不可用、明确人工决定和不可逆授权等真实硬边界时才停止。

Stage 返回尽量引用真实产物与版本/来源信息，给出质量债务和下一步建议；OPL 可提供的 `stage_run_ref`、owner receipt、typed blocker、human gate、route-back 与 memory 均以真实引用为准。推荐字段缺失时下游仍消费可用材料，不因返回 JSON 不完整而丢弃阶段进展。

区分领域报告与 OPL 运行回执：`stage_review_report`、`meta_review_report`、可读 `route_analysis` 是 Med Auto Cast 的普通审阅材料；OPL formal review receipt、owner receipt、typed blocker 和 Stage 转换由 OPL 按自身合同生成，不能在领域文件中伪造。只有终局 decisive Attempt 需要在 OPL closeout 中表达实际去向：`route_impact.stage_route_decision`；非终局 Attempt 的判断放在 `route_impact.stage_route_recommendation`。其 `decision_kind` 与 `target_stage_id` 面向 OPL 的声明 Stage ABI，不需要复刻成领域 JSON schema。终局路由缺失或不合 ABI 时，可消费产物保留、形成路由质量债并按 OPL 默认推进规则继续；不要把它改造成内容产物门禁。具体 Stage 去向由模型结合目标、产物和审查判断，框架只校验输出权威、形状和目标身份。

常规 Stage 由 OPL 按配置执行 `producer -> reviewer -> repairer -> re-reviewer` 质量循环。`meta-review` 是标记为 `cross_stage_meta_review` 的独立终审 Stage：单次综合判断患者目标、医学证据、导演意图、精确候选、声音/字幕/视觉一致性与阶段 Review 覆盖，并把缺陷回到最早 owner Stage；不再嵌套另一轮 formal review。它不替代医生审核，不签发 owner receipt、发布授权或 production-ready。

## 全季交付回读

全季审看包完成后，先按工作区的 `workbench.yaml`、系列登记、每集 `project.json`、`out/current.json` 与 `publish/<series>/<episode>/current/manifest.json` 重建当前版本；不要按修改时间、目录排序、旧 checkpoint 或文件名前缀猜版本。代码纸剧场的 `--master` 必须来自 `out/current.json`，`--delivery` 必须传精确 manifest 文件，不传目录。

逐集 `preflight-workbench` 通过只证明制作单、母版、publish 视频和 manifest 的引用与字节一致。全季审计还应核对字幕安全区、逐镜 `shot_recipe`、语义事件、无 BGM 审听候选、视频解码和 SHA-256；联系表、静帧、ASR、响度和布局只能定位问题，不能替代连续动态、完整听感或医学审查。`release_eligible`、视觉、连续动态、听感、医学和上传状态分开保留。

每集只保留一个活动 `current/`；被替换候选归档到该集自己的 `archive/<revision>/`。交付文档和生成器按实际目录写归档路径，不能把一集路径推广为全季，也不能把历史归档误报为本轮替换。Progress First 下，版本或文档问题先修 owner 并保留可消费产物，记录 `quality_debt` 或诊断后继续；只有当前性、权限、执行器、身份和明确人工决定等硬边界才停止。方法细节见 `runtime/workbench/docs/25_全季交付回读与经验沉淀.md`。
