# OPL Med Cast

正式名称为OPL Med Cast，仓库、Agent和Package技术标识为opl-medcast，领域为medical_video。OPL标准由Framework持有，以OPL Book Forge为结构参考。

- agent/与contracts/持有医学科普工作流、质量判断和领域合同；OPL持有执行、评测、版本、激活与回滚。
- 原始视频、关键帧、旁白、发布包和本机配置属于制作工作区，不复制进源码仓库。凭据只从工作区登记来源解析。
- 先核对当前目标与实际制作单，复用已审音轨和可用素材，保留单一写入者；后台检查不自动播放或发声。
- 关键帧、源视频、成片、完整听感、医学复核和平台发布分别记录，不以文件存在或技术检查代替语义批准。
- 中文维护文档；主Skill为agent/primary_skill/SKILL.md。修改后运行scripts/verify.sh。
- 本地构建不自动授权发布、平台上传、激活或替换现有生产工作区；未获用户授权不提交或推送。
