# DEV-091 · 部署就绪检查的 Host 头

状态：已解决。关联 [R6L](../work-items/R6L-2026-10-01-chromix.md)。修复部署检查，不改变入口主机名保护。

首次 R6L 部署使用 http://127.0.0.1:9100/readyz 的默认 Host，就绪校验收到 421，触发恢复原 Adapter/目录。复核原版本也拒绝该 Host；携带配置 public_base_url 的正式 Host 返回 200。不是 Chromix 引擎或既有浏览器故障。

保留首次回退记录；修正为配置中的正式 Host，重试后逐项检查生产绑定/容器身份及健康。不放宽入口 Host 校验，不把失败检查改写为首次通过。

修复后部署及生产复核均 PASS；Personal/Work healthy，原容器身份和绑定保持。证据为 R6L 私有 deployment-rolled-back.json、deployment-result.json 和 postdeployment-result.json；[验收](../../infra/sealskin/r6l-chromix-acceptance-2026-10-01.md) 保留首次失败与重试边界。
