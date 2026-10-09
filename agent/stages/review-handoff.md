# 审看包交付

以当前选集、制作单和修订版为准，把最新版视频、字幕、封面和平台文案整理到 publish 用户入口；配音、Score 与 QA 留在过程目录。先预检再复制，保留旧交付恢复路径。

输入为当前请求、工作区配置和上一阶段可用结果。输出：审看包、逐集状态与缺项、交付清单。已有结果可直接进入本阶段，资料缺项记录为待处理问题；身份、权限与当前版本不一致时停止依赖该条件的动作。按任务语义决定前进或返修，不启动第二 writer。

专业入口：`agent/professional_skills/medical-video-release-packager/SKILL.md`。

## 原工作台职责与专业交接

覆盖 S10：使用匹配当前修订的包器，登记文案生成双平台 TXT，复制当前母版、说明、审核与清单并回读。

- `agent/professional_skills/medical-video-release-packager/SKILL.md`
- `agent/professional_skills/medical-video-content-planner/SKILL.md`
- `agent/professional_skills/medical-video-series-producer/SKILL.md`

先读 `docs/production-sop.md` 的阶段映射；按 `docs/workspace-adapter.md` 选择实际工具和原输入合同。后续补充或返修从受影响职责继续，不为六阶段顺序重复制作。

## 用户入口与过程交接分离

输入是当前选定母版、字幕、文案目录和 Review/Meta Review 的可消费结论；缺少任一语义审查时如实标注待审，继续交付已有候选。输出有两个消费面：用户得到 `publish/<series>/` 的首页和每集唯一最新版文件；下一 Stage/返修负责人得到内部 manifest、审查证据、质量债及精确源码引用。不要让用户面对版本选择。

本阶段的自然语言交接可放 `deliveries/<series>/stages/review-handoff/`，机器 manifest 放 `deliveries/<series>/<episode>/manifest.json`。历史交付移到 `archive/deliveries/`，不放在 publish 中。用户入口里只保留直接可观看、可转存、可发布使用的文件与简明状态；正文不堆内部日志和工程信息。
