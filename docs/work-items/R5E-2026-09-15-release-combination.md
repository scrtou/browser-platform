# R5E · r7 登录、凭据与一致性组合验收

状态：已收尾（代码/隔离 QA，未部署）。开始日期：2026-09-15。结束日期：2026-09-15。

## 目标与范围

持续目标为按计划推进到项目可发布。前置 [R5D](R5D-2026-09-14-entry-authentication.md) 和 [R2A](R2A-2026-09-15-legacy-backup-preparation.md) 已收尾。本项补 [R5](../roadmap.md#r5) 已登记的 r7 组合验证：已有入口 QA 未启用 coherence，R5C3 的真实矩阵使用 r6，不能直接合并为当前发布组合通过。

以固定 R5D C3 控制器/Adapter、r7 完整产物和匹配 Guard/Relay 为起点，在全新私有 QA 根下同时启用登录、密封 Session/专属显示、Store 凭据和运行时一致性。修复本组合揭示的实现或恢复缺口，保留各轮失败及版本事实。不会重新启用已清理的 R5D QA，也不部署生产或执行真实 Home 维护。

## 代码与所有权核对

- 已读当前进度/计划、R4B 前置、R5D/R2A 收尾、入口与一致性契约及现有真实 QA 工具。
- Caddy → Adapter `access` → Profile 当前绑定/`coherence` → 加密 SealSkin API → `session_gate` → r7 显示；网站出站另由 Relay 代次门槛控制。登录状态、Profile journal 和 SealSkin 生命周期的所有权保持。
- `prepare-network-qa.py` 已支持凭据/显示 tmpfs、私钥和 DIRECT 地址证据挂载；现有 R5D stage/coordinator 固定了旧 QA 名称和挂载集合，组合准备/清理须核对新的精确 scope。
- `check-runtime-coherence.py` / entry / recovery / rotation 提供真实页面、出口、到期及故障流程；旧封装的 r6 环境预期和无登录路径不能直接充当 r7 授权入口结果。
- `secure-backup.py` 的共享控制来源尚未包含策略引用的 `coherence-assets/`，按 [DEV-038](../deviations/DEV-2026-09-15-038-coherence-backup-assets.md) 修复；R2A 的旧生产不引用这些资产，原收尾结论保留。

## 完成条件与验证

1. 新 QA 根、密钥、账号、Profile/Home/策略与实际镜像/产物摘要可追溯；生产四容器、真实 Home、五份配置/绑定及系统 Caddy 保持。保留基础 QA 权威；如使用已授权的两台外部轻量端点，生成本项独立配置/凭据并清理本项服务/记录。
2. 登录后固定入口在当前一致性报告允许时发放可用 Session；只读/匿名/跨主体请求不启动实例，重复进入复用同代次。真实页面、环境/出口/网络报告及 HTTP/WebSocket 路径有证据。
3. 在 r7 组合记录 C01–C05 的适用矩阵：显式地区/时区拒绝与 advisory、真实出口变化、报告到期/数据源故障及恢复。报告 UNKNOWN 或阻断时不能凭登录或私有能力绕过，已有网站隧道按门槛关闭；恢复保持应保留的数据/身份，不伪造新鲜报告。
4. 当前 Store 凭据撤销与入口注销分别验证其实际影响，无直连回退；控制/Worker 恢复后材料、登录和一致性门槛满足契约。
5. 组合的加密包包含所需一致性资产、密封状态、账号及身份；恢复到新私有 QA 目录，核对资产/引用和浏览器数据。现有新/旧格式备份边界回归保持，不能以本项 QA 替代 R2 真实 Home 恢复。
6. 相关代码/工具测试、最终版本核对、临时资源清理、公开敏感/语法/链接及 diff 检查通过；更新组件、设计/规格、验收/偏差索引、进度/计划和本记录后收尾。

## 发布与未测边界

当前预期复用固定 C3/r7；如需修改产品代码，另固定新候选并按影响重验，不能把旧镜像证据扩大为新版本通过。最多两个 QA 浏览器，按资源情况顺序执行。当前主机为 Debian 12，不做整机重启；Mac/Trilium、真实站点账号、生产 r7 迁移、linger 与 Debian 13 保留 R2/R4B 条件。

## 实施进度

- `backup-tests-1/`：共享资产修复与原新/旧格式共 101 项通过；DEV-038 的真实组合恢复仍待验证。
- `candidate-1/qa` 为本项新 QA，实际控制器固定 C3、Worker 固定 r7，同时挂载 Store/显示 tmpfs 与 DIRECT 地址证据。组合准备器直接建立新账号/应用/策略，不经过旧 R5D stage 的挂载替换路径。
- `endpoints-1/`：新随机名称、凭据和两个轻量服务；新增 HTTPS `/client?nonce=<32hex>` 提供同源合成 Cookie/localStorage/IndexedDB 页面，原观察域名白名单保持。33 项端点回环检查、10 个公网 TCP 端口和 12 个 DNS 检查通过。第二端点当时时钟偏差约 22 秒，观测域名固定到时间校验通过的第一端点；第二端点只用于实际出口，不放宽 ±5 秒校验。
- 准备和基础客户端的工具失败按轮次保留：预留但未初始化的主密钥与 Store 初始化冲突，已保存未用材料后正常初始化；合法显示参数被误判为 URL 能力、剪贴板目标瞬时未就绪、Playwright APIRequestContext 不使用 Chromium 域名映射均为 QA 工具问题，分别修正后新目录重验。实际 C3/r7 二者已取得 JP 代理/US DIRECT 的新鲜报告及真实页面存储，尚未据此宣告组合全项通过。
- `base-4/` 六项通过：匿名/只读/跨 Profile/CSRF 不启动、真实登录和 HTTP/二进制 WebSocket、同代次复用、公开健康脱敏、注销隔离及两个 Home 的三类存储。
- `faults-1/`、`faults-2/` 保留部分结果：GeoIP 缺失时普通显示与正确私有能力均 503，恢复文件后原绑定/数据恢复；C3 控制器重启保持密封 Session、Store 和浏览器数据。两轮分别停在 QA 的恢复状态解析及旧显示 Cookie 预期；未标整轮通过。
- `resume-1/` 两项通过：移除精确 QA tmpfs 材料后，正常 resume 重建显示/代理材料并保留 Worker/Session/operation 与三类存储。旧显示 Cookie 按既有恢复意图契约返回 401，原登录经固定入口重新交接同一 Session。停止 QA 控制器后的实际门槛到期约 0.60 秒关闭既有网站隧道，控制器恢复后取得新 nonce，原数据保持。
- `policies-1/` 三项通过：显式时区和国家约束分别拒绝登录后的固定入口及正确私有能力；advisory 保留告警并允许使用。三种策略均保留实际 r7 的 `zh-TW` / `Asia/Taipei`，不修改环境；独立 DIRECT Profile 保持允许。
- `rotation-1/` 前三项通过，已取得 JP → UNKNOWN → HK、独立历史及 recheck/block 的真实结果，返回 JP 仍阻断。新代次已取得允许的报告，但 QA 将只在阻断时存在的可选 `exit_change_blocked` 当作必填而报 KeyError；修正可选字段读取，在新目录完整重验，原轮次仍为部分结果。
- `rotation-2/` 四项完整通过：两个 Store Profile 共用入口而保持独立报告和历史，真实 JP → UNKNOWN → HK 后 recheck 放行、block 锁定；返回 JP 仍阻断，正常停止/新代次取得允许报告，两个 Home 的 Cookie/localStorage/IndexedDB 数据保持，正常停止清理通过。
- `revocation-1/` 保留部分结果：撤销停止 Relay 并关闭浏览器 WS/WSS，关闭确认使清理按约定保持 pending；QA 在 30 秒内仍读到浏览器等待连接超时的旧页面，整轮失败。继续检查实际页面已显示代理拒绝错误（`revocation-diagnose-1/`），改为最多 90 秒观察正常错误页，不修改浏览器超时或网络策略；须完整重验，不能将此诊断视为整轮通过。
- `revocation-2/` 在新代次预检失败：跨轮次暂停期间两个轻量端点达到原定六小时寿命，需核对实际退出后按原范围重新启动、保留前一进程证据。未知启动记录经正常停止收回，保留 Home；本轮未进入撤销测试。
- `revocation-3/` 三项完整通过：Relay 约 0.74 秒退出，浏览器 WS/WSS 关闭，新请求约 70 秒后显示正常代理错误；5 项原生直连尝试失败、Worker 出站抓包无回退。关闭确认导致清理 pending，取消后相同撤销操作重试完成；已撤销版本不能新建 Worker，新的未撤销版本保留两个 Home 的三类存储。
- `artifact-check-1/` 核对 32 个运行文件、50 个 Go 输入、四个二进制、实际运行 Adapter、Worker/Relay 构建输入及镜像、三个一致性资产和备份测试输入一致；尚需恢复后复核与最终清理。
- `faults-3/` 五项完整通过：GeoIP 缺失阻断正常登录和正确私有能力，恢复数据源后保持原绑定/数据；控制器 restart、同代次 tmpfs 重建、实际门槛到期与新 nonce 恢复均通过。
- `backup-restore-1/` 已通过加密创建/验证/解密、缺少当前账号拒绝、退役源 QA、合并备份后撤销；随后 QA 错把规范化账号 JSON 的空白/顺序变化当作内容变化而失败。结构化比较证明账号表一致且 Bob 仍禁用，修正 QA 比较；增加仅接受源 QA 已退役、归档再次验证、目标尚不存在的离线检查点继续入口，保留第一次失败，不重启已退役源环境。
- 离线继续的第一轮在验证前因 QA 局部变量遮蔽函数失败，暂存已清空；第二轮完成新目录/身份恢复，但准备器误将 QA HTTPS 映射到容器 443（源控制器实际为 8443），Adapter 保持 CONTROL_UNAVAILABLE。已核对原移除前端口证据，修复映射；只重建尚无 Worker 的精确恢复 QA 控制器，保留恢复目录与操作日志，不改 TLS 验证。

私有证据根：`infra/sealskin/runtime/r5e-release-combination-2026-09-15/`。全部 HTTP/Session 原始响应与错误日志保持私有。

- `recovered-client-1/` 两项通过：备份后禁用的账号仍被拒绝；A 经真实登录启动新代次，镜像/Home 与三类存储保持，r7 产物、全部三个一致性资产、Store、专属材料及新鲜报告通过。B 仅为空的禁用 QA 占位，不声称恢复其 Home。
- 最终 `base-4`、`faults-3`、`policies-1`、`rotation-2`、`revocation-3`、`recovered-client-1` 共 23 项独立实际检查通过。`artifact-check-2/` 再次核对新根的实际运行文件、二进制、镜像与资产一致。
- `cleanup-1/` 核对源/恢复代次资源为零、两套进程停止、两个基础夹具/网络及两个匿名卷移除、四个空 tmpfs 根删除、QA 端口关闭；生产四容器及五份配置/绑定保持。`external-cleanup-1/` 停止并删除两个远端服务目录，准确移除本项五条 A 记录，权威 UDP/TCP 与公共随机查询验证不存在，基础权威/委派/SSH/用户端口规则保留。
- `static-preclose-1/`、`static-final-1/` 覆盖公开敏感扫描、冻结产物、链接/锚点、JSON/Python 语法及实际源码 whitespace。原版本化 patch 的 65 条空白上下文警告逐条核对，其他 diff 与展开源码通过；原 Git index 保持。私有 QA Home、归档/解密包及密钥作为敏感证据保留。

## 收尾检查

- [x] 组合准备及代码/资产缺口处理；DEV-038 已解决，QA 失败历史保留。
- [x] r7 实际入口、C01–C05 适用变体及故障/撤销/恢复矩阵；没有扩大其他版本和原示例的证据。
- [x] 加密恢复及 101 项回归、恢复前后版本核对。
- [x] QA 清理、生产保持、组件/设计/规格/验收/偏差索引、进度/计划与静态检查。

收尾结论：已完成本项代码、隔离验收和文档交付，未部署。详见 [验收报告](../../infra/sealskin/release-combination-acceptance-2026-09-15.md)。R2 的真实 Home/整机/linger/目标平台、R4B 的 Mac 分项和生产切换仍待相应条件；下一步按计划处理这些前置，本次未启动 R6 或生产维护。
