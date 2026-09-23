# 医学关键帧资产协议

制作工作区 `assets/keyframes/catalog.json` 是索引权威，schema为medical_keyframe_library/v1。原图放用途目录；HTML、CSV及缩略图是生成投影。Agent源码不复制真实媒体。

用途：测量与监测、饮食与采购、运动与日常、睡眠与行为、门诊与治疗沟通、用药与药房、报告与随访、就医与家庭支持。系列、人物、风格和医学限制作为索引字段，不为每个交叉分类复制原图。

每项保留稳定ID、原图路径、类别、series_id、用途、来源路径及shot_id、静态审查范围与证据、复用注意事项、关联视频审查和使用记录。经实际查看且有参考价值才入库；excluded保留拒收理由，不混入可用项。重复索引和丢图属于可机械检查的问题。

入库只表示静态参考价值，不表示可跨篇直接复用、医学准确或动态通过。关联视频accepted=false时，静态图片仍可有参考价值，但不得返回其残留可用视频区间。复用前实际看图、核对人物/医学内容及授权范围，再决定调整或生成。

查询：`python3 runtime/native_helpers/med_autocast.py assets --workspace /absolute/workspace --category 05`。更新库使用制作工作区已验证的build_keyframe_library.py；入库决定由AI/owner做，不自动收录所有图片。
