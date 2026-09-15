# R5D · 入口登录、Session 授权与各层脱敏验收

[工作项](../../docs/work-items/R5D-2026-09-14-entry-authentication.md) · [访问配置与维护](entry-auth/README.md) · [Worker 显示材料](../browser-access/README.md) · [验收索引](../../docs/acceptance/README.md)

日期：2026-09-14 至 2026-09-15，UTC。结论：候选 3 与 r7 Worker 的代码、独立 HTTPS/真实客户端、恢复和凭据边界验收通过，临时 QA 已清理，文档和静态核对完成，工作项已收尾。生产四容器、系统 Caddy、真实 Home 和原绑定保持；本报告不表示已经发布。

后续 [R5E 组合验收](release-combination-acceptance-2026-09-15.md) 已在同一固定 C3/r7 上补启用 coherence 的适用组合、Store 撤销和加密新私有根恢复。本报告当时未启用 coherence 的范围与失败历史保持。

## 固定版本

| 对象 | 固定身份 |
| --- | --- |
| SealSkin 上游 | commit `2b13a42483c1dc7d367d5c340437bdc8ecd84bb4`，基础 `0.3.2-ls58@sha256:d52c155eb78882b27c7780e77df335939d46cd06a514c9fa310039307542ee6a` |
| 组合 patch | SHA-256 `e8da73396e7756abe8628e30161b37a17063ee3da368b92d686a7d692015d45c` |
| 控制 runtime | `browser-platform/sealskin:0.3.2-entry-auth-v1-0e2bdae7d717825a-pkg-9a7e6b5738e3`；ID `sha256:773f8f4a5e62bb91ff0cd55d9ca9eeade722835cbdd51a5be1d48946ae459cff` |
| 控制 checks | 同标签加 `-checks`；ID `sha256:1ded528ab852f1b86dfd3381813ab35b6e779427189def083e7b4e0c5633fd13` |
| Adapter | Go 1.27.1；`profile-adapter` SHA-256 `b6c5cf217813c024e7bbac119cf2a353bf6a934b81875f247ef658b59015000a` |
| 账号 CLI | `profile-accounts` SHA-256 `371727090ef96071c50766ad9d7f172caaa8520dd6f7c2ec52be83a23db67381` |
| r7 Worker | `browser-platform/camoufox:0.5.6-beta.30-r7-entry-a434ead635a40ccc`；ID `sha256:4baf6233f9410477937eeb4cca40e6a046b2cbed951ec3c49206c40976987d20` |
| 环境产物 | `env-tw-camoufox-r7`；SHA-256 `bc05e61905c4bea3f2a98a035c1267b6715cbb1b01789023cc7f2b7b41bcfdf0` |
| 真实客户端 | Chromium `151.0.7922.34`，Linux，独立网络命名空间；Caddy `v2.11.4` |

以下相对证据路径均位于本机忽略目录 `infra/sealskin/runtime/r5d-entry-auth-2026-09-14/`，简称证据根。它含私有账号、密钥、日志、响应和浏览器数据，不随公开仓库分发。候选 1/2 和中间失败保留，不作为发布身份。

`candidate-3/build/payload/manifest.json` 固定 32 个运行文件、上游原文件、依赖和构建输入；`candidate-3/adapter-build.json` 固定 50 个 Go 输入及四个二进制。`final-artifacts-1/result.json` 已核对源码、payload、5 个包装输入、50 个 Go 文件、四个二进制、5 个 Worker 构建文件、实际镜像标签 ID 和 r7 产物全部一致。Worker 构建见 `worker-build-1.json`；完整产物成功报告为 `infra/camoufox/evidence/acceptance-r7-2-2026-09-14.json`。

## 代码与配套检查

