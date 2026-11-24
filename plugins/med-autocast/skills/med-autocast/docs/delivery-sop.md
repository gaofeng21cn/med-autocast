# 制作与交付运维 SOP

本文归口媒体后端调度、视听复核、中断恢复以及成片打包与双平台交付的长期运维边界。专业实现见[成片与发布 Skill](../agent/professional_skills/medical-video-release-packager/SKILL.md)及[系列 SOP 第 7 节](../runtime/workbench/docs/04_医学科普视频系列SOP.md#7-发布交付)。

## 媒体后端运行

能力协议由后端目录持有，实例、模型、默认选择和密钥来源由制作工作区的部署 profile 持有；Agent 不硬编码某台 GPU 或云服务。现有工作区的生产默认值不因安装 Agent 而改写。

在 `workspace_root` 下检查 `scripts/media_backend.py` 的帮助和 `resolve` 入口，再读登记 SOP；只有需要当前服务诊断时才执行 `doctor`。对未知入口先读实现及副作用，不能从配置任意执行命令。真实生成前核对已审首帧、完整提示、参考资产在服务端的真实引用、帧数、分辨率和模型限制。

按同一观看任务累计生成预算，默认一次；明确输入或调用缺陷最多一次定向修正。更换 seed、提示或首帧不重置累计预算。未知能力实验单独立项，不挤占整季交付；模型漂移交导演更换已审方案，不随机重抽。

异步提交保存原任务 ID 和精确产物引用，断流先查 queue/history。错误返回先分清已生成但解码失败、未生成、服务不可达，避免重复计费。不将完整 base64、image_url、凭据或生成响应写入对话/回执。媒体实际下载后用 `ffprobe` 验证解码、时长、尺寸和流，再审实际内容；视频自带音轨被后期丢弃不等于已禁用模型音频采样。

## 视听复核

先核对当前制作单、源片审查决定和整段旁白。机器守路径、区间与状态，AI 判断解释对应和连续性。

- 源片 `accepted=false` 绝对优先于 `usable_range`；残留范围不能重新启用被拒视频。
- 审完整采用区间，并查入出点和相邻镜头。人物头顶、面部、手部、医疗设备、表盘或数字等关键细节看实际尺寸；联系表只定位，不能替代批准。
- 只剩短区间时重编整个叙事段，检查碎镜、跳切、主体变化与观看任务；不循环或长冻结凑时长。
- 对跨集多样性看真实源、场景和讲述作用，不能用裁切、改名或开头几秒变化冒充不同。
- 静态关键帧、源视频区间、`continuous_motion`、成片 `technical`、`visual`、完整 `listening`、`medical` 分别记录。缺证据写 `pending`；不把抽帧检查称作完整动态审看，不把音频文件存在称作完整听审。

默认后台检查，不自动打开播放器或发声。需要完整听审而当前不允许发声时，保留 `pending` 并交付明确待听项。发现构图或医学源问题，查询所有使用处，逐项修订并重查切点，不能只改首处。

媒体审看 MiniApp 是审看入口和意见采集面。它可以定位当前 Score 的镜头、打开精确 artifact 区间并回读已有意见，但不在页面内认定“通过”、改变质量债务或授权发布。页面关闭、刷新或切换不会取消当前制作；意见写入后仍由 Visual Review、Meta Review 和既有阶段控制器决定后续路线。

## 中断恢复

卡顿或 413 时只恢复精简 checkpoint、当前任务/队列 ID、实际产物路径和剩余目标，不导入整段旧对话、base64 或批量图片。

先核对原 runner 是否仍在执行、原 queue/history 和精确输出；存在 writer 就沿用，不重起第二个。以本次期望处理清单判断结束，旧 `ready` 汇总不代表新增任务已完成。已有有效产物不重跑 smoke 或重新生成。

恢复记录包括当前选集与修订、唯一执行者/任务 ID、每集已完成和剩余项、下一条可执行动作、证据路径。令牌或会话恢复不能改变审查状态、重置生成预算或默认授权发布。OMA 工程请求同样保存 `request_id` 及真实 `FoundryRun`（如果有）；启动前失败只记录失败，不编造 run 或蓝图，修复入口身份后复用同一 `request_id` 查询持久状态避免重复执行。

## 成片与双平台交付

先确定当前制作单和母版，确认包器匹配当前修订，不能默认根制作单或 `final` 比 `review` 更新。S08 使用原通用合成器落实画布、字幕、固定品牌、头像策略与 BGM 混音；S09 分别回读技术、构图、语义、连续动态、完整听感和医学审核，当前母版不直接继承被替换版本的构图复核。

S10 文案只在登记 `release_catalog` 维护，含义变化交内容策划回溯事实和故事包；包器只物化。每集至少交付 `video.mp4`、`小红书文案.txt`、`微信视频号文案.txt`、`发布交付包.md`；根据原合同附字幕、审看/技术记录及系列 manifest。复制后回读视频字节、字幕、文案全文和版本，不重渲染已审母版；只改画面时比较整段解码音轨，不以 WAV 路径未变代替。

默认用 [preflight-workbench](workspace-adapter.md#直接读取原制作单和交付包) 读取原合同；检查通过只证明对应引用和字节一致。审看包保留欠项，可按授权进入登记的 `publish_root`；不能另建平行交付入口。旧交付保留恢复路径，单集更新不覆盖其他集；公开上传需当前授权和平台回执，技术通过或进入 `publish` 不等于医学、听感或上传完成。

全季交付时按每集的当前制作单、`out/current.json`、内部交付 manifest 和 publish 视频逐一回读。历史交付归档到工作台 `archive/deliveries/<series>/<episode>/<revision>/`，位于用户交付目录之外。Progress First 下，文档或单个回读失败时保留已有审看包并记录质量债务，修复 owner 后继续。

### 面向用户的单一最新版交付

`publish/<系列展示名>/` 是唯一面向用户的交付目录：首页/观看页和各集成片。每集直接放 `video.mp4`、`封面.jpg`（可用时）、字幕、两平台 TXT 和简明交付说明；不放 `current/`、日期/版本子目录、旧版、源码、旁白 WAV、Score、预览或 QA。用户无需在版本间挑选；交付位置不改变原有动态、听感、医学或上传状态。

过程材料保存在 `deliveries/<series>/stages/<stage_id>/`，精确交付 manifest 位于 `deliveries/<series>/<episode>/manifest.json`，用户最新版指针由 `deliveries/<series>/<episode>.json` 记录。旧包完整移到 `archive/deliveries/<series>/<episode>/<revision>/` 后再安装新包并回读。

代码动画用 `paper_project package` 默认替换本集唯一最新版并在交付目录外保留旧包；`--output` 只用于交付目录外的过程导出。旧多版本纸剧场包可运行 `scripts/organize_delivery.py --workspace <工作区> --series <系列>`，只按精确指针整理。

用户入口按主题和集名组织：`publish/观看与发布.html` 覆盖全部当前系列；展示名映射见 `workbench.yaml.series.<series_id>.delivery`，内部 `series_id`/`episode_id` 保持不变。`publish_catalog` 更新观看页与全季 TXT 文案合集（`--check` 只读检查实际链接，`--migrate` 配合显式选集迁移）；单集更换从 `delivery_layout.locations` 定位。标准方法见[用户交付目录与导航 SOP](../runtime/workbench/docs/30_用户交付目录与导航SOP.md)。
