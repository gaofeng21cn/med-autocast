---
name: opl-medcast
description: 使用 OPL Med Cast 规划、制作、修订和审查医学科普视频，交付审看包并整理已审关键帧资产。
---

# OPL Med Cast

用当前请求确定系列、单集、工作区与交付范围。此智能体提供医学视频专业语义；OPL负责执行、状态、评测和包生命周期。

优先从主机已登记的 OPL 入口调用 `plan-series`、`produce-episodes` 或 `review-delivery`。公开合同见 `contracts/action_catalog.json`；如果还未安装/登记，就在当前获授权会话中使用专业 Skill 与本地辅助程序，说明这不构成 OPL 托管运行或资格通过。

1. 以 `workspace_root` 定位制作工作台，读取 workbench.yaml 与当前选集制作单。用仓库的 `runtime/native_helpers/medcast.py inspect --workspace <绝对路径>` 只读检查可用路径；不要把当前 cwd 当作制作工作区。
2. 选题与证据交 `agent/professional_skills/medical-video-content-planner/SKILL.md`；故事、画面解释与时间轴交 `medical-video-director`；真实媒体缺口交 `medical-video-backends`。具体路径见 `agent/stages/manifest.json`。
3. 成片和候选交 `medical-video-visual-qa`，交付交 `medical-video-release-packager`，跨阶段恢复与资产沉淀交 `medical-video-series-producer`，均位于 `agent/professional_skills/`。
4. 先复用已审资产和未变音轨。精简恢复原任务，保留单一 writer。每项通过状态必须对应真实证据；技术、静态、连续动态、完整听感、医学与上传分开。交付到 publish 表示审看入口，不能据此宣称已上传或可公开发布。

专业 Skill 及 SOP 可按当前任务选择加载，不要求用户重复批准已授权的本地工作。部署、生产媒体生成与发布须符合当前请求范围。详见 `docs/production-sop.md`、`docs/workspace-adapter.md`。
