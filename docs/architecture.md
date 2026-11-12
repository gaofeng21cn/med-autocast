# Med Auto Cast 架构

正式名Med Auto Cast，技术身份med-autocast，领域medical_video。agent/持有专业语义，contracts/持有动作、阶段、身份与边界。工作区持有系列、媒体、部署profile、资产catalog和质量记录。runtime/native_helpers 提供只读核对与显式工具寻址；workbench_tool 同步执行一个已授权工具，不成为第二调度器或医学裁决者。runtime/workbench 随包提供通用核心、模板和完整方法，工作区原工具优先。

## 知识归属、正文来源与运行记录

通用规则由 [OPL 知识来源与记忆政策](https://github.com/gaofeng21cn/one-person-lab/blob/main/docs/policies/knowledge-source-and-memory-policy.md) 持有。MAC 按知识 v2 合同声明 `scope` 和 `content_kind`；归属、内容性质和物理来源相互独立，`contracts/durable_knowledge_catalog.json` 只登记随包规则。

| 归属 | MAC 中的内容 | 正文与事实来源 |
|---|---|---|
| 产品 | 通用制作方法、领域边界和医学审查要求 | `agent/knowledge/`，随产品版本维护 |
| 用户或团队 | 作者表达偏好、协作规则和团队政策 | 用户已维护的资料库；无个人库时由工作目录保存正文 |
| 主题 | 疾病科普经验、长期系列的表达原则与跨集方法 | 主题知识主源，可在 Obsidian 或制作工作区 |
| 项目 | 某个系列或单集的叙事取舍、设计和已接受经验 | 对应项目的唯一正文位置 |

机制、政策、时点状态与决策可以出现在各个归属范围。当前母版、医学审核和声线许可来自业务原件及其回读；笔记总结保留来源和观察时间，不覆盖工作台事实。声线、形象和品牌执行配置继续由原作者档案维护，知识来源绑定不创建另一套配置。

有个人库、无个人库和混合来源使用同一条 Framework 链路：直接读取授权来源的已接受版本，冻结为本次 StageRun 上下文。工作区保存来源绑定引用、业务产物、提案与回执，不强制复制一份知识全文。生产、审阅、修复消费同一快照；其生命周期由 Framework 管理。

三个公开动作都可处理多集，因此明确声明 `execution_scope.kind: none`。它们保留工作区来源授权，只召回适用的产品、用户或团队、主题知识，不将系列名或任意一集冒充本次项目范围。需要单集项目知识时，直接 Skill 从 `workbench.yaml` 选择真实单集，核对 `project.json` 的系列和集号，再由正式 `workspace_index.json.projects` 找到该真实目录唯一对应的 `project_id`；以该目录作为 `opl knowledge prepare --project` 的路径参数。每集独立 prepare，另一集的私有知识不进入快照。未登记、目录冲突或身份不一致时报告项目知识缺口，不从目录名生成身份，也不回退读取全部项目。

`project-knowledge-locator` 提供上述只读核验；缺少正式登记时，Framework 的 `workspace adopt --project-root` 接入已存在单集目录，MAC 不写另一套 inventory。操作步骤见[单集知识登记](workspace-adapter.md#单集知识登记)。

MAC 判断经验是否值得沉淀及其归属，有权维护者接受后经通用写回机制更新唯一正文。可选经验缺失不阻断独立制作；必需医学依据、作者关键约束或授权缺失限制依赖它的行动。媒体生成与发布前复核关键约束与授权，派生摘要随来源变化重审。素材复用包、原始媒体和项目交付按业务保留规则管理，不随知识缓存或运行日志清理。

## Mini App 工作入口

MAC 的任务与媒体贡献遵循 [OPL MCP Apps 规范](https://github.com/gaofeng21cn/one-person-lab/blob/main/docs/mcp-apps/SPEC.md)。Framework 负责发现、共享进度/产物视图、上下文和当前任务动作；MAC 负责从登记工作区解析单集工程、当前候选、镜头时码与原有审查材料。资产库入口与 MAC 视频制作入口是独立贡献，不互相代替。

当前工程由 `workbench.yaml.series.<series>.episodes.<episode>.project` 决定；当前视频由工程 `out/current.json` 决定。界面不按文件修改时间猜当前版本。只提供工作区时列出已登记单集，选定系列与集号后读取该集；制作中缺少成片仍显示可用工程与 Score。共享产物视图呈现候选媒体和镜头定位，专业制作继续使用既有工作台与工具。

审看意见由 MAC 写入当前工程 `qa/miniapp-notes/`，绑定工程、Score 和当前媒体指针的 revision，供既有 Visual Review、Meta Review 和返修 Stage 读取。意见只是人工输入材料，不是审批、质量状态或第二任务队列；继续制作通过 OPL 当前可用的任务动作发起。连接能力经 OPL Connect 的宿主绑定接口调用，Mini App 不复制凭据或自行认定调用者身份。接口和使用方式见[工作台接入](workspace-adapter.md#mini-app-任务与媒体入口)。

`plan-series` 进入证据规划；`produce-episodes` 进入故事导演、媒体制作、阶段复核、跨阶段 Meta Review 和审看交付；`review-delivery` 从阶段复核进入同一条 Meta Review/交付路线。`asset-curation` 是交付后的可选沉淀与恢复入口，不是成片交付的硬终点。已有结果可跳转或返修，`stage.requires`、能力包和产物字段都是质量上下文与交接建议，不是 LLM 输出不完整时的启动门。受权限、身份及当前性约束的依赖动作不能越界。

### 媒体审看专用 MiniApp

当用户需要在候选视频、镜头时码、交付审查和 revision-bound 意见之间连续切换时，MAC 使用独立标准 MCP App `ui://med-autocast/media-review.html`。`open_media_review` 是只读 launcher，`media_review_note` 仅对 App 可见；两者都通过 `runtime/native_helpers/app_contribution.py` 调用现有 owner 读取与写入路径。媒体候选、Score、交付记录和意见文件仍归 MAC 工作区，MiniApp 不建立第二份媒体索引或质量状态。

该 surface 只提供当前候选、镜头时间线、工作区 artifact bridge、既有意见和意见表单。写意见时必须提交当前 `revision`，owner 负责并发检查、幂等和回读；审看意见是人工输入材料，不等于质量批准、Meta Review 结论或发布授权。没有 MCP App 宿主时，launcher 返回结构化 owner 数据，便于 Agent 继续使用既有工作台。

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

原十阶段与六个 OPL 阶段的完整职责对应见 [制作 SOP](../agent/policies/production-policy.md)，实际工具和输入合同见 [工作台接入](workspace-adapter.md)。同一个专业 Skill 可以参与多个阶段；合成由成片打包 Skill 实现，不能只交给后端 Skill。

媒体审看的加载、空态、错误和内容页都保留同一 OPL Apps 家族标题栏。家族标识与“媒体审看”标题同行；颜色、焦点、按钮和深浅主题遵循 App 持有的视觉契约，领域布局继续保留单集、镜头与审看意见的连续操作。