| 检查 | 结果与证据 |
| --- | --- |
| 固定 C3 镜像 Python | **534 passed**，0 skipped；`candidate-3/python-image-tests-1/` 的 XML、日志及运行结果 |
| Adapter 全包 race | PASS；`go-race-final-3/`。使用 C3 checks 镜像的 gcc、Go 1.27.1、`CGO_ENABLED=1` 和可执行的临时目录 |
| Adapter vet | PASS；`go-tests-final-1/vet.log` 及该目录的逐检查结果 |
| 生命周期包装 | 首轮 **82 passed、37 skipped**，`wrapper-tests-final-1/`；跳过原因为未指定 age，未将 skip 计作 PASS |
| 加密备份补验 | 指定固定 **age v1.2.1** 后 **37 passed、0 skipped**，`wrapper-tests-final-2/`；最终包装覆盖为 82 项加 37 项 |
| r7 产物/存储 | 完整重放、两个 QA Home 各十次重建、三类存储和同版本离线恢复通过；独立于下述正常显示验收 |
| 私有 TLS | 正确信任/名称通过，错误 CA、错误名称拒绝；`candidate-1/qa/access/tls-recovery-result.json`。最终真实客户端同时使用修正后的私有通道 |
| 发布配置 | `release-review-2/` 的两个 Caddy validate 和临时账号表加载/check 通过；`release-review-2-validation/result.json` 的 Compose 合并、固定镜像、原挂载与 loopback 端口检查通过 |

控制测试包括账号表权限/链接/格式、PBKDF2/限流/并发、CSRF/完整 Origin、交接原子消费与过期、恶意路径/重定向、失效后关闭已升级连接、Session 密封迁移及逐点写入中断/错误密钥、显示挂载/恢复/清理、备份配对和当前账号授权覆盖。测试用临时账号与 QA 状态；真实服务行为按下表单独证明。

## 真实 HTTPS 客户端矩阵

最终 `client-qa-13/client-result.json` 于 2026-09-15 **00:29:52–00:31:38 UTC** 完成，13 项 PASS，收到 2,180 个实际二进制显示帧，客户端 URL 未出现后端能力。两个 Profile 使用独立 QA Home；入口和 Session 使用两个受信任 HTTPS origin。登录期限缩短为 15 秒、ticket 为 5 秒以验证失效，产品默认仍为 1,800/30 秒。

| 场景 | 实际结果 |
| --- | --- |
| 未登录、错误密码 | 拒绝受保护入口/健康/显示，未创建 Worker |
| Profile 授权与 CSRF | 跨 Profile、错误 CSRF 拒绝，未调用生命周期创建 |
| 表单、Cookie、交接与画面 | 真实导航/表单保留完整 Origin（含端口）；Cookie 的 Secure/HttpOnly/host-only/SameSite 属性正确；兑换后为干净 Session URL，真实画面到达 |
| 跨 Session HTTP/WebSocket | 使用另一 Session 的显示授权不能读取或升级连接 |
| 重复交接 | 复制同一登录到无脚本临时上下文，点击真实“继续”并接收真实授权文档；显示 Cookie 复用，交接本身保留原连接 |
| ticket 单次使用与画面接管 | ticket 重放拒绝；第二个完整 Selkies 客户端接管旧 primary，Worker/Home/Session 保持 |
| ticket 到期 | CDP 在真实 POST 的响应阶段截住 303，未兑换 ticket 到期后再访问，拒绝 |
| 注销 | 关闭该登录主体的显示，另一主体显示及两个 Worker 保持 |
| 禁用账号 | 当前显示关闭，Worker/Home 保持 |
| 登录到期 | 到期关闭实际显示连接，Worker/Home 保持 |
| journal 绑定变化 | 关闭不再匹配的显示授权，无生命周期创建/删除 |
| 控制容器真实 restart | 从密封状态恢复原 Session/Worker，页面 Cookie/localStorage/IndexedDB 保持 |
| Worker 原代次 resume | 正常停止该 QA Worker，移除其专属 tmpfs 材料，再经原 resume API 重建材料并恢复；Worker/operation/Session 与三类存储保持 |

