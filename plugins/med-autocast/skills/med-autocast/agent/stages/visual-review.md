# 视听与医学复核

背景方式检查完整源区间及成片切点，临界细节看原尺寸逐帧；按需求完成连续动态与完整听感复核，另行记录医学复核。

输入为当前请求、工作区配置和上一阶段可用结果。输出：逐项复核决定、可用区间、待审状态与精确返修目标。已有结果可直接进入本阶段，资料缺项记录为待处理问题；身份、权限与当前版本不一致时停止依赖该条件的动作。按任务语义决定前进或返修，不启动第二 writer。

专业入口：`agent/professional_skills/medical-video-visual-qa/SKILL.md`。

## 原工作台职责与专业交接

覆盖 S09，并回溯 S03—S08：源片、当前合成版本、技术、解释对应、连续动态、完整听感和医生医学审核分别记录。

- `agent/professional_skills/medical-video-visual-qa/SKILL.md`
- `agent/professional_skills/medical-video-release-packager/SKILL.md`
- `agent/professional_skills/medical-video-content-planner/SKILL.md`

先读 `docs/production-sop.md` 的阶段映射；按 `docs/workspace-adapter.md` 选择实际工具和原输入合同。后续补充或返修从受影响职责继续，不为六阶段顺序重复制作。
