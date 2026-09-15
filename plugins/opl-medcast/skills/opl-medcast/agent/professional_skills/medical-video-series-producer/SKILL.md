---
name: medical-video-series-producer
description: 恢复医学视频系列任务、统筹阶段交接并沉淀已审关键帧资产。
---

# medical-video-series-producer

只处理当前请求范围。先解析明确的 `workspace_root`，所有制作数据、配置与媒体相对它定位；仓库只持有可复用方法，不读取无关凭据。OPL负责阶段运行，本 Skill 不创建调度器。

只收实际查看且值得复用的关键帧，按用途分类，以工作区 catalog 为权威，记录来源、审查范围与复用限制。把实证失败规则补入当前专业 SOP。 输出：资产索引更新、复用记录与经验修订。质量判断：是否复制了无价值图片；能否回溯原图；静态参考是否仍保留关联视频拒用决定；是否把历史项目特例写成通用硬限制。

跨阶段从精简checkpoint、原队列和当前期望清单恢复，不能整段导入图片对话或另起 runner。资产按用途组织，catalog是唯一索引；审过且有价值才入库，保留原图、来源、拒用源视频决定和跨篇复用限制。详见 [资产协议](../../../docs/keyframe-library.md)、[恢复 SOP](../../../docs/recovery-sop.md)。

通用规则：[领域边界](../../knowledge/domain_boundary.md)。原始专业经验来源见 [来源说明](../../../docs/provenance.md)。
