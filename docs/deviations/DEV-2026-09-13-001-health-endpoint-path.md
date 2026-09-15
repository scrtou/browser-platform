# DEV-2026-09-13-001 · 健康查询入口路径与人工探测暴露方式

状态：已解决。发现日期：2026-09-13。关联工作项：[R1 运行健康与浏览器恢复提示](../work-items/R1-2026-09-13-runtime-health.md)。

## 设计预期

[规格 45.5](../specs/proxy-environment/specification.md#455-api-行为与错误契约) 规划的自有入口 API 为 `GET /api/v1/profiles/{id}/health`（返回缓存报告及新鲜度）、`GET /api/v1/profiles/{id}/network-check`（只读）和 `POST /api/v1/profiles/{id}/network-check`（对已运行实例执行受控探测）。[规格 49.2](../specs/proxy-environment/specification.md#492-状态和新鲜度) 要求入口查询读取缓存、人工 POST 探测每 Profile 最短间隔 10 秒且同一 Profile 同时最多一个探测任务。

## 实际事实与证据

- 现有部署没有 `/api/v1` 前缀：前置 Caddy 只把 `/browser/*`（需登录）和 `/bootstrap/*`（能力 URL）转发到 Adapter，`/healthz`、`/readyz` 明确不公开（[Adapter 说明](../../adapter/README.md)、[SealSkin 部署](../../infra/sealskin/README.md#域名与-caddy-路由)）。
- 运维命令统一走本机 `0600` Unix socket，不新增公网 stop 接口（[生命周期说明](../../infra/sealskin/lifecycle/README.md#adapter-运维入口)）。
- R1 实现：公网侧只提供 `GET /browser/{profile}/health`（脱敏 JSON，读缓存或触发一次有界只读采集，不带 operation/Session 标识）；人工强制探测只通过本机 socket `POST /profiles/{profile}/health`（CLI `-probe-profile`），间隔 10 秒、单飞。源码见 [httpapi](../../adapter/internal/httpapi/server.go)、[control](../../adapter/internal/control/control.go)、[health.go](../../adapter/internal/profile/health.go)。

## 影响与处理决定

- 影响：仅路径与暴露面不同；新鲜度、缓存、探测节流、只读等语义与规格一致。公网不暴露强制探测，避免未鉴权轮询触发上游探测。
- 处理方式：**修订设计**。理由：与既有 Caddy 路由和“运维命令不公开”的决策一致，不必为一个路径引入新的公网前缀与鉴权配置。
- 实际授权或需要外部决定的内容：不适用。
- 关联计划与不能提前通过的验收：R5 的最终用户入口鉴权仍未验收，`GET /browser/{profile}/health` 与入口页同样依赖前置 Caddy 的登录保护。

## 实施、验证与文档同步

| 材料 | 更新 / 结果 |
| --- | --- |
| 实现 | Adapter 公网 `GET /browser/{profile}/health`；本机 socket `GET/POST /profiles/{profile}/health`；CLI `-health-profile`、`-probe-profile` |
| 验收与证据 | Go 单元测试（缓存/节流/单飞/脱敏）与 [健康验收](../../infra/sealskin/health-acceptance-2026-09-13.md) |
| 设计 / 规格 / 组件说明 | 规格 45.5 增加当前映射说明；[Adapter 说明](../../adapter/README.md) 记录实际路径 |
| 进度 / 计划 / 工作项 | 由 R1 工作项收尾时同步 |

## 最终复核

最终行为：公网只读健康 JSON 位于入口站点 `/browser/{profile}/health`，强制探测仅限本机 socket。剩余边界：公网入口鉴权属于 R5。解决日期：2026-09-13。
