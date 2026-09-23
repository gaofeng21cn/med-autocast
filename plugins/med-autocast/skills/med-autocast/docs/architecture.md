# Med Auto Cast 架构

正式名Med Auto Cast，技术身份med-autocast，领域medical_video。agent/持有专业语义，contracts/持有动作、阶段、身份与边界。工作区持有系列、媒体、部署profile、资产catalog和质量记录。runtime/native_helpers 提供只读核对与显式工具寻址；workbench_tool 同步执行一个已授权工具，不成为第二调度器或医学裁决者。runtime/workbench 随包提供通用核心、模板和完整方法，工作区原工具优先。

plan-series进入证据规划；produce-episodes进入故事导演、媒体制作与审查交付；review-delivery进入复核、交付和资产沉淀。已有结果可跳转或返修，stage.requires是质量上下文。受权限、身份及当前性约束的依赖动作不能越界。

OPL负责运行、阶段状态、生成接口、独立评测、包版本和激活。本仓不拥有OPL标准，不生成伪owner回执。六个专业Skill分工继承工作台经验，与OPL Book Forge保持相同层次。

原十阶段与六个 OPL 阶段的完整职责对应见 [制作 SOP](production-sop.md)，实际工具和输入合同见 [工作台接入](workspace-adapter.md)。同一个专业 Skill 可以参与多个阶段；合成由成片打包 Skill 实现，不能只交给后端 Skill。
