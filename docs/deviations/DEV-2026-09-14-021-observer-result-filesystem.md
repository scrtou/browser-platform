# DEV-021 · Docker 无法读取观测脚本的共享内存结果

状态：已修复并通过隔离验收（候选 4；未部署生产）。工作项：[R5C3](../work-items/R5C3-2026-09-14-runtime-coherence.md)。发现日期：2026-09-14。

设计要求：控制器通过固定、有界、私有的通道取得准确 QA Worker/Guard 的观测结果；缺失时不能放行，不读取用户页面或放开任意 exec。

实测事实：第一版一致性候选在准备 Guard 时阻断，未创建浏览器。固定脚本成功生成 `/dev/shm/browser-platform-coherence.json`，容器内 stat/read 均可见，但当前 Docker 的 `get_archive` 和 `docker cp` 均返回 404。单元模拟中的 archive 返回未覆盖实际共享内存挂载视图。此失败与原始记录位于被忽略的 `infra/sealskin/runtime/r5c3-coherence-2026-09-14/candidate-1/tw-direct-start-1/`；不改写第一版结果。

处理选择：修复实现。使用每个网络代次、每个角色独立的私有结果目录，控制器保留目录所有权，精确 bind 到该角色的固定路径；脚本只原子写一个有界 JSON，控制器验证 nonce、文件类型/权限/大小、代次和来源。保持固定 detached exec、单 Home 锁和取消等待，不开放调试端口或任意命令。停止时一起清理这些 QA 结果目录。

待验证：实际 Guard/Relay/正常浏览器结果读取、跨角色/跨代次拒绝、超时及清理；更新生命周期契约、准备器、QA 代理限制及最终验收后才能关闭。

验证结果：候选 4 的实际 Guard/Relay/正常浏览器结果可读，私有目录随代次停止清理；`c01-entry-2/`、`c03-entry-2/`、`rules-fault-1/` 通过。控制端固定候选的 458 项测试及配套 63 项挂载/exec/Guard 检查覆盖结果权限、角色/代次限制和有界失败。第一版失败保持原状。详细证据均位于被忽略的 `infra/sealskin/runtime/r5c3-coherence-2026-09-14/`，不代表生产已更新。
