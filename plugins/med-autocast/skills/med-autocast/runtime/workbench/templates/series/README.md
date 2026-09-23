# 新医学科普系列模板

按[十阶段SOP](../../docs/04_医学科普视频系列SOP.md#0-十阶段流程与交接)执行。先按档案合同选择/建立S01基线，在`workbench.yaml.series`登记作者及系列路径。本目录的`00_brief.md`、`04_series_plan.md`复制到`content_root`，`episodes/NN_slug/`按实际篇目复制并重命名；来源、事实库、患者问题地图、视觉素材库和旁白按[内容方法](../../docs/01_医学科普内容生产.md)产生，不复制旧疾病结论。发布catalog示例放入内容目录并去掉`.example`；制作单和视觉manifest示例应放在对应制作目录，不与内容混放。同一主题多季建议用`content/<topic_id>/<series_id>/`。

本README在新系列中改为该系列入口并填写下表，方法链接改为工作台实际路径；有既有checkpoint时引用它，避免多份独立状态记录。

## 阶段与证据摘要

下表只是填写格式；按当前任务范围新增条目，不预填通过。S01跨系列复用，S02—S04按系列，S05—S09按集；S10交付和持续维护。S09待审可与S10审看包交付并存。

| 对象 | Stage | 输入版本/引用 | 真实状态 | 产物及审核证据路径 | 未完成项与下一步 |
|---|---|---|---|---|---|
| 待填写系列或集ID | 待填写S01—S10 | 待填写 | 待处理 | 待填写 | 待填写 |

阶段摘要不替代事实、故事包、制作单、QA或交付manifest；恢复以其实际证据为准。选题/系列规划请求只交相应阶段成果，不自动启动生产。

## 文件与制作交接

最小结构：

```text
content/<topic_id>/
├── 00_brief.md
├── 01_sources.md
├── 02_fact_library.yaml
├── 03_patient_question_map.md
├── 04_series_plan.md
├── 05_visual_library.yaml
├── 06_release_catalog.yaml
└── episodes/<episode_id>/
    ├── 00_episode_brief.md
    ├── 01_narration.md
    ├── 02_visual_treatment.md
    └── 03_story_package.yaml
```

每篇制作目录为登记的 `<production_root>/<episode_id>/`，新系列建议 `productions/<series_id>/<episode_id>/`。静态分镜放 `animatic/`，候选放 `candidates/`，实际审核结果写入 `visual_delivery_manifest.json`。先合成候选再复核，动画门与技术 QA 通过后确认同一 `final/video.mp4` 为技术交付母版，无须重复合成。最终形态从作者档案读取，医学含义由审定旁白、字幕与必要审定画面负责；纯静态切图、zoom/pan 和 PPT 式变化不具备动画交付资格。

制作单从 `production_plan.example.yaml` 开始，视觉审核清单从 `visual_delivery_manifest.example.json` 开始。每集显式填写 `author_profile` 和 `primary_video_backend`；镜头类型与可生成性根据作者档案和已选后端决定，审定插图使用 `reviewed_visual_insert`。

模板是待填写草案，所有审核从 pending 开始，不能直接复制成通过记录。填写真实 WAV/SRT 路径与时长、每段可用源区间、旁白意图和审核依据；已有合格素材先复用。首篇 `series_visual_role` 写系列基线，不填“已对照上一集”；后续差异化按 [角色 SOP](../../docs/07_角色与视觉差异化SOP.md)。`brand_character_segments` 按实际人物段填写，非空会关闭全部额外头像；没有人物时需禁头像则用 `--no-avatar`。

完整步骤、听感/医学终审边界与单集打包示例以 [新版系列 SOP](../../docs/04_医学科普视频系列SOP.md) 为准。只修画面不重做 WAV/SRT，只修文案不渲染视频；不把历史 ready 提示、文件名或技术门通过当成内容批准。

有明确人物或物件关系时，先审完整关键帧，再生成单一主要动作；图片 API 404 按 [后端 SOP](../../docs/06_媒体后端运行SOP.md#41-场景关键帧与图片-api-故障) 恢复，不能直接跳过参考图。跨篇去重复须看真实源素材，同源裁切不算新镜头；新场景的标签位置须在合成后复核，必要时按区间设置 `visual_annotations.offset`，具体经验见系列 SOP 10.2。
