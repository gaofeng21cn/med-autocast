# 逐集独立导演迁移状态

更新：2026-10-14 · **89/89 集全部完成逐集独立导演，并全部渲染发布**

架构规则：每集独立 `episodeshots.ts` 与只含本集镜头的 `scene_directions.json`；跨集只共享
kit 原语与纸件资产。**共用工厂是缺陷，不是可选项。** 判定由
`scripts/check_episode_independence.py` 给出：`duplicated_direction_groups: 0`、
`duplicated_shot_groups: 0`、`verdict: ok`（89 集全部拥有自己的镜头实现）。

## 全局进度（89 集）

| 系列 | 集数 | 已独立 | 渲染发布 |
| --- | --- | --- | --- |
| pituitary_paper_theatre | 12 | 12 | 12 |
| diabetes_paper_theatre | 11 | 11 | 11 |
| hypertension_paper_theatre | 9 | 9 | 9 |
| gout_paper_theatre | 8 | 8 | 8 |
| lipids_paper_theatre | 8 | 8 | 8 |
| weight_management_paper_theatre | 8 | 8 | 8 |
| graves_paper_theatre | 7 | 7 | 7 |
| hashimoto_paper_theatre | 6 | 6 | 6 |
| breast_nodules_paper_theatre | 6 | 6 | 6 |
| pcos_paper_theatre | 7 | 7 | 7 |
| ckd_paper_theatre | 7 | 7 | 7 |
| **合计** | **89** | **89** | **89** |

`publish/` 下11 个系列目录合计 89 集，均为本轮之后的成片。

目视复核中修掉的两处构图问题（已重渲染发布）：乳腺 03 第一镜三张检查纸压住解剖图与彼此
的标签，改为排在解剖图下方；甲亢 06 第二镜三张评估纸飞行途中叠成空白卡，改为错落
起点与落位。

## 迁移过程中修复并沉淀的真实缺陷

1. 系列镜头工厂（`six_shots` / `story_shots` / `hypertension_shots` / `lipid_shots` /
   `field-director` 等）：改为按结构识别并清除；
2. 相互引用的孤儿模块（`anatomy.ts` ↔ `props.ts` ↔ `route.ts`）：改为 import 可达性清理；
3. 素材引用只校验了 `s.image()`，漏掉 `img(s,'…')`，导致整集渲染失败：两种写法都校验；
4. 导演镜头 id 与 `score.json` 不一致导致渲染为空：迁移即校验；
5. 重复写入的 `};`：自动清理；
6. 旧工厂遗留的实景照片背景、照片切图食物、跨系列素材引用：逐集换成本集纸景与本集素材。

以上规则已进入 `docs/34_逐集独立导演与系列资产分层SOP.md` 与 MAC 智能体随包脚本，
工具层不再允许共用工厂回流。
