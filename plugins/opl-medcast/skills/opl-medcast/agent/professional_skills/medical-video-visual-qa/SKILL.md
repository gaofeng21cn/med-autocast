---
name: medical-video-visual-qa
description: 审查医学视频的解释对应、构图、连续动态、字幕和听感并分层记录状态。
---

# medical-video-visual-qa

只处理当前请求范围。先解析明确的 `workspace_root`，所有制作数据、配置与媒体相对它定位；仓库只持有可复用方法，不读取无关凭据。OPL负责阶段运行，本 Skill 不创建调度器。

背景方式检查完整源区间及成片切点，临界细节看原尺寸逐帧；按需求完成连续动态与完整听感复核，另行记录医学复核。 输出：逐项复核决定、可用区间、待审状态与精确返修目标。质量判断：人物头部与手部、医学细节、运动连续性、字幕和旁白是否一致；静态筛选是否被误记成动态或医学通过。

accepted=false 优先于残留 usable_range；完整区间和边界全部检查，所有人物头部都在检查范围。联系表用于定位，不能批准细节、连续动态或医学正确性。未经完整听审保持 listening=pending。详见 [视听检查](../../../docs/visual-review-sop.md)。

通用规则：[领域边界](../../knowledge/domain_boundary.md)。原始专业经验来源见 [来源说明](../../../docs/provenance.md)。
