---
name: med-autocast
description: 使用 Med Auto Cast 规划、制作、修订和审查医学科普视频，交付审看包并整理已审关键帧资产。
---

# Med Auto Cast

用当前请求确定系列、单集、工作区与交付范围。此智能体提供医学视频专业语义；OPL负责执行、状态、评测和包生命周期。

优先从主机已登记的 OPL 入口调用 `plan-series`、`produce-episodes` 或 `review-delivery`。公开合同见 `contracts/action_catalog.json`；如果还未安装/登记，就在当前获授权会话中使用专业 Skill 与本地辅助程序，说明这不构成 OPL 托管运行或资格通过。

1. 以 `workspace_root` 定位制作工作台，读取 workbench.yaml 与当前选集制作单。用仓库的 `runtime/native_helpers/med_autocast.py inspect --workspace <绝对路径>` 只读检查可用路径；不要把当前 cwd 当作制作工作区。
2. 新作者或新系列先由 `medical-video-series-producer` 核对作者表达基线、系列登记与完整样片依据；执行原 `workbench_config validate --series`。选题与证据交 `agent/professional_skills/medical-video-content-planner/SKILL.md`；故事、画面解释与时间轴交 `medical-video-director`；真实媒体缺口交 `medical-video-backends`。具体路径见 `agent/stages/manifest.json`。
3. S07/S08 由导演、后端与 `medical-video-release-packager` 共同完成配音、字幕、选段、品牌、混音和合成；具体工具见 `docs/workspace-adapter.md`。成片和候选交 `medical-video-visual-qa`，交付交 `medical-video-release-packager`，跨阶段恢复与资产沉淀交 `medical-video-series-producer`，均位于 `agent/professional_skills/`。
4. 先复用已审资产和未变音轨。精简恢复原任务，保留单一 writer。每项通过状态必须对应真实证据；技术、静态、连续动态、完整听感、医学与上传分开。交付到 publish 表示审看入口，不能据此宣称已上传或可公开发布。

新视频先执行作者/医生基线：确定作者档案、医生形象是否露脸、参考声线、表达方向和医疗身份边界，再进入内容和导演阶段。默认视频走本地 JS 动画与叙事性手绘拼贴，视频模型为显式备选；先用 `check_animation_assets` 检查正确且可分层的素材，再通过 `render_javascript_animation` 渲染。`Dr.咩` 基线默认使用本机 IndexTTS 2.5 和作者参考音频；只有没有用户声线基线时，才使用 Edge TTS `zh-CN-XiaoyiNeural` 作为保底技术测试。ImageGen 素材由当前会话的 ImageGen Skill 生成并登记，网上素材须保留来源许可；`audio_baseline` 的响度结果不能代替完整语气审听。具体输入见 `runtime/workbench/docs/13_素材准入与配音基线.md`。

专业 Skill 及 SOP 可按当前任务选择加载，不要求用户重复批准已授权的本地工作。部署、生产媒体生成与发布须符合当前请求范围。详见 `docs/production-sop.md`、`docs/workspace-adapter.md`。

六阶段与原十阶段职责映射见 `docs/production-sop.md`。完整专业方法、模板和通用工具随包存于 `runtime/workbench/`；已有工作区优先使用原入口。默认交付预检使用 `med_autocast.py preflight-workbench`，直接读取原制作单和交付清单，不另外维护 Med Auto Cast 制作状态。
