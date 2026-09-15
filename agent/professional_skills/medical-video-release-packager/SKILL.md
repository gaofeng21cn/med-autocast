---
name: medical-video-release-packager
description: 校对当前制作单并组织医学视频审看交付包。
---

# medical-video-release-packager

只处理当前请求范围。先解析明确的 `workspace_root`，所有制作数据、配置与媒体相对它定位；仓库只持有可复用方法，不读取无关凭据。OPL负责阶段运行，本 Skill 不创建调度器。

以当前选集、制作单和修订版为准，把母版、字幕、配音与 QA 交付到工作区正式 publish 审看入口。先预检再复制，保留旧交付恢复路径。 输出：审看包、逐集状态与缺项、交付清单。质量判断：集数/版本/路径是否同源当前；旧包器是否回退新版；技术通过是否错误宣称完整听感、医学或上传完成。

先用 medcast.py preflight 对齐外部当前制作单与选集；通过只表示确定性预检。复核工作区包器是否支持当前修订版，再运行，不能默认旧 v1 包器适用于新母版。审看交付允许明确质量欠项；上传需当前授权并独立回读。详见 [交付 SOP](../../../docs/delivery-sop.md)。

通用规则：[领域边界](../../knowledge/domain_boundary.md)。原始专业经验来源见 [来源说明](../../../docs/provenance.md)。
