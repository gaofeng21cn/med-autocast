# 用户交付目录与导航 SOP

用户交付按主题和集名组织。内部使用稳定的 `series_id`、`episode_id` 和制作版本；中文或用户语言的展示名称由内容策划与交付负责人决定并登记，不靠目录排序、修改时间或机器猜标题。标准是让用户直接找到当前作品，而不是理解制作批次。

## 目录与名称权威

```text
publish/
├── 观看与发布.html                     全部当前主题，可搜索主题与集名
├── README.md
└── <系列展示名>/
    ├── 观看入口.html                   各集播放器和视频、文件、文案链接
    ├── README.md
    ├── 全季发布文案.md                 汇总已交付 TXT，不新增医学事实
    └── <集号_标题>/
        ├── video.mp4
        ├── 封面.jpg                    有封面时附上
        ├── subtitles.srt               也兼容已有“字幕.srt”
        ├── 小红书文案.txt
        ├── 微信视频号文案.txt
        └── 发布交付包.md
```

`workbench.yaml.series.<series_id>.publish_root` 指向实际用户主题目录；`delivery.display_name` 保存展示名，`delivery.episode_dirs` 用英文集号映射实际用户目录。名字首次登记后固定；改医学正文或发布标题不会自动重命名已交付目录。显式修改名称时走迁移并同步精确指针。

```yaml
delivery_policy:
  naming: localized_titles
  layout: latest_only
  index: 观看与发布.html
  batch_directories: false
series:
  stable_series_id:
    publish_root: publish/系列展示名
    delivery:
      display_name: 系列展示名
      active: true
      episode_dirs:
        01_stable_id: 01_本集标题
```

本配置是可消费的名称交接，缺少展示名时继续按已有明确路径交付候选；不把中文、固定栏目或字段完整性设为启动门。新工作区默认选择展示名称布局；新集打包时从已登记系列名和 release_catalog 准备名称。已有非空目录需显式迁移，不静默搬迁或创建并行版本。

## 实际工具

```sh
# 更新当前总入口、系列观看页及文案合集；不生成或重编码视频
python3 scripts/publish_catalog.py --workspace /path/to/workbench

# 只读检查实际导航链接、目录和当前交付指针
python3 scripts/publish_catalog.py --workspace /path/to/workbench --check

# 先在 workbench.yaml 登记展示名，再按精确指针显式迁移选定系列
python3 scripts/publish_catalog.py --workspace /path/to/workbench \
  --migrate --series stable_series_id
```

可重复使用 `--series` 选择多个系列。只有明确退役的系列才使用 `--archive-series ID`；制作批次旧入口用 `--archive-entry 相对名称` 显式归档，不猜所有未知目录都是垃圾。源文件先按当前 pointer/manifest 核对，目标冲突不覆盖；迁移保存配置、原导航和受影响当前元数据，原视频与文件保持字节一致。归档和恢复映射留 `archive/deliveries/_layout/<时间>/`，不在用户目录留副本或旧入口。

## 打包及验收

`paper_project package`、`package_review` 和匹配正式 final 合同的包器消费同一 `delivery_layout.locations`，不自己拼接英文集号路径。单集更换后保持中文目录、归档旧包并刷新总入口；不重新渲染未改变的视频。旧工作区显式升级方法与工具，不覆盖专用代码。

观看页是离线 HTML、无 CDN、无自动播放；各系列的视频、封面和文案使用系列内相对链接，可单独转存整个系列目录。总入口按所有当前系列生成，不保留“四季”“六个新系列”这类批次入口；无实际文件的 ZIP 不提供下载链接。文案合集消费实际 TXT，医学语义修改仍回系列 release_catalog。

Review 检查用户能否按主题和集名找到文件、复制链接能否打开、当前指针是否相同母版、历史是否移出 publish。文件和 SHA 校验只证明位置与字节；连续动作、听感、医学审核和上传状态原样保留。导航缺项不回滚有效成片，保存诊断与质量债后修复交付组织。
