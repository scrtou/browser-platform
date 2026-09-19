# DEV-2026-09-19-052 · R6F 复用旧生产候选时输入摘要漂移

状态：待处理。发现日期：2026-09-19。关联工作项：[R6F](../work-items/R6F-2026-09-19-release-combination.md)。

## 设计预期

R6F 应以当前 R6A–R6E 候选源码、生产只读现态和保留的 R4B 回退材料形成可追溯候选。发布包的源码/配置摘要必须与其声明的准备阶段一致；旧包不能在输入变化后继续被当作当前候选。对应范围是 R6F 生产候选与回退核对，不能以旧包的 `READY_FOR_MAINTENANCE` 状态替代新的 R6F 组合验收。

## 实际事实与证据

只读执行 `verify-r4b-production-release.py` 针对历史 `release-ready-2` 包时返回 `live production input drift`。`release-audit.json` 中记录的摘要与当前文件不一致：

- `infra/sealskin/adapter-config.json`
- `infra/sealskin/adapter-state.json`
- `infra/sealskin/config/.config/sealskin/profile-network-policies.json`

差异来自 R4B 包准备后完成的 r9 生产切换和运行状态写入；Caddy 与 Compose 摘要仍一致。当前生产仍为 R4B r9/Work 运行态，未因本次核对变更。私有脱敏核对见 `infra/sealskin/runtime/r6f-release-combination-2026-09-19/production-readonly-1.json`；拒绝输出不含凭据。

## 影响与处理决定

- 对当前交付的影响：历史 `release-ready-2` 仍可作为回退材料和历史证据，但不能直接作为 R6F 的新生产候选；R6F 候选必须重新构建并记录当前输入摘要。
- 处理方式：保留待处理。已在隔离运行目录构建 R6F 审查二进制和 manifest；尚未把 R6F 管理面配置或控制器补丁安装到生产，也未执行真实 Home/Session 回退。
- 实际授权或需要外部决定的内容：真实 Mac/Trilium 复测、真实上游代理、生产维护窗口和是否部署候选需要后续明确授权；本记录不扩大授权。
- 关联计划与不能提前通过的验收：R6F 组合 QA、真实客户端和生产安装门槛保持未验证；旧包的历史通过范围不能覆盖这些缺口。

## 实施、验证与文档同步

| 材料 | 更新 / 结果 |
| --- | --- |
| 实现 | 未修改生产实现；隔离候选二进制位于被忽略的 R6F 证据根。 |
| 验收与证据 | 旧包复核按预期拒绝；当前生产只读边界和服务状态已记录。 |
| 设计 / 规格 / 组件说明 | R6F 工作项补充当前候选必须重新绑定输入摘要的范围。 |
| 进度 / 计划 / 工作项 | R6F 保持进行中，生产仍未变。 |

## 最终复核

历史包漂移已确认并隔离处理，尚未完成新的生产候选发布包和部署验收。解决前不得把旧 `release-ready-2` 的维护状态写成 R6F 通过。
