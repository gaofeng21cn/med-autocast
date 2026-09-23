# 来源与适配

领域来源：现有“科普视频”工作台的六个medical-video专业Skill，以及docs/04_医学科普视频系列SOP.md、06_媒体后端运行SOP.md、07_角色与视觉差异化SOP.md、11_解释对应与叙事连续性SOP.md、13_剪辑与联合时间轴检查.md。构建输入快照保留在维护者本地恢复档案，不随公开包分发；当前Skill为针对可移植Agent的语义整理，不是原文无差别复制。

结构参考：OPL Book Forge的agent/primary_skill、stages、prompts、professional_skills、knowledge、quality_gates及声明式合同；未复制BookForge历史通过记录。Framework持有标准，Book Forge只是参考。

本仓骨架与carrier由Framework buildStandardDomainAgentScaffold/buildScaffoldFiles生成；主Skill与专业方法由当前获授权开发会话编写。生成工具需要显式OPL_FRAMEWORK_ROOT，不作为Agent运行时依赖。载体主Skill与canonical主Skill字节一致，随包附带领域方法供离线加载。

OMA已调用engineer-agent，但在安装描述符/本机carrier身份一致性校验处失败，没有FoundryRun、AgentBlueprint或EvalSpec。不能将本仓开发成果伪称为OMA运行产物，亦不能将结构检查当作资格通过。精确证据与恢复路径见docs/status.md。

## 工作台能力完整迁移

本次以来源工作台六个 Skill 和 01—13 号专业文档为基线，保留完整职责、交接、H3 提示设计及模板，按目录改写链接并说明案例的适用范围。通用源工具存于 runtime/workbench/scripts；除显式工作区根解析外，原字幕、合成、混音、动画合同、后端提交和文案格式沿用原实现。

新增 workbench_adapter 与 package_review 补充工具寻址、原合同只读核对和不重渲染的单集审看交付。私人 docs/local、作者/部署档案、媒体和权重不分发；其中可移植教训整理为 production-lessons.md。源工作台的 build_remaining_episode_packages.py 仅转交特定旧系列 legacy_tools，不作为通用工具发布；原工作区仍可在对应历史任务中使用它。

专业 Skill、阶段引用和工具不能仅按数量验收。后续维护须检查原职责是否仍有执行者、所需方法和工具能否从安装包定位、现有制作文件是否能直接使用，再验证受影响真实行为。内容方法不能为了缩短主入口而删除；长方法按需加载。原始工作区数据仍是领域事实权威，框架仍拥有 OPL 标准。
