# 逐集独立导演与系列资产分层 SOP

## 结论（架构规则，不是偏好）

**每一集必须拥有自己的故事、导演稿、分镜和镜头实现。跨集复用的只能是动画原语代码（kit）和纸件资产，不允许共享「导演」。**

历史上工作台存在 `six_shots.ts` / `hypertension_shots.ts` / `story_shots.ts` 这类系列级镜头工厂：76 集共用 3 个渲染工厂，89 集只有 11 份导演稿（每系列一份，连 `intent` 文字都逐字相同）。后果是同一系列每一集都用同样的空间、同样的进入节奏和同样的构图模板，病理学差异和患者决策差异无法进入画面。这不是效率，是把 89 集压成 11 集。

工厂模式从一开始就不应该是可选项。批量工具只负责渲染、打包和记录，不允许代替导演。

## 三层资产分层

| 层 | 是什么 | 是否跨集共享 | 例子 |
| --- | --- | --- | --- |
| 动画原语（kit） | 与内容无关的可控动作与材质代码 | 是 | `arc()`、`unfoldRevealCompareStow()`、`layerReveal()`、`place()`、`contactShadow()`、`cutout()`、`tape()` |
| 纸件词汇（vocabulary） | 怎么画一件纸：器官纸片、资料页、纸袋、夜间空间、药瓶 | 是 | `organ()`、`page()`、`paperFolder()`、`nightSpace()` |
| 导演（director） | 这一集讲什么、镜头怎么排、动作因果是什么 | **否** | `episodeshots.ts`、`scene_directions.json` |

判断标准很简单：把两个不同疾病的集数放在一起，如果它们的镜头代码逐字相同（或仅改了 topic 字符串），就是错的。共享到「只差一个参数」的程度，就已经越界了。

## 每集导演稿必须回答的六个问题

1. 这一集的患者任务是什么？（来自 `episode_stories.yaml` 的 `patient_task`）
2. 五个镜头各自的**空间**是什么？换空间要有理由，不能每镜清空桌面。
3. 每个镜头里**哪个物件先动**、动了之后**引发什么**、结果落在哪里？
4. 镜头**为什么在此刻切走**？下一镜接住了什么？
5. 旁白的这一句落在哪个动作之后？字幕与接触落点是否同拍？
6. 这一集独有的医学表达风险是什么（不能靠外形确诊、不能暗示自测、不能把机制图当答案）？

## 迁移步骤（每集）

1. 读 `content/<series>/paper_s01/episode_stories.yaml` 里本集的 `patient_task`、`beats[].text`、`beats[].directing`。
2. 新建 `src/episodeshots.ts`：本集 5 个镜头各自的空间、动作因果、相机独立撰写。可以 import 词汇层，禁止 import 其他集的镜头文件。
3. 重写 `src/scene_directions.json`：只保留本集镜头，`intent` 写本集真实意图，禁止复制系列级模板。
4. `main.ts` 改为 import `./episodeshots`，删除对本集已不使用的工厂文件的引用。
5. `build` → `render` → 抽帧目视：至少检查每镜的进入帧、动作极值、接触落点和切出帧。
6. `package` 发布，再跑 `scripts/check_episode_independence.py`。

## 架构门：独立性检查

`scripts/check_episode_independence.py` 按内容哈希检查：

- 导演稿（`scene_directions.json`）不得跨集逐字相同；
- 除词汇层白名单（`series_grammar.ts`、`paper_objects.ts`、`six_objects.ts`、`meal_objects.ts`、`main.ts`）和 `kit/` 外，任何 `.ts` 文件不得跨集逐字相同。

它返回 `blocked` 时不是要卡死流程（Progress First），而是把重复集列为必须返修的项写进 `work/episode-independence.json`；发布清单必须显示这些集没有独立导演。内容判断仍由导演和审片负责，脚本只守架构身份。

## 允许共享什么（明确边界）

- **纸景板**：同一间诊室纸景可以跨集复用，像剧场里同一套布景；但镜头怎么用它、里面放什么、怎么动，必须每集独立。
- **纸件词汇函数**：`page()` 怎么画一页资料是共享的；把化验单和记录夹进同一个资料袋是本集导演动作。
- **kit 原语**：`arc()` 怎么走是共享的；本集从哪到哪、为什么走、什么时候反应，是导演。

## 批量工具的边界

`optimize_current_episodes.py`、`install_series_grammar.py` 只能做 build/render/package 和语法下限安装。它们**不得**生成或改写镜头内容。任何脚本生成的镜头都必须经导演审读后才算一集的导演稿。

## 相关文档

- `docs/26_代码动画技法与风格工作流.md`：kit 原语与媒介技法

## 迁移工具的硬化（2026-10-14 实做记录）

把 60 集从系列工厂迁到逐集导演的过程里，工具暴露出四类真实缺陷，已在
`scripts/migrate_episode_director.py` 与 `scripts/check_episode_independence.py` 中修复，
规则对任何后续制作同样生效：

1. **工厂文件名不统一，不能按名字清理。** 历史上出现过 `six_shots.ts`、`story_shots.ts`、
   `hypertension_shots.ts`、`lipid_shots.ts`、`field-director.ts` 等多种命名。现在改为按
   结构识别：`main.ts` 里任何绑定 `shots` / `makeShot` 的本地 import 一律删除，再由构建
   校验接管。
2. **孤儿模块会互相引用，「有没有人引用我」永远删不掉。** 例如垂体瘤旧工厂留下的
   `anatomy.ts` 与 `props.ts` 相互 import。清理改为从 `main.ts` 与 `episodeshots.ts` 出发
   做 import 可达性分析，删掉一切不可达模块。
3. **素材校验必须覆盖两种写法。** `s.image('id')` 与 `img(s, 'id', …)` 都会在运行时对照本集
   manifest 解析；只查前一种会让 `img()` 引用未登记素材，直到渲染才报「未登记素材」。
4. **镜头 id 必须与 `score.json` 一致。** 导演稿的镜头 id 与评分文件不一致时，画面不报错
   但渲染为空；现在迁移即校验。

本轮实际修复的内容缺陷（都属于「按质量优先重做」时应同步修掉的类型）：实景照片背景、
照片切图的食物、引用其他系列的素材、导演镜头 id 与评分不一致、重复写入的 `};`、以及
一次 `img()` 引用未登记素材导致整集渲染失败。

**结论不变：共用工厂从来不是可选项。** 迁移脚本只负责接线、生成与校验，镜头内容永远由
本集导演撰写；任何一集出现跨集逐字相同的镜头代码或导演稿，都视为该集未完成。
- `docs/35_纸剧场纵深与媒介统一SOP.md`：景深、媒介统一层、环境板要求
- `docs/36_逐集评估与独立改写SOP.md`：逐集评估口径
- `scripts/check_episode_independence.py`：架构门

## 迁移脚本

migrate_episode_director.py 是每集迁移的机械部分：安装当前 kit（纸景房间、纸片餐具、纸片记录纸、纸化背景处理）、把 main.ts 指向本集 episodeshots.ts、按本集故事与代码实际使用的房间生成本集 scene_directions.json、删除无人引用的旧系列工厂文件，并构建验证。脚本不写镜头内容：导演稿由人或模型逐集创作，脚本只保证接线正确、旧工厂不会残留。

已迁移系列的共同做法见 work/episode-migration-status.md。
