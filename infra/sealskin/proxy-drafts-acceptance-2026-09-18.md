# R6D 代理草稿、隔离探针与 proxy_required 修订验收

日期：2026-09-18（UTC）

本报告覆盖 R6 管理面的第 4 步候选代码。生产 Adapter 仍为 candidate-4，控制器仍为 `0.3.2-entry-auth-v1-2ba57382ce75c8f9`，未替换二进制、账号表、控制器、Caddy、真实 Home、Secret Store 或正在运行的 Session。详细脱敏结果保存在被忽略的 [R6D 私有结果](runtime/r6d-proxy-drafts-2026-09-18/result.json)。

## 实现范围

- 控制器第二层补丁 [environment-management.patch](lifecycle/environment-management.patch) 在 R6C 归档端点之外增加管理员加密路由 `/api/admin/environment-management/`：`proxy-secrets` 调用同一 `FileSecretStore.put` 并只返回引用；`proxy-probe` 在控制器进程内把上游冻结为公网 IPv4，执行 socks5 / HTTP CONNECT / HTTPS CONNECT 握手与隧道内 TLS `HEAD`，只返回稳定代码；`network-policies` 在注册表锁内用控制器 `NetworkPolicy` 模型校验后只追加修订，摘要按控制器规范规则计算，同内容幂等、同 ID 不同内容拒绝，HTTPS 上游 CA 作为 `network-secrets/` 下 0600 独占文件落盘。差异登记为 [DEV-049](../../docs/deviations/DEV-2026-09-18-049-proxy-secret-import-channel.md) 与 [DEV-050](../../docs/deviations/DEV-2026-09-18-050-proxy-draft-probe-scope.md)。
- Adapter：`proxy_template` 配置（owner 必须等于启动身份、Relay/探针镜像摘要、批准探测 URL）；SealSkin 管理员客户端新增导入、探针、追加与撤销方法；Profile 目录新增按浏览器递增的 `proxy_secret_version` 与网络绑定修订；草稿为内存对象，30 分钟过期、每浏览器一个、替换即撤销旧版本；`proxy_apply` 要求探针通过、修订未漂移、重新认证、verified Stop 后资源为零，按“追加策略 → 应用引用 → 撤销旧版本 → 目录修订”顺序执行且每步幂等；`network_direct` 切回已登记 DIRECT 修订并撤销全部代理凭据；删除浏览器时撤销全部版本。面板表单字段处理后清空，日志与页面不含凭据。

## 隔离验证

Adapter（主机 Go 1.27.1，只读源码；race 在无网络的 checks 镜像内以 gcc、`CGO_ENABLED=1`、`-p 1` 串行执行）：

```text
go test -count=1 ./...                 9 packages; 243 passed, 0 failed, 0 skipped
go vet ./...                           PASS
gofmt -l .                             no output
go test -race -p 1 -count=1 ./...      PASS (9 packages)
```

新增 Go 测试覆盖：模板校验；草稿字段/协议-认证配对/私网、环回、元数据、CGNAT、`localhost`、`.internal`、单标签、IPv6、userinfo 主机拒绝且不触达控制器；导入请求的 secret ID、版本、四维授权与幂等键；版本只增不复用（失败导入也消耗版本）；草稿替换撤销旧版本；探针请求携带引用、授权与模板探测 URL；未探针/探针失败/过期/未知草稿拒绝应用；修订漂移与运行中（异属记录）拒绝且不产生注册表或应用变更；追加失败不改目录；应用后的策略内容、应用补丁、目录记录与下一次启动使用的策略引用；切回 DIRECT 的撤销；删除时撤销全部版本；面板表单的通知、能力边界与凭据不进入页面或日志；SealSkin 客户端对四个新接口的请求/响应校验与引用格式。

控制器补丁在从 checks 镜像导出的固定 R5D 树上验证（`git apply --check` 后重新导出干净树再次 `git apply` 并逐字节比对通过）：

```text
python3 -m pytest -q -o asyncio_mode=auto tests           545 passed, 0 failed（含新增 11 项与 R6C 归档 1 项）
```

新增 pytest 使用本机 fake SOCKS5 / HTTP / HTTPS CONNECT 代理与本机 TLS 目标（测试内生成 CA、代理与目标证书）：导入只返回引用、密文不含明文、可按授权解析、重复版本 409、格式错误 422；三条路由对非管理员 403 且不写入 Store；策略追加摘要等于 `network.digest(NetworkPolicy(...).model_dump())`、注册表 0600、幂等重试 `created=false`、同 ID 不同内容 409、无模式/认证不匹配/未知字段/外部 CA 路径 422；HTTPS CA 私有落盘并参与摘要；socks5 正确凭据通过（`HEAD` 到目标、结果 204）、错误密码 `PROXY_AUTH_REJECTED`、跨 Profile 授权 403、HTTP/HTTPS CONNECT 通过、HTTPS 代理缺 CA `PROXY_TLS_FAILED`、目标 CA 缺失 `PROBE_TLS_FAILED`、无认证对需认证代理 `PROXY_AUTH_REJECTED`；请求校验与私网上游 `NETWORK_UPSTREAM_ADDRESS_INVALID`；结果不含凭据。

## 未覆盖与后续

没有真实公网代理、真实 Relay/Guard 代次或真实浏览器参与；探针通过不等于该代理在受管理代次中可用，启动时仍由 Guard 命名空间探针与一致性门槛把关。探针不给出出口国家/地区。控制器第二层补丁与 Adapter 候选均未部署，生产删除、创建与代理路径没有变化；缺少补丁接口时草稿创建返回不可用，不会回退到明文文件策略。DIRECT 生产前置、R6E 自定义指纹与 R6F 真实客户端/回退组合仍未实施。

R6D 可收尾为未部署候选；下一计划项为 R6E。任何生产部署仍须等待 R6F 组合 QA 与明确维护授权。
