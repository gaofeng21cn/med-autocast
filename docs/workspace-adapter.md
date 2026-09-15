# 制作工作区接入

Python辅助程序仅依赖PyYAML。安装到独立环境：

```sh
python3 -m venv .local/venv
.local/venv/bin/pip install "PyYAML>=6,<7"
.local/venv/bin/python runtime/native_helpers/medcast.py inspect --workspace /absolute/medical-workspace
python3 runtime/native_helpers/medcast.py assets --workspace /absolute/medical-workspace
```

inspect支持medical_video_workbench/v2，仅读取工作区配置中的profile路径、系列目录与入口存在性，不输出profile正文或后端密钥，不连接GPU服务。媒体默认值继续由workbench配置解析。

OPL三个公开动作由StageRun加载专业Skill。它们是AI工作流，并非同名Python命令。未安装/登记时不能声称托管动作可运行；当前本地会话可以直接使用专业Skill调用已验证的制作工作区脚本。生成与剪辑副作用只在用户请求覆盖时执行。

交付预检使用三个独立JSON：

```sh
python3 runtime/native_helpers/medcast.py preflight --workspace /absolute/workspace   --current review/current-selection.json   --delivery review/delivery.json   --source-review review/source-review.json
```

current含schema=opl_medcast_current_selection/v1、series_id、revision、episode_ids、master_refs（集号到工作区相对母版路径）。delivery含schema=opl_medcast_delivery/v1、同series_id和revision、intent=review或publication_candidate，episodes每项有episode_id、master_ref、narration_ref、subtitles_ref、shots和reviews。

shots每项含source_id、source_ref、source_range=[start,end]。独立source-review按source_id索引，每项有accepted、source_ref和usable_range。旧审查记录没有source_ref时，需依据精确生成回执补齐映射，不能按前缀猜测。

reviews按technical/visual/continuous_motion/listening/medical记录status；passed必须有evidence_ref和匹配母版的artifact_ref。not_applicable须说明原因且仍需owner核对。预检不读取证据含义或认证签字，不颁发质量、发布、上传批准。

机器路径禁止越出工作区及符号链接逃逸。不修改原工作区以凑预检；通过副本或新输入适配旧合同，媒体保持原位。
