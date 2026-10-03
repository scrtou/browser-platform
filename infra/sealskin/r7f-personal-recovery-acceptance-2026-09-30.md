# R7F · Personal 代理恢复与停止时点备份 — 2026-09-30

[验收索引](../../docs/acceptance/README.md) · [R7F 工作项](../../docs/work-items/R7F-2026-09-23-production-release.md)

## 结论与范围

Personal 原绑定 `personal-tw-socks` revision 1 的当前控制器探针仍为 `PROXY_PROBE_TIMEOUT`。已有 `tw` revision 1 明确授权 Personal，使用其精确 Profile/Home/Application grant 和已有 Secret Store 引用，14:50 UTC 实际 SOCKS5 认证、CONNECT、TLS 与 HTTPS 200 通过，返回 `PROXY_PROBE_OK`。没有提取凭据、新建 Secret Store 版本或修改目录探针历史。

新停止时点备份完成后，经现有管理页执行的绑定已于 14:55 UTC 只读核对通过：**Personal revision 10、`proxy_required`、`tw` revision 1、独立 policy `personal-tw-r1`**。完整 resolved App 仅改变 policy ID/SHA，原应用、镜像和 Home 保留，操作标识与准备记录一致。此时仍 stopped/0 resources，新代次运行健康及浏览器数据验收待打开后完成。

用户随后确认已绑定并打开。14:58 UTC 复核时 **Personal revision 12、enabled/running、overall=healthy**，新鲜 `PROXY_OK`、浏览器和显示通过；Worker 经当前 Relay 的域名/TLS/HTTPS 成功，四类原始绕过被明确拒绝。此结果补齐旧目录兼容绑定所缺的新代次健康，DEV-071 已解决；浏览器 GUI 与原有登录/数据读取仍单独待确认。

用户进一步明确使用 **Mac 浏览器**，Personal 和 Work 的 `https://example.com/` 均访问正常；原有书签/已登录网站等确认项答复为 **不适用**。本次 Personal 代理恢复的停止/备份/绑定/新代次健康/实际入口条件已满足，DEV-069 已按本次恢复范围解决；不把“不适用”写成旧登录恢复通过，不覆盖 Trilium、完整管理页矩阵或 Work 停止重建/三类存储。

本轮没有部署二进制、控制器、Relay 或 R7G。Work 和“测试”在探针及备份前后的容器身份保持；本轮不停止它们。

## 验证结果

| 项目 | 结果与证据范围 |
| --- | --- |
| 初始绑定与资源 | Personal revision 9、旧策略与完整应用一致、stopped；record/Worker/orphan/resource/Relay/Guard/network 均为 0 |
| 旧绑定当前探针 | 控制器请求成功但实际代理连接超时；未把三天前的 accepted/PROXY_PROBE_OK 当作当前健康 |
| 现有 `tw` 候选 | accepted、授权含 Personal；精确 grant 下 `PROXY_PROBE_OK`，HTTPS 200，约 1.1 秒 |
| 观察过程保持 | 配置、Profile 目录和代理目录摘要不变；三个 Profile 的容器身份不变。控制器进程内有界探针不创建容器或新代次 |
| 新加密备份 | 1,204 条目，age create、verify、独立 restore 均通过；归档 SHA 与恢复回执一致 |
| 恢复副本边界 | `ready_to_activate=false`、`access_review_required=true`；未激活副本，解密临时目录已清理 |
| 原 Home 文件 | 在 Personal 前后均 stopped/0 resources 时，恢复副本的 1,035 个 Home 文件逐一比对全部一致；不代表浏览器读取或旧网站登录成功 |
| 当前管理员恢复材料 | 副本 0600、内容与指定恢复源一致；恢复私钥对应当前注册公钥，恢复公钥与当前公钥一致；以恢复身份执行加密只读管理 API 成功。未输出密钥或其摘要 |
| 实际管理页绑定 | revision 10、`tw` r1、独立 policy、原 Home/应用及完整 App 仅改 policy 的六项检查通过；绑定后仍 stopped/0 resources |
| 用户打开后的运行 | revision 12，1 record / 1 Worker / 0 orphan / 5 resources / 1 Relay / 1 Guard / 2 networks；精确原镜像与 Personal Guard 归属通过 |
| 14:58:21 UTC 健康 | `overall=healthy`、`stale=false`；入口、控制面、Session、Worker、浏览器、显示、`PROXY_OK`、`REPORT_FRESH` 通过 |
| Worker 受管公网路径 | SOCKS5 域名 CONNECT，经当前 Relay/外部代理验证 TLS，`https://example.com/` 返回 200 与预期页面内容 |
| 四类绕过 | 原始公网 TCP、公网 DNS、metadata 在 connect 阶段 `ENETUNREACH`；完整有效 Docker DNS 查询在 send 阶段 `EPERM`。超时不会被判为通过 |
| 最终保持核对 | 14:59 UTC Personal/Work/“测试”均新鲜 healthy；Work/“测试”Session 与容器身份不变，配置和代理目录不变；只新增精确 Personal policy，所有旧策略内容不变 |
| Mac 真实客户端 | 用户确认 Personal/Work 内公网页面正常，原有书签/登录为不适用；浏览器版本、视区和 Trilium 未提供或未测 |

## 继续步骤与限制

Personal 固定入口打开后的服务器检查与 Mac 浏览器公网页面确认已通过。Trilium、完整管理页面、r10 桌面及正常重建/三类存储仍按各自范围待验收。`tw` 为域名上游，当前成功不保证未来地址不漂移；R7G 动态热切换仍未部署。

旧管理员身份的特定拒绝证据仍缺，本次新恢复身份成功不能代替它，DEV-070 保持打开。Work 正常重建/三类存储/实际回退、目标客户端完整矩阵及 r10 桌面确认仍按 R7F 原完成条件保留；本次两浏览器的原有书签/登录确认项为用户明确不适用。

私有证据在忽略目录 `infra/sealskin/runtime/r7f-personal-20260930/`：前后快照、两个当前上游探针、完整原应用、绑定准备与实际绑定结果、新加密归档/未激活恢复副本、Home 文件比对、恢复身份结果及只读后续探针。旧失败和历史备份保留；不恢复旧 journal、账号表或 Session 状态覆盖后续操作。

本轮收尾核对：16 份受影响文档的 641 个相对链接/锚点及 `git diff --check` 通过，4 个私有检查脚本语法通过；实际备份/恢复、身份保持、绑定与运行网络结果已逐项核对。解密临时目录已清理，未创建临时容器；加密归档、未激活恢复副本与证据按恢复用途保留。R7F 仍按上述剩余条件进行中。
