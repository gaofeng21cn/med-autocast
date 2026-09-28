---
name: med-autocast
description: 使用 Med Auto Cast 规划、制作、修订和审查医学科普视频，交付审看包并整理已审关键帧资产。
---

# Med Auto Cast

用当前请求确定系列、单集、工作区与交付范围。此智能体提供医学视频专业语义；OPL负责执行、状态、评测和包生命周期。

主 Skill 与专业 Skill 是通用制作方法，不内置具体医生品牌。品牌名称、人物母版、参考声线和系列露出规则属于目标工作区的作者/系列档案；运行时读取并保持系列一致。示例作者不得成为新作者的默认身份。用户显式跳过人物形象或专用声线时分别记录，不从另一项推断。

品牌露出与人物出镜独立：固定图形印记、字体、材质、位置或片尾动作也能建立系列识别，不能把品牌一致性解释成每集必须出现医生人物。人物是否进入画面由该集叙事和作者档案决定。

优先从主机已登记的 OPL 入口调用 `plan-series`、`produce-episodes` 或 `review-delivery`。公开合同见 `contracts/action_catalog.json`；如果还未安装/登记，就在当前获授权会话中使用专业 Skill 与本地辅助程序，说明这不构成 OPL 托管运行或资格通过。

首次准备本地环境由智能体按`docs/installation.md`调用随包 `runtime/workbench/scripts/setup_workbench.sh --workspace <新目录>`；先检查已有工作区，不能覆盖其专用实现。环境就绪、作者基线、真实语音/成片验收分开；可选模型不阻断核心安装。

1. 以 `workspace_root` 定位制作工作台，读取 workbench.yaml 与当前选集制作单。用仓库的 `runtime/native_helpers/med_autocast.py inspect --workspace <绝对路径>` 只读检查可用路径；不要把当前 cwd 当作制作工作区。
2. 新作者或新系列先由 `medical-video-series-producer` 核对作者表达基线、系列登记与完整样片依据；执行原 `workbench_config validate --series`。选题与证据交 `agent/professional_skills/medical-video-content-planner/SKILL.md`；故事、画面解释与时间轴交 `medical-video-director`；真实媒体缺口交 `medical-video-backends`。具体路径见 `agent/stages/manifest.json`。
3. S07/S08 由导演、后端与 `medical-video-release-packager` 共同完成配音、字幕、选段、品牌、混音和合成；具体工具见 `docs/workspace-adapter.md`。成片和候选交 `medical-video-visual-qa`，交付交 `medical-video-release-packager`，跨阶段恢复与资产沉淀交 `medical-video-series-producer`，均位于 `agent/professional_skills/`。
4. 先复用已审资产和未变音轨。精简恢复原任务，保留单一 writer。每项通过状态必须对应真实证据；技术、静态、连续动态、完整听感、医学与上传分开。交付到 publish 表示审看入口，不能据此宣称已上传或可公开发布。

新视频先执行作者/医生基线：确定作者档案、医生形象是否露脸、参考声线、表达方向和医疗身份边界，再进入内容和导演阶段。默认视频走本地 JS 动画与叙事性手绘拼贴，视频模型为显式备选；先用 `check_animation_assets` 检查正确且可分层的素材，再通过 `render_javascript_animation` 预览和渲染。有授权参考声线时使用作者档案登记的本地 IndexTTS 或等效后端；无专用声线或用户明确跳过时，才使用 Edge TTS `zh-CN-XiaoyiNeural` 保底。ImageGen 素材由当前会话的 ImageGen Skill 生成并登记，网上素材须保留来源许可；`audio_baseline` 的响度结果不能代替完整语气审听。具体输入见 `runtime/workbench/docs/13_素材准入与配音基线.md`。

专业 Skill 及 SOP 可按当前任务选择加载，不要求用户重复批准已授权的本地工作。部署、生产媒体生成与发布须符合当前请求范围。详见 `docs/production-sop.md`、`docs/workspace-adapter.md`。

默认纸剧场先把医学素材转为患者问题地图，再规划系列故事圣经和每集 `episode_blueprint`。blueprint 必须包含锚点物件、开场误读、beat_form、读取顺序、因果事件、分层资产和结尾行动；导演再交接动作、阅读停留、blocking、分层资产与字幕避让的分镜。粗动态分镜、透明素材和可 seek 的 JS 预览均可在编码前返修。方法与质量门见 `runtime/workbench/docs/15_纸剧场系列策划与制作.md`、`runtime/workbench/docs/16_纸剧场前置策划与质量门.md`，不以文档齐全或联系表替代叙事和听感审核。

六阶段与原十阶段职责映射见 `docs/production-sop.md`。完整专业方法、模板和通用工具随包存于 `runtime/workbench/`；已有工作区优先使用原入口。默认交付预检使用 `med_autocast.py preflight-workbench`，直接读取原制作单和交付清单，不另外维护 Med Auto Cast 制作状态。

新用户只需提供主题、受众与大致时长；其余由智能体完成。首步默认建立品牌识别、医生形象和授权声线基线；已有系列复用其作者档案中的人物、声线与品牌出场方式。人物基线不要求每集出镜；某集仅用固定品牌印记仍属于该系列，不记录为跳过形象。用户也可显式跳过人物基线或专用声线，制作通用纸剧场；只有无专用声线或明确跳过时才用 Edge，记录 `voice.mode: edge` 并重置声音待审。不得因专用声线后端故障静默切换。工具入口为 `configure_voice --mode edge|reference`。按 `runtime/workbench/docs/14_新用户首片SOP.md` 完成首片。