详细状态、请求阶段与主机动作见该目录的 `display-states.json`、`host-actions.json`、`controller-restart.json`、`worker-resume-response.json` 和 `observations/`。真实页面报告使用存储 ready 标记及每次请求 nonce，避免把早先剪贴板结果当作恢复后的观测。

Selkies 的固定上游只允许一个 primary：新完整客户端向旧连接发送 `KILL`，再以 1000 / `Superseded by new client` 关闭。这里分别验证重复交接不撤销授权，以及完整客户端的正常接管；没有新增多控制端协作，也没有把上游接管误记为网关注销成功，见 [DEV-035](../../docs/deviations/DEV-2026-09-14-035-handoff-backend-capability.md)。

QA 客户端采用 `--network none`，经私有 Unix socket 转发到固定 QA Caddy，在自己的 loopback 维持真实 TLS/Host/Cookie/WebSocket。宿主 socket 目录 0700、文件 0600，检查 `SO_PEERCRED`；错误 UID 的实际连接被拒绝。客户端网络与临时代次网络分开，修复和失败证据见 [DEV-036](../../docs/deviations/DEV-2026-09-15-036-client-host-network-change.md)。

## 材料拒绝与 S 组边界

`worker-auth-negative-2/result.json` 使用固定 r7、有效环境产物和真实默认 `/init`，验证五种情况：**缺失输入、错误 Session、文件权限过宽、符号链接、可写输入挂载**。五项均出现 `SESSION_AUTH_INPUT_INVALID`，nginx 未开放显示监听。五个专属容器及临时挂载已清理。

`runtime-security-3/result.json` 在控制器重启和 Worker resume 后于 **00:33:28 UTC** 完成：**407 个扫描面，无已知秘密命中**。两个 Home 分别扫描 89/90 个文件，每个 Worker 观察 50 个进程，按实际 UID（包括 nginx 的 UID 33）读取环境，没有遗漏仍存活进程。Session 密封、专属只读 tmpfs 的归属/权限/绑定通过；正确 Basic Auth 两次 200，缺失/错误六次 401，Worker 保持。

| 规格 | 本项覆盖与保留范围 |
| --- | --- |
| S01 | 运行扫描覆盖 QA 普通状态、两个 Home、Adapter 配置、Docker inspect、进程环境/argv 与日志，无已知密码、私钥或后端 Session 能力；密文和专用秘密目录单独核对。r7 产物与公开文件另做静态核对；真实用户 Note、生产 Home 未扫描 |
| S02 | 上游凭据维持专属 Relay 边界；Worker 自身显示材料仅进入其专属只读 tmpfs，进程环境/argv/Home 不含秘密。真实正确/错误 Basic Auth、五类启动拒绝、控制器/Worker 恢复及清理通过；实际协作房间未测 |
| S03/S04 | Session 缺库/密钥/权限/材料异常与入口禁用/注销按上述测试拒绝。上游 Secret Store 授权、轮换、紧急撤销和阻断仍引用 [R5B](secret-store-acceptance-2026-09-14.md) 的版本/范围 |
| S05 | 37 项真实 age 控制测试覆盖 Session 密钥/密文配对、加密归档和当前账号表启用；真实运行证明密封 Session 重启及材料重建。完整新环境上游凭据恢复引用 R5B；真实 Home 恢复仍归 R2 |
| S06 | 本项扫描 Adapter、控制器/Python、两层 Caddy、Worker nginx/Selkies 日志，入口/API 哨兵响应通过。两层 Caddy 的错误过滤另在 v2.11.4 六条真实 TLS 失败请求中通过，见 `caddy-logs-after-2/`；Relay 的日志/代理认证异常按 R5A/R5B 原版本证据引用，本轮未重跑其协议矩阵 |

日志清洗保留固定事件、级别和允许的审计字段，不渲染原始异常/traceback/请求对象；不能据此宣称保留了完整错误详情。扫描结果只针对测试中已知秘密和列明的文件/运行面，不等于所有输入的形式化证明。

