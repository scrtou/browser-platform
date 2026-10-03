# DEV-2026-09-29-076 · Adapter 丢失控制器的 DIRECT 能力观测

状态：已解决（代码、回归与限定 Adapter 部署完成）。发现及解决日期：2026-09-29。关联工作项：[R7F](../work-items/R7F-2026-09-23-production-release.md)。

## 预期与实际

受管理 DIRECT 发布前须核对控制器 `network_direct_version`。生命周期 API 的 Home 清单返回该字段，但 Adapter 的 `sealskin.HomeRuntime` 没有相应 JSON 字段，`Capabilities()` 也没有映射。因此运维 `inspect-profile` 丢失了控制器实际提供的 DIRECT 能力；2026-09-29 发布准备检查在此处拒绝，不能据此认定控制器没有实现 DIRECT。

## 处理决定

修复 Adapter 的只读协议字段和能力映射，保留旧控制器缺字段时的 0（未知/不可证明），不根据镜像标签或配置猜测为 1。此项不扩大 `required_runtime_capabilities` 可配置字段，不改变现有启动、停止或网络绑定门槛。

## 验证与收尾条件

- 加密清单协议回归覆盖缺字段、version 1 和未来未知版本，原值完整传递。
- 全量 Adapter test/vet、关键包 race 与现有生命周期回归通过。
- 固定候选与旧二进制，按 R7F 授权只替换 Adapter 后复核实际 DIRECT 字段；Personal/Work 仍停止且资源为零，“测试”的 Session/Worker/网络及 Home 保持。
- 同步组件说明、DIRECT 契约、验收报告、进度/计划与工作项。

结果：全量 test/vet/gofmt、五包 race 与加密清单三个版本场景通过。Adapter `346d6377…` 已部署，生产 `inspect-profile work` 的 DIRECT 版本为 1；Personal/Work 仍 stopped/0 resources，“测试”原运行身份保留且新鲜 healthy。首轮检查器的 Host 缺失导致回退，修正检查请求后按原就绪门槛复验通过，详见 [本轮验收](../../infra/sealskin/r7f-production-review-acceptance-2026-09-29.md)。本结果不表示 Work 已启用 DIRECT。
