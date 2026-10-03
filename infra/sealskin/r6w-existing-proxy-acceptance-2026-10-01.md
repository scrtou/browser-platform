# R6W · 新建浏览器复用已有代理验收

结论：已收尾并部署（2026-10-01）。新建浏览器的网络下拉展示所有 accepted 代理，认证代理无需重填账号密码；服务端为新浏览器追加精确授权并物化独立策略。原用户浏览器、Home、会话、凭据、目录和执行器保持。工作项：[R6W](../../docs/work-items/R6W-2026-10-01-existing-proxy-create.md)。

## 实现与范围

原问题由两层限制共同造成：UI 排除认证代理，后端拒绝未在代理修订初始 grants 内的新 Profile。新增控制器加密管理员授权接口，以 owner/profile/home/app、原凭据版本及密文摘要、创建请求摘要为边界；HMAC 认证的私有追加文件不修改原 AES-GCM 版本，Adapter 不获取旧密码。确认授权后追加目录 allowed_profiles，并保存完整上游/引用/独立 policy 绑定。

创建先校验应用和参数并持久化请求摘要/creating 意图，再授权、追加策略、保存绑定和安装应用。同键改参无外部副作用；重启后保留未完成意图且不能启动，原请求可重试。策略/安装的控制器请求键也按派生 browser ID 隔离，避免不同 UI 管理员通过同一管理员 API 会话使用同名键时串用缓存。

[DEV-117](../../docs/deviations/DEV-2026-10-01-117-create-network-binding.md) 已修复：完整网络字段漏存、副作用早于校验、未完成创建启动校验，以及跨管理员控制器缓存碰撞。原 Ready 绑定检查和未完成记录启动禁令没有降低。

## 验证

| 检查 | 结果与边界 |
| --- | --- |
| Go/HTTP | 完整 test/vet，认证代理下拉与表单解析、引擎/指纹联动回归通过；精确授权/独立 policy、无明文落盘、无效请求、禁用代理、同键改参、并发重复、授权/策略/安装失败后的 NewService 重建重试通过 |
| 并发检查 | Profile、SealSkin client、HTTP 全套 race 通过；之后仅追加确定性的策略/安装键隔离，针对该改动的控制器缓存模拟测试在旧版失败、最终版通过，最终 Profile test/vet通过 |
| 控制器 | 554 项通过；原密文不变、追加授权并发/持久/幂等、四维身份拒绝、跨 owner/版本/请求拒绝、篡改/不安全文件拒绝、恢复锁与撤销覆盖；真实加密 API 和私有 SOCKS5/TLS 请求通过 |
| 备份 | 85 项通过；实际 age 加密备份/验证/新目录恢复、追加授权字节及解析保持、恢复锁与备份后新撤销合并通过 |
| 实际浏览器 | 两个独立 Chromix QA Home 使用同一认证代理版本，各自策略和运行代次；经 SOCKS5 的 HTTPS、IPv4/IPv6/DNS 直连阻断、代理故障关闭及恢复通过。控制器重启后两组容器 ID/启动时间、Session 和授权保持 |
| 撤销 | 对 QA 共享版本撤销，按原实现失效租约、阻断 Relay、正常停止并清理两个受影响代次；Home 保留，再授权拒绝。撤销测试首版误认为会保留 Worker，已按原 `secret_runtime.revoke` 明确的正常清理契约修正断言；未修改实现或减弱原要求 |
| 发布与隔离 | 控制器完整 97 文件中只改2个，Adapter冻结97文件/10路径差异；Compose仅新增 controller image覆盖。运行镜像/可执行文件摘要、ready、加密新接口、原容器/Session/目录/凭据/spool/runner 比对通过；QA资源归零 |

最初旧网络 QA 的模拟 Worker 不满足现有显示认证契约，保留失败和正常清理证据后改用实际 Chromix 验收。真实 QA 的私有 HTTPS CA仅通过隔离 admin wrapper 加入测试 policy，未写入生产配置；实际浏览器出网证据来自其网络命名空间中的认证 TLS 探针，不冒称目标 Mac/Trilium 页面验收。

## 发布身份与操作

- 最终 Adapter：`28b0929c679a52240c210cc1eefbc5e55ccf84f959280a4cd13608467e01b5d8`。
- 控制器：`sha256:1d93d6b8a92e7d431a603d4f2778b92aa2e91e8943df25c73f49f9013ef8a40e`；基于 R6J1 `ad21dd6d…` 的两文件增量。
- 生产追加 Compose层：[compose.proxy-reuse.json](compose.proxy-reuse.json)，保留容器标签中列出的原配置顺序；没有发布 R6I/R7G。
- 准备器：[prepare-proxy-reuse.py](lifecycle/prepare-proxy-reuse.py)，补丁：[proxy-create-authorization.patch](lifecycle/proxy-create-authorization.patch)。完整准备器补丁链已验证可应用，未把全链部署生产。
- 生产未执行新增浏览器或新凭据授权，以保护用户数据；生产接口采用缺字段请求确认422拒绝且零副作用，功能创建在隔离环境完成。

首轮发布后补齐确定性缓存键隔离，第二次仅更新 Adapter。首轮源包、二进制和回执保存在私有 `initial-release/`，最终源包/清单在 `adapter-source/`、`adapter-manifest.json` 与 `adapter-delta.json`。`deployment.json` 是最终身份，`final-adapter-before/after.json` 记录最后一次保护比对；原R6V备份和首轮R6W备份均保留。存在追加授权后旧控制器不能直接回退，否则无法解析新授权；先按正常生命周期处理相关绑定，不能通过恢复旧目录或删除授权/墓碑回退。

新鲜运行复查：Work/Chromix healthy，原“测试”offline，Personal原有 `PROXY_UPSTREAM_UNKNOWN` 保持，未扩大为全部网络健康。目标客户端新下拉的实机反馈仍属客户端计划，不阻塞此次服务器功能交付。

私有证据根：`infra/sealskin/runtime/r6w-existing-proxy-20261001/`，包括 test/vet/race、控制器/备份日志、真实浏览器/重启/撤销、清理和发布回执；公开记录无密码、Cookie或授权 Session URL。
