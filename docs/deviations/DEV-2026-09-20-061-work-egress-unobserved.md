# DEV-061 · Work 公网不可达反馈与健康覆盖缺口

状态：部分处理（受管理 DIRECT 已部署，新代次健康、Worker 网络与 Mac 真实公网页面通过；当前组合独立重建/三类存储/实际回退通过；生产真实 Home 正常重建/页面已完成，原书签/登录项不适用；完整客户端矩阵仍待验证）。日期：2026-09-20，更新：2026-09-30。
关联：[R7 方案工作项](../work-items/R7-DESIGN-2026-09-20-browser-workspace.md)、[R6H](../work-items/R6H-2026-09-20-management-ui-deployment.md)。

## 预期与事实

用户查看 Tab 第二版后反馈 Work 不能访问公网。只读核对发现：

- Work 为 running、1 record/1 Worker、0 managed resources、0 orphan；Profile 无 network policy、无 Camoufox artifact，Wayland 开启。
- 唯一挂载 Work Home 的 Worker 只连接一张 `Internal=true` 的 bridge 网络；Docker 附件无 IPv4 gateway，容器 `/proc/net/route` 无 IPv4 默认路由。
- 缓存报告显示 healthy，进程/显示通过，但 proxy 为 `not_applicable / PROXY_NOT_CONFIGURED`，没有成功的公网出站检查。代码 `profile/health.go:evaluateRunning` 对无策略绑定不执行受管理出网检查。
- 没有请求真实浏览器导航、发起公网探针、读取用户浏览记录或修改 Firefox 设置；未证实其应用层代理、IPv6、DNS、网站错误及历史网络变更的完整因果链。因此确认的是缺少直接 IPv4 出网路径和健康覆盖不足，不宣称所有根因已定位，也不把故障归因于 Tab CSS。

## 处理决定

列为 R7A 最高优先级：按浏览器实际网络路径只读分层诊断，再在授权维护窗口修复/迁移受管理 DIRECT 或代理；不能用给 Worker 接公网 bridge、修改全局防火墙或重启全部容器绕过隔离。网络 unknown/unobserved 必须与运行正常分开展示；完成条件包含真实浏览器 HTTPS/DNS、出口、失败不直连、重建保持和数据复核。

本次只编方案，不实施修复。R6F 与 R6H 的历史运行/发布证据保留原范围，不再延伸为当前 Work 公网成功。

## R7A 更新

2026-09-21 复核时 Work 已由此前管理动作停用并安全停止，当前为 0 record / 0 Worker / 0 resource；R7A 没有重新启动旧代次。Adapter 候选已把无策略运行代次标为 `network_mode=unmanaged`，新增 `egress=warn / EGRESS_NOT_CONFIGURED`，使进程/显示正常时整体为 degraded；已配置新策略但旧代次尚未采用时使用 `EGRESS_UNMANAGED_GENERATION`。全量 test/vet/gofmt 与相关包 race 通过，见 [R7A 验收](../../infra/sealskin/r7a-work-egress-diagnosis-acceptance-2026-09-21.md)。

健康覆盖缺口在候选源码中已处理，但尚未部署。

## R7B 更新

R7B 进一步确认现行 Work 兼容镜像没有 Firefox Relay 锁定配置；只绑定 network policy 会使浏览器直连并被 Guard 正确阻断。候选在精确既有 Firefox/Wayland/退出/显示认证父层上增加最小受管理网络配置，独立 DIRECT QA 已通过真实公开 HTTPS、四类原始绕过拒绝、网关故障 fail-closed、正常 Stop/新 generation 和 Cookie/localStorage/IndexedDB 恢复，详见 [R7B 验收](../../infra/sealskin/r7b-managed-work-egress-acceptance-2026-09-21.md) 与 [DEV-065](DEV-2026-09-21-065-work-firefox-proxy-policy.md)。

生产 Work 仍停用、停止、0 资源，现行控制器也尚未安装 DIRECT 地址证据挂载，因此偏差保持“部分处理”而非冒充线上已修复。R7F 固定发布、回退和真实 Mac/Trilium Work 公网验收通过后才能关闭。

证据在忽略目录 `infra/sealskin/runtime/r7-design-2026-09-20/`：work-inspect、work-health、work-topology、work-ipv4-routes；公开记录不含 Session、私网地址、Home 路径或凭据。

## R7F 生产更新 · 2026-09-30

用户完成受控迁移、启用并从固定入口打开后，Work revision 8 使用批准的受管理 Firefox/Wayland 镜像和独立 DIRECT policy；新代次为 1 Worker/5 resources/1 Relay/1 Guard/2 networks，12:47 UTC 新鲜健康为 `DIRECT_OK`。实际 Worker 经 Relay 的域名 CONNECT、验证 TLS、公开 HTTPS 200/预期内容通过，原始公网 TCP 与 metadata 尝试失败；12:51 UTC 有效 Docker/公网 DNS 请求分别被权限/路由明确拒绝，见 [生产验收](../../infra/sealskin/r7f-legacy-migration-acceptance-2026-09-30.md) 与 [探针修正](DEV-2026-09-30-078-work-dns-probe-evidence.md)。

原 Home/应用保留，迁移后启动前的 31 个数据库摘要与独立恢复副本一致。该文件证据及 Worker 网络探针不替代 Firefox GUI、旧登录/三类存储读取、正常重建、实际回退或 Mac/Trilium 验收；这些完成条件仍保留，本偏差继续部分处理。上方未部署/停止的段落为各阶段历史。

同日后续用户确认：当前 Mac 浏览器中 Work/Personal 公网页面均正常，原有书签/登录确认项“不适用”。真实浏览器公网页面缺口已补齐；正常重建、三类存储、实际回退和完整目标客户端矩阵仍未完成，本记录保持部分处理。

同日独立恢复补证：固定当前线上二进制与镜像组合，真实管理页迁移/回退、Wayland 公网页面、正常停止新代次三类存储、网关故障拒绝和再次迁移读回均通过，干净复跑及两次 QA 清理完成；15:29 UTC 生产身份保持且均健康。见 [独立验收](../../infra/sealskin/r7f-work-recovery-acceptance-2026-09-30.md)。生产 Work 真实 Home 重建和完整目标客户端矩阵仍未执行，本偏差保持部分处理。

同日生产重建后补证：Work 已正常停止/零资源、新停止时点 5,938 条目加密备份/独立恢复及 5,740 个 Home 文件一致，固定入口新代次的原 Home/应用/策略、浏览器/显示/DIRECT 与四类绕过拒绝均通过。用户确认重开后页面和输入正常，原书签/登录项“不适用”。352 文件服务器材料已定版；早期“生产真实 Home 重建仍未执行”不再是当前待办。完整目标客户端与生产三类存储的证据边界保留，详见 [生产重建](../../infra/sealskin/r7f-work-production-rebuild-acceptance-2026-09-30.md)和[父项复核](../../infra/sealskin/r7f-completion-review-2026-09-30.md)。
