# H3 医学视频提示设计

适用：导演为 H3 新镜头写提示或定位提示问题时读取。依据 MiniMax 官方 [Prompt Skill](https://github.com/MiniMax-AI/MiniMax-H3/blob/d21241f0a4b3acbb34c97dae47fa417b7065e438/skills/h3-prompt-writing/SKILL.md)，固定版本 `d21241f0a4b3acbb34c97dae47fa417b7065e438`（2026-08-15）。这是保留上游来源的本项目适配，未安装或改写官方 Skill，也不复刻托管 Context-IR。

## 先完成中文导演卡

先按[连续性SOP第0.4节](../../../../runtime/workbench/docs/11_解释对应与叙事连续性SOP.md#04-先保证下限再增加效果)确认基础素材及实际可用区间、新生成希望增加什么、失败接回哪里，再记录同期旁白、参考图、开场、一次变化、可用落点和前后连接。只有“需要一个好镜头”而没有可执行替代时先补基础表达。中文导演卡负责医学含义；英文提示不增加事实或建议。

例如“少盐也要关注调味品”：同一厨房的调味瓶已在手旁 -> 患者收起瓶子 -> 注意力回到原菜肴。这个动作表达减少额外调味，不能冒充展示了包装钠含量比较；比较需要另一个包装近景，由后期放相同单位的审定示例。

## 按实际输入选择模式

人物构图反例（2026-09-08）：`teal-shirted torso ... in the background`直接引入无头躯干，`pushes in ... retaining the entire dish and both hands`没有保护头部；已生成视频出现了相应问题。完整首帧不补救错误的终点构图要求。优先中景和固定机位；可用正向构图描述：`A medium-wide shot keeps the man's entire head, both hands and the dish visible throughout the action, with clear space above his hair. The camera holds its position as he places the green garnish onto the dish.` 这段是修订示例，未作为新请求验证；采用前仍须核对实际首帧和模型输出。详见[构图复盘](../../../../runtime/workbench/docs/production-lessons.md)。

| 模式 | 输入含义 | 提示结构 |
| --- | --- | --- |
| T2VA | 无参考图片 | 直接三个基础字段 |
| I2VA | 一张实际首帧 | 首帧对齐说明 + 三个基础字段 |
| FL2VA | 真实首帧和独立尾帧 | 两端对齐说明 + 两帧间的连续路径 + 三个基础字段 |
| L2VA | 只有尾帧 | 尾帧对齐说明 + 合理开场至尾帧的路径；当前排队器尚未实现此路线 |
| Ref2VA | 身份、风格、动作或编辑源等参考 | 使用对应权重/节点与六段格式，不把I2VA的一张首帧称为Ref2VA |

基础格式见[上游base指南](https://github.com/MiniMax-AI/MiniMax-H3/blob/d21241f0a4b3acbb34c97dae47fa417b7065e438/skills/h3-prompt-writing/references/base-en.txt)，高级参考模式再读[上游ref指南](https://github.com/MiniMax-AI/MiniMax-H3/blob/d21241f0a4b3acbb34c97dae47fa417b7065e438/skills/h3-prompt-writing/references/ref-en.txt)。按意图选择，不因能输入多张图就假定支持全部模式。

## I2VA 完整示例

下面是待验证的提示设计，不是已执行回执。只有实际首帧与描述一致时才使用；源图不含这些物体时先改图或改描述。

```text
For the target video, at 0.00 seconds into the target video, <Picture 1> (from [Shot 1]) is fully referenced.

integrated_multimodal_description: [Shot 1] A 2D watercolor illustration with soft paper texture and clear hand-drawn contours continues from <Picture 1>. In the established kitchen, the patient in the teal top stands at the counter, with the seasoning bottle beside the right hand and the prepared vegetable dish in front. The patient lifts the bottle, places it on the shelf behind the counter, and brings the empty hand back beside the dish. The bottle stays on the shelf. The camera holds a static medium shot, keeping the hand, bottle and dish visible throughout the action. The clothing, kitchen layout and dish remain consistent with the opening image. The patient remains silent.

overall_soundscape: Quiet kitchen room tone, a light bottle contact on the shelf and soft clothing movement.

non_diegetic_music: N/A
```

这段用静机位是为了看清拿放，但提示不保证保持构图。当前测量姿势讲到脚、背、手臂时，用已审全景和固定局部剪辑；不依赖H3推镜精确停在某部位。生活镜头运镜可作增强，必须有失败仍成立的基础表达。原生运镜和静态图缩放分开登记，队列包装器不能再追加冲突的locked-camera。

首镜写 `[Shot 1]`，不加时间。确有第二镜时写 `[Shot 2] At 00:03.500, the camera cuts to ...`，切点递增且在实际时长内。一般外部剪辑比在一个请求中塞跨地点剧情容易复核，但多镜不是模型禁用能力。

## FL2VA 与 Ref2VA

FL2VA 首行按实际末镜编号和有效时长替换：

```text
How the reference pictures align with the target video — Picture 1 (from Shot 1) aligns with the 0.00-second mark of the target video; Picture 2 (from Shot 1) aligns with the S.SS-second mark of the target video.
```

`S.SS` 是模板占位，发送前必须替换；视频按24fps及17k+5帧网格生成，核对实际帧数、尾帧位置与输出时长，不能只用请求的整数秒推断剪辑长度。正文描述从首帧到尾帧的真实动作，不能只重复两张图片，也不能同时要求位置完全不变。需要一次性移动时，不用同一张图锁住两端。

Ref2VA 使用以下顺序，具体标签与内容关系按上游指南完成，不把空字段示例送给模型：

```text
subject_definitions: ...
summary: ...
retention_analysis: ...
detailed_description: [Shot 1] ...
overall_soundscape: ...
non_diegetic_music: ...
```

`<Subject N>` 定义被引用的人物/物体/风格等内容；`<Picture N>` 定义实际帧或规划锚点；`<Video N>` 描述整体编辑或连续性来源；`<Audio N>` 描述声音引用。编号在全文与真实上传列表一致。角色、风格和动作可以来自不同资产，明确哪项保留、哪项变化，不以“严格参考全部图片”含糊代替。

## 本项目声音与文字适配

正式医学旁白保持独立音轨。上例允许模型生成环境声，合成默认不用该音轨；无背景配乐写 `non_diegetic_music: N/A`。只有确实要求整段完全静音时，`overall_soundscape` 才写 `N/A`。环境声字段保留不代表必须使用它，也不保证模型绝不产生其他声音。

不要求生成可读中文、血压阈值或品牌。要读数或标签时直接切固定设备、包装、记录近景后排准确文字；不指望模型一直留白，也不默认跟踪变形或被手遮住的屏幕。身份约束只写有关特征，不堆禁词。医学旁白保持独立，口型与原生朗读不进入当前必需能力。

## 失败后不继续扩写提示

袖带结构、医疗姿势、屏幕和手物交互已有失败证据时，先改职责分配。新动作默认一次，只有明确输入/调用缺陷最多一次定向修正；改图、seed或模式按同一观看任务累计。约4-6秒预期可用动作可作起点，不将长旁白直接变成长请求。需要精准结果时接审定结果画面；需要安装教学时先取得准确示范素材。更多形容词、禁令或官方字段不能提供精确性保证。

## 交给后端前

检查实际参考图、模式、首尾时间、正向动作、运镜与锁定约束是否互相一致；观察任务是否与同期旁白相符。确定性检查守标签、时码与输入完整性，导演负责语义。保存编写稿和最终发送稿的关系。

截至2026-09-07，`scripts/queue_h3_shots.py` 已增加 `official_prompt` 完整直通、模式核对与 `sampling` 明确参数，`--dry-run` 可输出实际图；提交时保存回执并恢复原任务。旧 `motion_prompt` 保留历史包装，不将本页完整格式塞入旧字段。第5集已取得608×352、Turbo8和常规20步的实际输出，未观察到足以推广20步的明确动作收益；不能从小样本宣称新提示普遍提高成功率。当前按用户要求先旧尺寸完成内容与形式迭代。
