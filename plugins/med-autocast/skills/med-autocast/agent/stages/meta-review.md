# 跨阶段 Meta Review

Meta Review 是成片交接前的跨阶段审阅层。它把当前候选、导演意图、医学证据、声音与字幕、阶段 Review 和质量债务放在同一条证据链上，判断整体目标是否仍然成立，并把每个问题归回最早的责任阶段。

它不是第二个医学审核，也不是 `visual-review` 的附属检查。它不签发医学批准、发布授权、owner receipt 或 production-ready 声明；这些边界仍由领域负责人、人工审核和 OPL 运行合同持有。

输入可以是不完整的阶段结果。可消费的候选、分镜、证据或 Review 结果足够时继续审阅；缺少关键材料时输出 `quality_debt`、`route_back` 或 `human_gate`，不要把 LLM 结构不完整本身升级成启动失败。

## 审阅范围

- 患者任务、系列定位和本集故事是否仍被成片清楚表达
- 医学证据、旁白、字幕、视觉隐喻、素材来源和声音基线是否互相一致
- 视觉、连续动作、字幕安全区、完整听感和医学 Review 是否覆盖了当前精确版本
- 已知质量债务是否影响审看、继续修订或 `ready` 声明
- 缺陷最早属于 `evidence-plan`、`story-directing`、`media-production` 还是 `visual-review`

## 输出

推荐写入 `review/meta_review.json`，并携带可读的 `defect_owner_matrix` 和 `route_analysis`。这份文件解释建议的去向；终局 Attempt 的实际 Stage 转换另由 OPL `route_impact.stage_route_decision` 承载，不把运行 ABI 伪装成领域文件合同。结果可以是：

- `pass`：当前整体目标和交接证据足以继续到 `review-handoff`
- `repair_required`：可定位的缺陷应回到最早责任 Stage
- `quality_debt`：已有可消费结果，但证据或质量仍不足以宣称 ready
- `blocked`：只有真实权限、身份、当前性、执行器或不可逆授权边界才使用
- `human_gate`：需要明确的医生、作者或发布负责人决定

阶段提示、专业 Skill、工具和推荐产物由 `contracts/stage_capability_bundle.json` 定位。Meta Review 是一次跨阶段判断，不为自己再启动 `producer -> reviewer -> repairer -> re-reviewer` formal review 循环；常规 Stage 的质量循环仍由 OPL 按原策略执行。
