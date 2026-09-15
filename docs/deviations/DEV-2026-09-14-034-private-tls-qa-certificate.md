# DEV-034 · 私有 TLS QA 使用无服务名称的旧证书

状态：已解决（QA/发布准备器，未部署生产）。工作项：[R5D](../work-items/R5D-2026-09-14-entry-authentication.md)。

预期：Adapter 对私有控制与 Session 上游同时校验证书信任和配置的服务名称，QA 使用独立、明确名称的证书。

事实：入口准备器直接复制 LSIO 初始 `proxy_cert.pem` 作为 CA，并指定 `network.invalid`。实际证书只有 `CN=*`，没有对应 SAN，候选 1 的 Adapter 因严格校验而返回控制不可用。准备器最后的 readiness 超时，记录为 `candidate-1/prepare-entry-2.log`；未进入真实登录/显示验收。前置 QA TLS 配置已验证有效。

处理选择：修复 QA 准备器，生成仅用于本项隔离实例、含精确 SAN 的私有证书并验证配对；保持严格的 CA/名称检查。生产发布候选也必须包含可审查的私有 TLS 证书准备与校验步骤。不得使用全局跳过证书验证或把旧通配 CN 当作已通过。

须验证：错误 CA/名称拒绝，正确私有 TLS 的控制请求及显示代理成功；QA 原身份/状态保持，生产 Caddy 与容器无变更。

2026-09-15 最终验证：`candidate-1/qa/access/tls-recovery-result.json` 的正确信任/名称通过、错误名称和 CA 拒绝；C3 的 `client-qa-13/` 通过真实私有控制及显示链。`release-review-2/` 含精确 SAN 的新私有证书/密钥和已验证 Caddy/Adapter 配置，生产身份、Caddy 和四容器保持。原 readiness 失败保留，没有跳过 TLS 校验；详情见 [最终验收](../../infra/sealskin/entry-authentication-acceptance-2026-09-15.md)。
