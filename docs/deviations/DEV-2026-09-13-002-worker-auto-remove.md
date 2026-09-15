# DEV-2026-09-13-002 · Profile Worker 容器使用 Docker 自动删除，重启后无法按代次恢复

状态：已解决（实现侧）；旧代次切换待用户决定。发现日期：2026-09-13。关联工作项：[R2 开机持久运行与生产恢复](../work-items/R2-2026-09-13-boot-recovery.md)。

## 设计预期

[架构](../design.md#profilehome-与-generation)：Profile 长期保留、Worker 可重建；[计划 R2](../roadmap.md#r2) 与 [规格 48.2](../specs/proxy-environment/specification.md#482-docker-与主机重启行为) 要求受管理 Personal 在开机后按“控制面对账 → Guard 规则就绪 → Relay/探测 → Worker → 显示检查”的顺序恢复，故障时保留阻断与占用；MVP-8 要求控制服务、Docker、VPS 重启后可恢复 Profile 数据。[v2 验收](../../infra/sealskin/network-isolation-acceptance-2026-09-13.md#docker-重启与仍需维护窗口的项目) 的独立 daemon 结果写为“`restart=no` 的 Worker、Guard、Relay 等容器保持停止”。

## 实际事实与证据

- 上游 `DockerProvider.launch` 以 `remove: True`（AutoRemove）创建每个 Worker（补丁前的 [docker_provider.py](../../infra/sealskin/lifecycle/profile-lifecycle.patch) `run_kwargs`）。生产核对（2026-09-13，只读 `docker inspect`）：Work、Personal 两个 Worker `AutoRemove=true, RestartPolicy=no`；控制器与静态 Relay 为 `AutoRemove=false, unless-stopped`。
- 独立 Docker-in-Docker 对照实验（Docker 29.8.0，无外部网络，VFS；证据 `runtime/boot-recovery-2026-09-13/autoremove-daemon-test.log`）：同时运行 `--rm` 与普通容器，优雅停止并重启 daemon（未启用 live-restore）后，`--rm` 容器**被删除**，普通容器保留为 `Exited (137)`。
- 隔离 QA 复现（`runtime/boot-recovery-2026-09-13/qa/proxy-events.jsonl` 与 Docker events）：Worker 退出后立即 `die → destroy`，Adapter 只能记录 `unknown`/`stopped`，没有可恢复的代次。
- 因此现有生产代次在 daemon/主机重启后不会成为“已退出但可恢复”的容器；会话记录会被 API 启动时的 `_remove_stale_sessions` 清除，Adapter 对账后标为 `stopped`，下次入口新建代次。Home 数据不受影响。v2 验收中“`restart=no` 保持停止”的结论只对**合成 Worker（无 AutoRemove）**成立。

## 影响与处理决定

- 影响：当前生产会话在 Docker/VPS 重启后一定丢失（Home 保留，可重新启动新代次，Personal 会自动采用 `personal-socks5-r2`）。规划中的按序恢复只对新建代次有效。
- 处理方式：**修复实现**。补丁 `0.3.2-resume-v1` 起，带 Profile 身份的 Worker 以 `remove=False`、`restart_policy=no` 创建，退出后保留为容器，由生命周期 `stop` 显式删除；新增 `resume` 按序恢复休眠代次。普通（非 Profile）会话保持上游自动删除。
- 实际授权或需要外部决定的内容：现有 Work/Personal 代次要获得可恢复性必须停止后新建（会中断当前浏览器会话，Home 数据保留）。是否安排该切换由用户决定；本项不自动停止生产会话。
- 关联计划与不能提前通过的验收：MVP-8、N 组“重启”场景在生产整机重启验收前不能填通过；v2 报告与进度页中“`restart=no` 保持停止”限定为合成 Worker。

## 实施、验证与文档同步

| 材料 | 更新 / 结果 |
| --- | --- |
| 实现 | 补丁 `docker_provider.py`：Profile Worker `remove=False` + `restart_policy no`（Python 单测断言；普通会话仍 `remove=True`）；`profile_resume.py` 按序恢复 |
| 验收与证据 | dind 对照实验（上文）；隔离 QA 演练：真实 Firefox 代次全部容器停止、控制器与 Adapter 重启后由启动对账按序恢复同一批容器，数据完整（见 [开机恢复验收](../../infra/sealskin/boot-recovery-acceptance-2026-09-13.md)） |
| 设计 / 规格 / 组件说明 | [生命周期说明](../../infra/sealskin/lifecycle/README.md#休眠代次与按序恢复) 增加休眠代次与恢复顺序；[规格 48.2](../specs/proxy-environment/specification.md#482-docker-与主机重启行为)、[v2 验收](../../infra/sealskin/network-isolation-acceptance-2026-09-13.md)、[进度](../progress.md#startup) 的“保持停止”结论收窄为合成 Worker |
| 进度 / 计划 / 工作项 | R2 工作项与进度页记录旧代次需切换才具备可恢复性 |

## 最终复核

最终行为：`0.3.2-resume-v1`（2026-09-13 21:49 UTC 上线）起，带 Profile 身份的 Worker 不再自动删除，重启后保留为已退出容器并可按序恢复；隔离演练（真实 Firefox 代次全容器停止 + 控制器/Adapter 重启）通过。剩余边界：现有 Work/Personal 代次仍是发布前的自动删除容器，只有停止后新建才具备可恢复性，切换时机由用户决定；正式整机重启验收仍待维护窗口。解决日期：2026-09-13。
