# R7B · Work 受管理出网与无直连验收

状态：已收尾。开始日期：2026-09-21。结束日期：2026-09-21。

## 目标与范围

- 用户要求 / 对应计划：[R7 v4](../browser-workspace-plan.md) 的第二项实施工作；前置 [R7A](R7A-2026-09-21-work-egress-diagnosis.md) 已收尾。
- 本项交付：为 Firefox legacy / Wayland 的 Work 形态建立独立受管理公网路径。没有独立代理凭据时优先采用受管理 DIRECT；策略、Home、应用和 generation 不与 Personal 复用。
- 完成条件：主机原生公网 IPv4 与固定解析器前置可证明；独立 QA 通过 DNS、TCP/TLS/HTTPS、Guard/网关、无直连回退、停止—重建—恢复、Home 持久化和健康报告；失败保留旧生产 Work 定义与 Home。
- 生产边界：当前 Work 已停用、停止且资源为零。本项先做隔离 QA 和发布候选，不以直接接公网 bridge、放宽防火墙或复用 Personal secret 解决；生产绑定与启用只在 R7F 固定发布包和回退门槛内执行。
- 本项不实现统一代理目录或 UI 下拉，它们属于 R7C–R7E。

## 阅读与代码核对

| 材料 / 代码入口 | 核对结论 |
| --- | --- |
| R7 v4、R7A/DEV-061、DIRECT 契约与 R5C1 验收 | 旧 Work 缺少受管理路径；既有 DIRECT 候选已证明 Guard/网关/地址证据模型，但未覆盖当前 Firefox legacy/Wayland 组合与现行 overlay |
| 生命周期 patch、Guard/Relay、Adapter 健康与恢复 | 生产 payload 含 DIRECT 代码但未挂载宿主地址证据，生产 Relay 也非 DIRECT 镜像；隔离 QA 使用固定控制器副本与 `direct-egress=1` 网关完成验收 |
| Work 镜像、应用、Home 与当前目录/运行态 | 固定 legacy 镜像和原 Home 保留；发现旧镜像缺少 Firefox Relay 锁定，已用精确父层构建候选；生产继续 disabled/stopped/0 resources |
| 已有工作区改动 | 保留 R6/R7 既有改动；所有 QA 使用独立名称、Home、策略和忽略目录 |

## 实施与偏差

关联偏差：[DEV-061](../deviations/DEV-2026-09-20-061-work-egress-unobserved.md)、[DEV-063](../deviations/DEV-2026-09-21-063-work-qa-firefox-argument.md)、[DEV-064](../deviations/DEV-2026-09-21-064-work-qa-launch-context.md)、[DEV-065](../deviations/DEV-2026-09-21-065-work-firefox-proxy-policy.md)、[DEV-066](../deviations/DEV-2026-09-21-066-focused-network-qa-cleanup-evidence.md)。前三轮 QA 暴露进程识别与 Launch Context 测试编排偏差；第四轮进一步证明旧 Work 镜像缺少 Firefox Relay 锁定配置；聚焦验收的清理摘要入口也已按原严格门槛泛化。工具和候选均已修复，第六轮完整通过，等待最终清理与文档收尾。

## 验收复核

| 原要求 | 实现位置 | 检查与证据 | 结果 / 未测范围 |
| --- | --- | --- | --- |
| Work 独立受管理公网 | `infra/work-firefox-managed/`、DIRECT policy、Firefox legacy 应用与 QA Home | 第六轮真实 Firefox/Wayland 页面、健康与固定候选镜像 | 通过；生产绑定归 R7F |
| DNS/HTTPS 与失败不直连 | Firefox SOCKS/远端 DNS、Guard/Relay/网关探针 | 公开 HTTPS、经 Relay 探针、4 类原始绕过；停止网关后重复 | 通过，故障保持 fail-closed |
| 停止/恢复与 Home 数据 | 生命周期与 Work 正常退出层 | 正常 Stop → 新 generation；Cookie/localStorage/IndexedDB | 通过，三类数据恢复且进程换代 |
| 生产保持与回退 | 当前目录/状态/容器摘要 | 清理前后 inspect；[公开验收](../../infra/sealskin/r7b-managed-work-egress-acceptance-2026-09-21.md) | Work 仍停用/停止/0 资源；Personal 身份未变；未部署 |

## 文档与收尾

- [x] 逐项回看原始任务、计划、设计和实际行为。
- [x] 完成本项必要验证，公开报告与私有证据范围明确。
- [x] 相关偏差已处理并复核；未完成项有明确状态。
- [x] 更新设计/规格/组件/用户或运维说明，或记录不适用原因。
- [x] 更新验收索引。
- [x] 更新开发进度与生效范围。
- [x] 更新开发计划的完成条件、剩余工作和下一项。
- [x] 核对 QA 清理、回滚材料、链接及工作区变更。
- [x] 更新本记录与工作项索引，确认是否允许开始下一项。

收尾结论：已收尾。候选 `sha256:895907b7…` 的 Firefox/Wayland 受管理 DIRECT、无绕过、故障关闭、正常换代和三类存储恢复通过；QA 已清理，生产保持。下一项允许建立 R7C；生产发布仍只在 R7F 执行。
