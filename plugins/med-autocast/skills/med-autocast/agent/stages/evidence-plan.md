# 医学证据与系列规划

根据受众问题、现有资料和医学证据组织系列与单集范围；记录结论来源、适用人群、日期与不确定性，不把风险关联讲成因果。

输入为当前请求、工作区配置和上一阶段可用结果。输出：系列卡、证据表、单集目标与待核问题。已有结果可直接进入本阶段，资料缺项记录为待处理问题；身份、权限与当前版本不一致时停止依赖该条件的动作。按任务语义决定前进或返修，不启动第二 writer。

专业入口：`agent/professional_skills/medical-video-content-planner/SKILL.md`。

## 原工作台职责与专业交接

覆盖 S01—S04：作者表达基线、患者需求、事实库与引用、系列边界和代表样片。

- `agent/professional_skills/medical-video-series-producer/SKILL.md`
- `agent/professional_skills/medical-video-content-planner/SKILL.md`
- `agent/professional_skills/medical-video-director/SKILL.md`

先读 `docs/production-sop.md` 的阶段映射；按 `docs/workspace-adapter.md` 选择实际工具和原输入合同。后续补充或返修从受影响职责继续，不为六阶段顺序重复制作。
