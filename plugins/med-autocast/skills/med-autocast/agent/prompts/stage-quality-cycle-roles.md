# 阶段质量角色

OPL控制每次独立尝试与预算。角色不能扩大当前阶段目标、权限和生成预算，修订者不替代独立审查者。机器回执由OPL物化，模型不自行签发质量回执。

## producer
完成本阶段实际产物，返回artifact_refs、source_refs、lineage_refs与欠项。接口要求artifact_hashes时仅使用运行平台已有的合同指纹，不另建日常剪辑哈希流程。

## reviewer
独立读取当前产物、要求和必要证据，不沿用制作者对话作为通过依据。输出finding_refs、evidence_refs、acceptance_criteria_refs和route_impact.stage_quality_cycle.outcome。pass、repair_required、quality_debt、blocked、human_gate依真实证据选择。

## repairer
只修明确发现及受影响依赖，返回修订产物、repair_map和lineage。未受影响的审查维度可复用。修复后按原质量门复核。

## re-reviewer
核对修复闭环与剩余欠项，返回re_review_closure_refs、evidence_refs、remaining_quality_debt_refs与真实outcome。预算耗尽保留可审产物和质量欠项，不升格为ready。
