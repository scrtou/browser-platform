# R6 · 账号、代理、指纹选择与环境关闭设计

状态：待启动。登记日期：2026-09-16。实现日期：未开始。结束日期：未结束。

## 目标与范围

- 对应 [R6 后续产品能力](../roadmap.md#r6) 和 [环境管理面规格](../specs/proxy-environment/management.md)。
- 设计并最终实现四项能力：账号密码访问、手动配置受管理代理、选择已验收的环境指纹、手动安全关闭环境。
- 继续使用 Adapter 作为业务授权和 Profile 状态所有者，SealSkin 作为 Session/Docker 生命周期所有者；不在客户端直接操作 Docker、Home 或上游代理。
- 当前交付仅完成设计文档；本记录不表示代码实现、QA、生产部署或 R4B 已收尾。

## 设计结论

- 访问使用现有 R5D 的 HTTPS 表单登录、短期 Cookie、CSRF、Origin、Profile 授权和显示 Cookie；增加环境级能力，不使用长期 HTTP Basic。
- 指纹使用已生成并通过验收的 `EnvironmentArtifact`。第一版把每个可选择组合建模为独立 Profile/Home，禁止运行中切换任意指纹字段。
- 代理先进入短期草稿，凭据写入 Secret Store，隔离探针通过后固化 ProxyConfig/NetworkPolicy 修订；Worker 始终经 Guard/Relay，不能直连或热切换。
- 关闭复用现有 `profile.Stop`/`Reconcile` 状态机，撤销显示访问并保留 Home；“停用”和“删除”是不同的管理员动作。
- 启动由服务端生成一次性 `launch_plan`，冻结账号、Profile、Home、Artifact、代理、网络策略和能力摘要，客户端不能提交任意后端参数。

## 阅读与代码核对

| 材料 / 代码入口 | 当前结论 |
| --- | --- |
| `adapter/internal/access`、`infra/sealskin/entry-auth/` | 已有账号密码、Profile 授权、短期登录/显示 Cookie、CSRF、Origin 和日志边界，并已随 R4B 组合部署生产 |
| `adapter/internal/profile` | 已有 Ensure/Stop/Reconcile、Home 独占、持久化停止意图和 UNKNOWN 保留；关闭按钮应复用，不新增 Docker 路径 |
| `adapter/internal/sealskin` | 已有 Session、Worker、Guard/Relay、环境身份和运行时能力快照 |
| `docs/specs/proxy-environment/{types.go,schema.sql,specification.md}` | 已有 Profile、环境产物、代理、网络策略、运行绑定和审计的参考契约；修订不可变、停止后切换 |
| R5A/R5B/R5D 验收 | 代理协议/认证、Secret Store、入口认证和显示授权已有隔离候选，均须与 R4B 生产材料合并后再发布 |

## 实施与偏差

本设计阶段未修改代码、配置、账号、Home、Session 或生产资源。实施阶段如发现“手动选择”需要跨 Home 复用、代理地区与指纹冲突、或 SealSkin 缺少所需控制能力，必须建立单独偏差记录，不降低验收条件。

## 验收复核

| 原要求 | 实现位置 | 预定检查 | 当前结果 |
| --- | --- | --- | --- |
| 账号密码访问和环境授权 | Adapter access / `profile_access` | 未授权、过期、撤销、CSRF、限速、显示 Cookie | 设计完成，未实现 |
| 手动代理 | Secret Store / Relay / proxy draft | 凭据脱敏、隔离探针、无直连、修订绑定 | 设计完成，未实现 |
| 手动选择指纹 | EnvironmentArtifact / Profile/Home | 只允许已验收摘要、运行中拒绝、Home 独占 | 设计完成，未实现 |
| 手动关闭 | `profile.Stop` / `Reconcile` | 正常关闭、失败保留、资源清理、Home 保留 | 现有生命周期已验收，管理入口未实现 |

## 文档与收尾

- [x] 架构设计、代理/环境规格和 R6 路线图已登记。
- [x] 现有入口、状态所有权、凭据和生命周期边界已核对。
- [ ] 创建实现子项并开始代码工作；R4B 已于 2026-09-17 收尾，R2 剩余退出登录/Debian 13 是否作为前置由用户决定。
- [ ] 完成独立 QA、客户端验收、生产候选、部署与回退。

收尾结论：设计提案完成，工作项保持待启动。下一步：R4B 生产迁移条件已于 2026-09-17 完成；待用户决定是否等待 R2 剩余条件后，按本文实施顺序建立 R6 实现子项。
