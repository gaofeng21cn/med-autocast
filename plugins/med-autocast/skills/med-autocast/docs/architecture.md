# Med Auto Cast 架构

正式名Med Auto Cast，技术身份med-autocast，领域medical_video。agent/持有专业语义，contracts/持有动作、阶段、身份与边界。工作区持有系列、媒体、部署profile、资产catalog和质量记录。runtime/native_helpers 提供只读核对与显式工具寻址；workbench_tool 同步执行一个已授权工具，不成为第二调度器或医学裁决者。runtime/workbench 随包提供通用核心、模板和完整方法，工作区原工具优先。

`plan-series` 进入证据规划；`produce-episodes` 进入故事导演、媒体制作、阶段复核、跨阶段 Meta Review 和审看交付；`review-delivery` 从阶段复核进入同一条 Meta Review/交付路线。`asset-curation` 是交付后的可选沉淀与恢复入口，不是成片交付的硬终点。已有结果可跳转或返修，`stage.requires`、能力包和产物字段都是质量上下文与交接建议，不是 LLM 输出不完整时的启动门。受权限、身份及当前性约束的依赖动作不能越界。

## Stage 能力与交接

阶段定位由 `agent/stages/manifest.json` 给出；每个 Stage 通过 `contracts/stage_capability_bundle.json` 关联建议的工作包、输入/输出产物、工具、Review 范围和 route-back 目标。Stage prompt、专业 Skill、quality gate 与工具入口仍各自保持单一职责，能力包只帮助 OPL 选择和交接，不创建第二调度器。

六个主阶段按责任变化组织，不把每个素材或编码动作都拆成独立 Stage：Evidence Plan、Story Directing、Media Production、Visual Review、Meta Review、Review Handoff；`asset-curation` 是交付后的可选沉淀。主路线让内容、导演、制作、审查和交付的责任清楚，同时保留模型按现有产物跳步、回退或合并执行的空间。Stage 的 `requires`、输入输出建议及下一阶段建议用于定位和说明，不作为缺字段即停止的门槛。

每次阶段返回优先给出可继续消费的 `artifact_refs`，并可附 `artifact_envelopes`、`stage_run_ref`、`next_stage_recommendation`、`quality_debt_items` 与 `route_back`。需要交接时可引用 OPL 生成的 `owner_receipt_ref`、`typed_blocker_ref`、`human_gate_ref`、`route_back_ref` 或 `memory_ref`；这些是可选引用，Med Auto Cast 不伪造回执正文，也不把引用缺失当成不能继续。质量债务随结果传给后续 Stage；它可以限制 ready、医学批准或发布声明，但不限制消费已有结果。

交付参考 RedCube 对 deliverable goal、review surface 与 export bundle 的分层：Med Auto Cast 将请求目标、候选版本、实际 Review 范围、未解决债务和交付包分别说明，作为建议而非固定产物 schema。可按用户和工作区目标调整文件组合；候选交付不等于医学批准或公开发布。领域报告和 OPL 回执分开命名：`stage_review_report`/`meta_review_report` 是可读产物，OPL formal receipt 由运行框架持有。Meta Review 中 `route_analysis` 是理由材料；实际终局 Stage 转换只由 decisive Attempt 的 `route_impact.stage_route_decision` 承载，缺失时保留产物、记路由质量债并按 OPL 默认推进。

常规 Stage 的质量循环由 OPL 按 `producer -> reviewer -> repairer -> re-reviewer` 策略执行。标记为 `cross_stage_meta_review` 的 `meta-review` 是一次独立跨阶段判断，不再递归触发另一轮 formal review；它比较患者任务、证据、导演意图、实际候选和各阶段结果，找出最早责任 Stage，并输出建议的 outcome 与 route。它不签发医学批准、发布授权、owner receipt 或 production-ready 声明；可消费结果仍可继续推进。

## 内容与渲染分离

所有动画风格共享 `Score / Shot / Asset / Layout / Review` 合同，风格选择通过 `style_id`，画面实现通过 `renderer`：

```text
Score / Shot / Asset / Layout / Review
                    ↓
            renderer adapter
     ├── canvas2d      (当前 paper_collage 默认)
     ├── svg            (线条、图解和形变)
     ├── remotion_dom   (React/DOM 排版与装配)
     └── webgl_three    (2.5D、粒子和三维结构)
```

当前共用渲染入口按 HTML 项目的 `window.__seek(t)` 逐帧捕获；随包完整模板是 Canvas 2D，故 `paper_collage + canvas2d` 为稳定默认。renderer 注册表区分已激活、计划和实验项；renderer ID 不会自动安装或切换实现。未激活实现仍可用于前期导演规划，之后可选兼容的已激活 renderer 并如实记录质量债务，不能把计划项报告成已渲染。Remotion 与 HyperFrames 可作镜头预览、薄装配或特定 renderer 候选，不另建主时间轴；视频模型属于显式选择的后端能力，不是动画风格。

OPL负责运行、阶段状态、生成接口、独立评测、包版本和激活。本仓不拥有OPL标准，不生成伪owner回执。六个专业Skill分工继承工作台经验，与OPL Book Forge保持相同层次。

原十阶段与六个 OPL 阶段的完整职责对应见 [制作 SOP](production-sop.md)，实际工具和输入合同见 [工作台接入](workspace-adapter.md)。同一个专业 Skill 可以参与多个阶段；合成由成片打包 Skill 实现，不能只交给后端 Skill。
