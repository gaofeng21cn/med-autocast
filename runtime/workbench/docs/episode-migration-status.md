# 逐集独立导演迁移状态

更新：2026-10-14（本轮：血脂、科学减重、垂体瘤、甲亢；桥本推进中）

架构规则：每集独立 `episodeshots.ts` 与只含本集镜头的 `scene_directions.json`；跨集只共享
kit 原语与纸件资产。**共用工厂是缺陷，不是可选项。** 判定由
`scripts/check_episode_independence.py` 给出，报告在 `work/episode-independence.json`。

## 全局进度（89 集）

| 系列 | 集数 | 已独立 | 剩余 |
| --- | --- | --- | --- |
| pituitary_paper_theatre | 12 | 12 | 0 |
| diabetes_paper_theatre | 11 | 11 | 0 |
| hypertension_paper_theatre | 9 | 9 | 0 |
| gout_paper_theatre | 8 | 8 | 0 |
| lipids_paper_theatre | 8 | 8 | 0 |
| weight_management_paper_theatre | 8 | 8 | 0 |
| graves_paper_theatre | 7 | 7 | 0 |
| hashimoto_paper_theatre | 6 | 2 | 4 |
| breast_nodules_paper_theatre | 6 | 0 | 6 |
| pcos_paper_theatre | 7 | 0 | 7 |
| ckd_paper_theatre | 7 | 0 | 7 |
| **合计** | **89** | **65** | **24** |

尚未独立的 24 集仍是旧系列工厂版本，画面质量停留在旧水平，不计入已优化：
桥本 4（03–06）、乳腺 6、多囊 7、肾病 7。

## 本轮完成

- 血脂 8 集：独立导演稿 + 渲染 + 发布（`publish/血脂异常`）。
- 科学减重 8 集：独立导演稿 + 渲染 + 发布；06 修复一处 `img()` 未登记素材导致的渲染失败。
- 垂体瘤 11 集（含 e00 与 09 分层解剖返修）：独立导演稿，旧工厂与相互引用的孤儿模块全部清除。
- 甲亢 7 集：独立导演稿。
- 桥本 01–02：独立导演稿。

## 每集的共同做法

- 读本集 beats 独立决定空间、动作因果与相机；镜头 id 与 `score.json` 一致；
- 纸景房间来自 `kit/rooms.ts` 的 `paperRoom()`，不使用实景照片背景；
- 餐食、餐具与记录纸来自 `kit/tableware.ts`；
- 引用的素材必须在本集 `asset_manifest` 中（`s.image()` 与 `img()` 两种写法都校验）；
- 迁移用 `scripts/migrate_episode_director.py`：装 kit、改 `main.ts`、生成本集导演稿、
  按 import 可达性删除旧工厂与孤儿模块并构建验证。
