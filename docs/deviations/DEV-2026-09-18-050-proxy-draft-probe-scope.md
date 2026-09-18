# DEV-2026-09-18-050 · 代理草稿探针的执行位置与范围

状态：已解决（候选补丁，未部署；真实上游代理未测）。发现日期：2026-09-18。关联工作项：[R6D](../work-items/R6D-2026-09-18-proxy-drafts.md)。

## 设计预期

[管理面规格](../specs/proxy-environment/management.md#代理配置) 要求“探针在隔离网络中验证认证、TLS、DNS 与出口，不访问宿主机/私网/未批准地址；结果带出口国家/地区供一致性策略参考”。

## 实际事实与证据

- 现有的隔离探针 `run_probe`（`profile-lifecycle.patch` 的 `network_runtime.py`）只在受管理启动时执行：需要已创建的 generation 占用、Guard 命名空间和 Relay 容器。草稿阶段没有 generation，也不应为未固化的草稿创建 Docker 资源（会产生第二条 Docker 生命周期路径）。
- 出口国家推断依赖 R5C3 一致性策略的 GeoIP 资产与运行中的 Relay 观测（`coherence_report.py`），草稿阶段没有对应代次。

## 影响与处理决定

- 处理方式：修订设计的实现范围，保留安全约束。草稿探针改为控制器进程内的有界检查（`proxy_probe.py`）：先把上游主机解析并冻结为一个公网 IPv4（字面量或 DNS 全部答案都必须是公网地址，环回/私网/链路本地/CGNAT/保留/多播、`localhost`、`.internal`、`.local` 拒绝）；再按 socks5 / HTTP CONNECT / HTTPS CONNECT（可附上游 CA）用 Store 中解析的凭据建立到批准 `probe_url` 的隧道，并在隧道内完成 TLS 验证与 `HEAD`；只返回稳定代码、冻结地址、HTTP 状态与耗时。
- 探针不产生出口国家/地区；该信息继续由启动后的一致性报告提供。探针通过只表示上游认证、协议与 TLS 可用，不替代每次受管理启动前在 Guard 命名空间内执行的 `run_probe` 和一致性门槛。
- 探针从控制器网络命名空间发起出站连接；控制器已能访问上游（启动时 `resolve_upstream` 亦在此解析）。探针不会连接私网或宿主机地址，凭据不写入日志。

## 实施、验证与文档同步

| 材料 | 更新 / 结果 |
| --- | --- |
| 实现 | 控制器 `proxy_probe.py`、`environment_management.py` 的 `proxy-probe` 路由；Adapter `ProbeProxyDraft` |
| 验收与证据 | pytest 使用本机 fake SOCKS5 / HTTP / HTTPS CONNECT 代理与本机 TLS 目标：正确凭据通过、错误凭据 `PROXY_AUTH_REJECTED`、跨 Profile 授权 403、HTTPS 代理缺 CA `PROXY_TLS_FAILED`、目标 CA 不匹配 `PROBE_TLS_FAILED`、私网/元数据/CGNAT 地址与非 HTTPS 探测 URL 拒绝；结果不含明文凭据。真实公网代理未测 |
| 设计 / 规格 / 组件说明 | [管理面规格](../specs/proxy-environment/management.md#代理配置) 已注明草稿探针范围与一致性报告分工 |
| 进度 / 计划 / 工作项 | R6D 工作项已记录 |

## 最终复核

规格的“隔离探针”在草稿阶段以控制器内有界协议探针实现，启动门槛仍由 Guard 命名空间探针与一致性策略承担；出口地区不由草稿探针提供。真实上游代理与生产验证归 R6F。
