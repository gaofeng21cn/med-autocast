---
name: medical-video-backends
description: 通过制作工作区已登记的媒体后端生成真实缺口并验收媒体回执。
---

# medical-video-backends

只处理当前请求范围。先解析明确的 `workspace_root`，所有制作数据、配置与媒体相对它定位；仓库只持有可复用方法，不读取无关凭据。OPL负责阶段运行，本 Skill 不创建调度器。

先恢复原任务、精确输出与唯一写入者。读取部署 profile，复用音轨和已审源。按真实缺口执行已授权工作区后端入口、轮询原任务并验证输出；剪辑前预检当前制作单。 输出：精确媒体引用、去密回执、剪辑清单、候选成片。质量判断：输入是否为已审首帧和完整提示；任务预算是否累计；拒用源是否排除；旁白未变是否复用；媒体是否实际解码。

`workspace_root` 下先检查 scripts/media_backend.py 与登记 profile，再按工作区已验证的后端 SOP 执行，命令 cwd 必须是工作区。不可把同名本地图片当作服务器已上传引用。服务可达、官方支持及推理日志不等于真实出片。任务中断查原队列，缺陷定向修正最多一次，换seed不重置预算。详见 [后端 SOP](../../../docs/backend-sop.md)。

通用规则：[领域边界](../../knowledge/domain_boundary.md)。原始专业经验来源见 [来源说明](../../../docs/provenance.md)。
