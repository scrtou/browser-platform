# 应用日志限额的生产维护材料

2026-10-01：用户已授权正常停止、备份并重建现有浏览器，R6J1 日志专用维护已通过。[生产验收](../sealskin/r6j1-log-deployment-acceptance-2026-10-01.md)记录准确版本、备份、实际生效范围及回退入口。

## 当前生效范围

日志专用控制器 `sha256:ad21dd6de070fce88e59a6c32fd213c017fcb587dffd3cac907693cb7b3b6525` 基于原生产镜像，只修改两处创建代码并新增 bounded_logs.py，完整保留其余 overlay。控制器、静态 Relay 和三个 Home 的九个专属容器，共 11 个实际 HostConfig 均为 json-file / 10 MiB × 3 / compress=true。后续新 Worker、Relay、Guard、启动探测也由创建代码强制设置，应用 overrides 不能取消。

日志按大小轮换，不提供按天删除保证；活跃文件可能略超阈值，名义上限不是文件系统硬配额。Adapter 和主机共享 journald 未调整，其预算由后续审计承接。

## 已执行维护与恢复边界

三个 Home 分别正常停止并确认无任何资源/挂载，完成新 age 备份、verify、独立 restore 及内容/权限比对。重建使用原 Home、应用、Worker 镜像和代理修订；Session/operation 更新。“测试”重建后正常关闭远程浏览器，保留用户意图。Personal/Work 健康，三个 Home 的 HTTPS 与禁止直连通过，固定入口与监控 timer 正常。

维护期间使用原 Adapter 二进制的私有监听，保留认证及独占状态锁；新代次通过先行 QA 的一次性离线生命周期工具建立。它不是新部署的产品 API，也不改变公开授权流程。未来维护仍需实时核对范围、所有权及恢复路径，不能直接重放本轮操作或共享状态。

私有 `runtime/r6j1-log-deployment-20261001/` 保存原 Compose 链、配置快照、源码/镜像证据、密文和回退说明。旧镜像回退不授权恢复旧账号、真实 Home 或共享 journal；先以正常生命周期处理任何部分失败代次。已创建容器保留各自日志配置，旧控制器后续新建容器恢复为无限额，须单列记录。

## 历史组合候选

先前 `fa9349bb…` 候选包含未批准部署的 R7G，虽通过 562 项控制器与真实 QA，未用于本次生产。通用 prepare.py 当前会应用 dynamic-upstream 补丁，不能直接拿其输出替换日志专用生产镜像。R7G 和 R6I 的独立发布门槛继续保留，详见[候选验收](../sealskin/r6j-log-policy-acceptance-2026-10-01.md)。

当前实际 Compose 链在原链末尾追加私有 `runtime/r6j1-log-deployment-20261001/compose.logging.json`，同时固定日志专用镜像和两服务 logging；可从当前控制器的 Compose 标签只读核对。后续重建须保留该配置或显式合并等价策略，单独重放旧链属于回退，不是当前日志版本。
