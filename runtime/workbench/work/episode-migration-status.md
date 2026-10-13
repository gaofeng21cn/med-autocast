# 逐集独立导演迁移状态

更新：2026-10-14

架构规则：每集独立 episodeshots.ts 与只含本集镜头的 scene_directions.json；跨集只共享 kit 原语与纸件资产。判定由 scripts/check_episode_independence.py 给出。

| 系列 | 集数 | 已独立 | 剩余 |
| --- | --- | --- | --- |
| pituitary_paper_theatre | 12 | 1 | 11 |
| diabetes_paper_theatre | 11 | 6 | 5 |
| hypertension_paper_theatre | 9 | 9 | 0 |
| weight_management_paper_theatre | 8 | 0 | 8 |
| lipids_paper_theatre | 8 | 0 | 8 |
| gout_paper_theatre | 8 | 8 | 0 |
| graves_paper_theatre | 7 | 0 | 7 |
| hashimoto_paper_theatre | 6 | 0 | 6 |
| breast_nodules_paper_theatre | 6 | 0 | 6 |
| pcos_paper_theatre | 7 | 0 | 7 |
| ckd_paper_theatre | 7 | 0 | 7 |
| **合计** | **89** | **24** | **65** |

## 已完成系列的共同做法

- 每集读自己的 beats，独立决定空间、动作因果与相机；
- 纸景房间来自 kit/rooms.ts 的 paperRoom()，不再用实景照片背景；
- 餐食、餐具与记录纸来自 kit/tableware.ts 的 paperPlate/paperFood/sheet；
- 动作时点读 score.json 的事件，接触都有阴影；
- 迁移用 scripts/migrate_episode_director.py：装 kit、改 main.ts、生成本集导演稿、删除无人引用的旧工厂文件并构建验证。

## 尚未迁移的系列

垂体瘤 11、糖尿病 5（07/08/09/10/e00）、科学减重 8、血脂 8、甲亢 7、多囊 7、肾病 7、桥本 6、乳腺 6。
这些集目前仍是系列工厂版本，画面质量停留在旧水平，不计入已优化。
