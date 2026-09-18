# R6D · 代理草稿、隔离探针与 proxy_required 修订

状态：已收尾（候选，未部署）。开始日期：2026-09-18。结束日期：2026-09-18。

## 目标与范围

- 用户要求 / 对应计划：[R6 远程浏览器管理面](R6-2026-09-16-environment-management.md)、[管理面规格第 2 版](../specs/proxy-environment/management.md#代理配置)、[R6 计划](../roadmap.md#r6)（第 4 步）。
- 本项交付：管理员可为已存在（已停止）的远程浏览器创建代理草稿（http/https/socks5，`none` 或用户名/密码，HTTPS 可附上游 CA）；凭据只进入 Secret Store，Adapter 与日志只保留 `secret://` 引用；草稿经控制器探针验证认证、TLS 与出口后固化为不可变 `proxy_required` 网络策略修订，写入应用定义与 Profile 目录修订，下一代次生效；也允许把浏览器切回已登记的受管理 DIRECT 修订。草稿 30 分钟过期，过期、失败或被替换即撤销其凭据；删除浏览器时撤销其专属凭据。
- 明确不在本项：自定义指纹作业（R6E）、真实上游代理/真实客户端组合 QA 与生产候选（R6F）、生产 DIRECT 前置、运行中代次热切换（设计明确禁止）。
- 验证范围：Go 单元/HTTP/客户端测试（fake SealSkin）、控制器补丁的 pytest（本机 fake SOCKS5/HTTP CONNECT 代理与本机 TLS 目标）、静态检查、checks 镜像 race；不操作生产二进制、真实 Home、Session、Docker 生命周期或真实代理。
- 前置项及其收尾记录：[R6C](R6C-2026-09-18-create-delete-launch.md) 已于 2026-09-18 收尾并提交（`d6775a0`）。

## 阅读与代码核对

| 材料 / 代码入口 | 核对结论 |
| --- | --- |
| [管理面规格](../specs/proxy-environment/management.md)、[Secret Store](../../infra/sealskin/lifecycle/secret-store.md)、[生命周期 README](../../infra/sealskin/lifecycle/README.md#按-generation-分配代理与网络) | 策略修订是控制器 `NetworkPolicy.model_dump()` 的规范 JSON SHA-256；引用型凭据需 `upstream_protocol`/`upstream_auth` 成对、四维授权（owner/profile/home/app）精确绑定；注册表 `profile-network-policies.json` 归控制器 metadata 目录，只追加。 |
| `profile-lifecycle.patch` 的 `secret_store.py`、`secret_runtime.py`、`network_runtime.py` | 已有 `FileSecretStore.put/resolve/revoke`、管理员 `POST /api/admin/profile-secrets/revoke`、`resolve_upstream` 冻结 IPv4、启动时 Guard 命名空间内 `run_probe`；没有管理员导入、策略追加或草稿探针接口。 |
| `adapter/internal/profile/{management,directory,service}.go` | R6C 创建只接受已存在的策略引用；目录 `update` 只允许标签/起始页/停用，无网络绑定切换；`DeleteBrowser` 未撤销 Secret Store 凭据。 |
| `adapter/internal/sealskin/client.go` | 管理员客户端只有应用安装/补丁/删除与 Home 归档；`PatchInstalledApp` 已存在可用于更新 `provider_config` 的策略引用。 |
| `adapter/internal/httpapi/manage.go` | 面板表单 `POST /manage/browsers/{id}` 按 `action` 分派；删除需 `Reauthenticated`。 |
| 已有工作区改动、运行版本 | 开始时工作区干净（`d6775a0`）；生产 Adapter 仍为 candidate-4，控制器未应用第二层补丁。 |

## 实施与偏差

设计决定（实施前）：

1. Adapter 不持有 Secret Store 或注册表文件；导入凭据、追加策略修订与探针都由控制器第二层补丁提供管理员加密接口，Adapter 通过独立管理员身份调用。凭据只在草稿提交请求与控制器 `put` 之间的加密通道中出现，不落 Adapter 磁盘或日志。差异登记为 [DEV-049](../deviations/DEV-2026-09-18-049-proxy-secret-import-channel.md)。
2. 草稿探针在控制器进程内以冻结的公网 IPv4 执行有界协议握手、CONNECT/SOCKS5 与到探测 URL 的 TLS，私网/环回/链路本地/保留地址拒绝；它不替代每次受管理启动时在 Guard 命名空间内执行的 `run_probe`。差异与边界登记为 [DEV-050](../deviations/DEV-2026-09-18-050-proxy-draft-probe-scope.md)。
3. 草稿为 Adapter 内存对象（与 launch plan 同类，重启即失效并按记录撤销）；每个浏览器同时最多一个草稿；`secret_id` 固定为 `proxy-<browser id>`，版本号在目录记录中持久递增，保证不复用。
4. 固化顺序：追加策略修订（同内容幂等）→ 应用定义补丁 → 撤销旧凭据版本（幂等）→ 目录修订切换；每步幂等，可用同一草稿重试。切回 DIRECT 复用同一顺序，只引用已登记的不可变 DIRECT 修订。

偏差文件链接：[DEV-049](../deviations/DEV-2026-09-18-049-proxy-secret-import-channel.md)、[DEV-050](../deviations/DEV-2026-09-18-050-proxy-draft-probe-scope.md)，均已解决为候选补丁。实施中另发现两处实现细节并直接修正：控制器探针需在 CONNECT 隧道（可能已是 TLS）内再做一层 TLS，改用 `ssl.MemoryBIO` 驱动；探针请求使用随机幂等键避免控制器按 crypto session 缓存回放旧结果。

## 验收复核

| 原要求 / 验收编号 | 实现位置 | 检查与证据 | 结果 / 未测范围 |
| --- | --- | --- | --- |
| 草稿字段校验、私网/元数据地址拒绝、`none` 不带凭据 | `profile/proxy.go`（`validateProxyDraft`、`validUpstreamHost`）、控制器 `proxy_probe.public_ipv4` | Go：17 类无效草稿拒绝且不触达控制器；pytest：环回/私网/CGNAT/元数据/`localhost`/`.internal`/IPv6 拒绝，DNS 混合私网答案拒绝 | 候选隔离验证 |
| 凭据只入 Secret Store，引用四维绑定，草稿过期/替换/失败撤销 | `profile/proxy.go`、控制器 `environment_management.import_proxy_secret` | Go：导入请求授权/幂等键、版本只增、替换撤销、失败导入消耗版本、30 分钟过期后探针/应用拒绝；pytest：只返回引用、密文无明文、重复版本 409、非管理员 403 | 候选隔离验证 |
| 探针：协议/认证/TLS/出口，地址 ACL，结果脱敏 | 控制器 `proxy_probe.py`、`proxy-probe` 路由 | pytest：本机 fake socks5/HTTP/HTTPS CONNECT 与 TLS 目标，正确凭据通过、错误密码/无认证 `PROXY_AUTH_REJECTED`、跨 Profile 403、缺上游 CA `PROXY_TLS_FAILED`、目标 CA 不匹配 `PROBE_TLS_FAILED`，结果无凭据 | 候选隔离验证；真实公网代理、出口地区未测（DEV-050） |
| `proxy_required` 修订只追加、SHA 与控制器规则一致、应用与目录修订绑定 | 控制器 `append_network_policy`、`profile/proxy.go`、`directory.setNetwork` | pytest：摘要等于 `network.digest(model_dump())`、幂等、同 ID 不同内容 409、无效策略 422、HTTPS CA 私有落盘；Go：追加内容、应用补丁与目录记录一致，追加失败不改目录 | 候选隔离验证 |
| 运行中拒绝切换、下一代次生效、切回 DIRECT、删除撤销 | `profile/proxy.go`、`management.DeleteBrowser` | Go：异属记录/修订漂移拒绝且无注册表或应用变更；应用后 launch plan 与启动请求使用新策略引用；DIRECT 切换与删除撤销全部版本 | 候选隔离验证；真实代次使用新策略归 R6F |
| 面板表单、管理员/重新认证边界、通知不泄漏 | `httpapi/manage.go`（`manageNetwork`、模板） | Go：草稿/探针/应用/DIRECT 表单通知，`apply`/`direct` 需幂等键与修订，缺 `manage` 能力 403，页面与日志不含凭据；`Reauthenticated` 门槛沿用删除路径 | 候选隔离验证；真实网关 reauth 端到端由 R6B 既有测试覆盖 |

证据：[R6D 验收](../../infra/sealskin/proxy-drafts-acceptance-2026-09-18.md)；私有目录 `infra/sealskin/runtime/r6d-proxy-drafts-2026-09-18/`（Go 测试/race 日志、控制器全量 pytest 日志、输入摘要、result.json）。全模块 243 项 Go 测试、vet、gofmt、checks 镜像 race 通过；控制器补丁 545 项 pytest 通过，补丁在重新导出的干净树上 `git apply` 后与工作树逐字节一致。

## 文档与收尾

- [x] 逐项回看原始任务、计划、设计和实际行为。
- [x] 完成本项必要验证，公开报告与私有证据范围明确（[R6D 验收](../../infra/sealskin/proxy-drafts-acceptance-2026-09-18.md)）。
- [x] 相关偏差已处理并复核（DEV-049、DEV-050 已解决，均为候选补丁）；真实上游与生产验证明确归 R6F。
- [x] 更新设计/规格/组件/用户或运维说明：管理面规格、规格索引、Adapter README、Secret Store 与生命周期 README、配置示例。
- [x] 更新验收索引。
- [x] 更新开发进度与生效范围。
- [x] 更新开发计划的完成条件、剩余工作和下一项。
- [x] 核对 QA 清理（隔离树与 verify 目录已清理，仅保留日志与摘要；未创建 Docker 资源、未挂载 Docker socket）、回滚材料（补丁为第二层版本化文件，生产未应用）、链接及工作区变更。
- [x] 更新本记录与工作项索引，确认是否允许开始下一项。

收尾结论：候选代码、控制器补丁与隔离验收完成，未部署生产。下一步：按顺序选取 R6E；真实上游代理、真实代次与生产部署仍归 R6F，不得据此部署。
