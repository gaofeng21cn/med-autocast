# 跨阶段 Meta Review

先读取当前工作区、当前精确候选和所有可用阶段交接材料。不要按文件名、mtime、旧对话或残留交付猜测当前版本。

把 `episode_blueprint`、证据包、实际旁白/字幕、素材清单、渲染候选、visual-review 结果和已有质量债务放在同一条证据链中检查。先判断患者任务是否仍然成立，再判断阶段 Review 是否覆盖了这个版本，最后判断是否需要回到最早责任阶段。可以消费不完整但有用的结果；缺失输入记录为质量债务或路由建议。

输出一份可继续消费的 Meta Review 报告，推荐包括：`outcome`、`evidence_refs`、`global_goal_fit`、`cross_stage_consistency`、`review_coverage`、`quality_debt_refs`、`defect_owner_matrix`、`route_analysis`、`next_stage_recommendation`。每个 finding 说明精确证据、影响范围、最早 owner stage 和下一步。报告内的 route analysis 解释建议，不直接启动 Stage，也不是 OPL 路由字段的替代物。

允许的 outcome 是 `pass`、`repair_required`、`quality_debt`、`blocked`、`human_gate`。`blocked` 只用于真实执行器、权限、身份/当前性或不可逆授权边界；结构化字段缺失、工具未绑定或模型输出不完整应保留结果并写入 `quality_debt`。Meta Review 不签发医学批准、发布授权、owner receipt 或 production-ready 声明。

本 Stage 本身就是独立的跨阶段评审，不再嵌套另一轮 formal review。直接给出可复核的判断和路由理由；可定位的问题返回最早的 canonical owner stage。实际阶段转换由 OPL 注入的终局 closeout 协议承载：终局 Attempt 使用 `route_impact.stage_route_decision`，其他 Attempt 只给 `route_impact.stage_route_recommendation`。即使材料不完整，只要存在可消费结果也继续交接，并把缺口记录为质量债务；路由缺失只产生路由质量债并按默认推进继续，不得因推荐字段缺失而停止阶段推进。
