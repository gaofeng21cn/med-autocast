# OPL Med Cast 架构

正式名OPL Med Cast，技术身份opl-medcast，领域medical_video。agent/持有专业语义，contracts/持有动作、阶段、身份与边界。工作区持有系列、媒体、部署profile、资产catalog和质量记录。runtime/native_helpers仅提供只读机械检查，不成为第二调度器或医学裁决者。

plan-series进入证据规划；produce-episodes进入故事导演、媒体制作与审查交付；review-delivery进入复核、交付和资产沉淀。已有结果可跳转或返修，stage.requires是质量上下文。受权限、身份及当前性约束的依赖动作不能越界。

OPL负责运行、阶段状态、生成接口、独立评测、包版本和激活。本仓不拥有OPL标准，不生成伪owner回执。六个专业Skill分工继承工作台经验，与OPL Book Forge保持相同层次。