本项 QA 策略没有启用运行时 coherence。私有能力头仍执行 `session_gate`，凭据正确但一致性证据缺失会拒绝的控制测试通过；R5C3 的真实策略矩阵仍按其 [独立报告](runtime-coherence-acceptance-2026-09-14.md) 引用，不能宣称已在 r7 上重跑全矩阵。

## 静态与文档收尾

`final-static-1/result.json` 检查 351 个公开文件、106 份 Markdown 的 1,333 个本地链接/锚点、21 份 JSON 和 14 个入口相关 Python 文件语法，全部通过；对公开文件及 r7 产物核对 21 个已知秘密变体和私钥块，无命中。两层 Caddy 的日志过滤块与 `caddy-logs-after-2/` 实测版本一致，路由改动没有扩大该旧证据的测试范围。

普通工作区和暂存区 diff、展开后的上游源码 `diff --check` 均通过。完整工作区 `git diff --check` 返回 2 的 65 条记录全部是版本化 patch 中必须保留的单空格空白上下文行，逐行核对见 `final-static-1/nested-patch-review.json`；没有修改 patch 内容或把原始返回码写成 0。源码与 payload 摘要另由 `final-artifacts-1/` 核对。收尾状态更新后的复核见 `final-static-2/`。主仓库 index 保持，既有 pycache 和其他改动保留。

## 偏差与失败保留

[DEV-030](../../docs/deviations/DEV-2026-09-14-030-untrusted-error-logging.md) 至 [DEV-036](../../docs/deviations/DEV-2026-09-15-036-client-host-network-change.md) 分别记录不受信任日志、明文 Session 状态、URL/Origin、Docker 显示秘密、私有证书 SAN、交接能力泄漏及 QA 网络变化。处理均为修复实现或 QA，保留原要求与失败范围。

候选 1/2、`client-qa-1/` 至 `client-qa-12/`、修复前 Python 哨兵及 Caddy 首轮读取错误保留。`worker-auth-negative-1/` 因未提供有效产物而未到显示验证器，不能算材料拒绝通过；`runtime-security-1/` 未覆盖 UID 33，不能算完整扫描。`runtime-security-2/` 为 resume 前 406 面，最终采用第三轮。race 首轮缺 cgo、第二轮临时目录 noexec 的失败保留，最终第三轮通过。包装首轮 skip 也保留，补验没有修改其原结果。

## 清理、发布与剩余条件

`cleanup-1/result.json` 为 PASS：两个 Profile 经原生命周期 stop；6 个 generation 容器、其全部网络、3 个 fixture、基础 QA 网络、4 个精确匿名卷已移除；Adapter/前置 Caddy/scoped Docker proxy 停止，私有 socket 和显示 tmpfs 移除，loopback 28110/28443/29110/29443 关闭。私有磁盘证据和 QA Home 有意保留，不是仍运行的部署。

生产 `sealskin`、`profile-relay-personal`、`blissful_tesla`、`elastic_nightingale` 的 ID/image/StartedAt/PID 与五份配置/绑定摘要保持，前后证据为 `production-before.json`、`cleanup-1/production-after.json`。系统 Caddyfile SHA-256 为 `1903c54062da238b16491e6960d6edb7e53acf2398e239295aa79018211db6b7`。基础 QA 权威 `r5c2-public-dns-authority` 的 ID/StartedAt 保持。本项没有操作远端测试服务器。

发布材料为 `release-review-2/`：两个域名的授权/维护路由、Adapter 配置、私有 TLS、Compose overlay、tmpfiles/启动顺序与输入摘要已准备并通过静态配置验证；没有创建生产账号或加载生产配置。它仍引用准备时的生产 Profile/App/策略，须结合 R4B 的 r7 迁移材料。维护与匹配回退见 [操作说明](entry-auth/README.md#发布候选与维护顺序)。

尚未验证：目标 Mac/Trilium、真实 Note/Home、实际协作房间、生产发布/整机重启、Debian 13、跨浏览器版本回退和生产账号配置。R2、R4B 及整体发布门槛保留；本次候选通过不代表 S 组或项目全部完成。
