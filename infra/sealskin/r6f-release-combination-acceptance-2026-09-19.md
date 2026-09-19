# R6F 组合 QA、真实客户端、生产候选与回退阶段验收

日期：2026-09-19（UTC）

本报告记录 R6F 已完成的隔离检查和当前阻断项。R6F 尚未收尾，生产 Adapter、控制器、Caddy、账号、Home 与 Session 保持 R4B 运行态，未执行生产安装或回退。详细日志、候选二进制摘要和脱敏运行态位于被 Git 忽略的 [R6F 私有证据](runtime/r6f-release-combination-2026-09-19/production-readonly-1.json)。

## 已完成的隔离检查

- 当前源码基线为 `c7e946f`。Adapter 在固定 Go 1.27.1 环境中通过 `go vet ./...`、格式化检查和全模块测试；checks 镜像内 `CGO_ENABLED=1`、串行 `go test -race -p 1 -count=1 ./...` 通过，日志末尾为 `exit=0`。
- 固定 Camoufox r9 镜像内执行 `acceptance.py --phase unit`，artifact 单元验收通过。直接在宿主 Debian 12 执行同一组 artifact 测试会因 Python 3.11/运行架构与固定产物不匹配返回 `ENVIRONMENT_VERSION_MISMATCH`，因此不把宿主结果写成通过。
- R6E 主机执行器/准备器的 21 项 Python 回归继续通过；真实 R6E 作业的 10 次重建、目录追加和夹具清理沿用 R6E 报告，不扩大为 R6F 组合通过。
- 使用固定 age v1.2.1 工具和 checks 镜像重跑备份测试：114 项通过，1 项失败。失败为 `test_legacy_cli_uses_real_socket_age_and_offline_restore` 的子进程包装场景，返回稳定 `BACKUP_OPERATION_FAILED`，未触及生产；该失败保留，备份/恢复验收不能标记为完整通过。未提供 age 工具的初次运行记录为 115 skipped，随后已补入固定工具重跑。
- 构建了隔离审查候选 `candidate-1`：`profile-adapter`、`profile-accounts`，并以源码、控制器第二层补丁、固定 r9/SealSkin/checks 镜像摘要生成 manifest。候选标记为 `ISOLATED_REVIEW_ONLY`，未安装为服务。
- 直接读取生产状态：Docker、Caddy、用户 Adapter 均 active，`Linger=yes`；Personal 为 1 record/1 Worker/5 resources/1 Relay/1 Guard/2 networks、network phase running；Work 为 1 record/1 Worker、无 Relay/Guard/network；入口边界为登录 200、两个 Profile 未登录 303、Session 根 404。此检查只读，生产未变。
- 只读复核历史 R4B `release-ready-2` 时按预期拒绝 `live input drift`：其准备摘要早于当前 r9 配置/状态写入。该差异已登记 [DEV-052](../../docs/deviations/DEV-2026-09-19-052-stale-release-package.md)；历史包继续作为回退材料，不能直接冒充 R6F 新候选。

## 尚未完成

组合控制器/Worker 的 R6A–R6E 同版本独立 QA、真实上游代理凭据探针、真实自定义产物 Worker、Trilium/macOS 实机分项、完整备份恢复、回退演练和生产候选安装仍未完成。当前机器缺少生产维护授权和真实 Mac 操作通道，不能据此执行这些动作；R6E 执行器也仍未安装为生产服务。

R6F 保持“进行中”。在备份子进程失败、完整组合 QA、真实客户端和候选重新绑定完成前，不得把 R6 父项标记为收尾或部署管理面。
