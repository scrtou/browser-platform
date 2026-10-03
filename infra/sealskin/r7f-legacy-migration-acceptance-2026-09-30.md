# R7F · 旧 Work 网络迁移/回退路径与限定发布 — 2026-09-30

[验收索引](../../docs/acceptance/README.md) · [R7F 工作项](../../docs/work-items/R7F-2026-09-23-production-release.md)

## 结论与生效范围

受控 legacy → managed DIRECT 迁移、显式回退和启动锁修复已完成实现与隔离验收。Adapter **`7f4e2a1aee6c79de904e19b2e40c2c69c6ec39152fbc0ff13798db6ef1c49635`** 与服务端批准目录已限定发布。实际进程摘要、就绪入口、目录/账号/应用/策略文件及 Profile/Session/Worker/网络身份核对通过；只改变 Adapter 和新增迁移目录配置。

12:30 UTC 发布时点强制探测：“测试”仍为新鲜 `healthy`；Personal/Work 均 stopped/0 resources，Work 仍 disabled、原 Firefox/Wayland/Home 和无 policy 状态保留。当时尚未执行 Work 迁移、回退和公网生产动作；该发布结果不等于 Work 公网恢复。

## 用户操作后的实际迁移复核

用户确认完成管理页操作后，只读核对 10 项通过：Work **revision 7、ready、无 pending、managed DIRECT、仍 disabled/stopped/0 resources**；原 Home/Application 保留，完整 resolved App 等于批准的原应用仅更换目标镜像及 policy；迁移回执、目录 policy ID/SHA 一致。生产实际迁移已完成。

在前后均确认停止且资源为零的条件下，原 Home 的 **31 个 SQLite 数据库**与本次加密恢复副本逐一 SHA-256 比对，全部一致。这证明此次配置迁移保留这些文件，不代表已从浏览器读取 Cookie/localStorage/IndexedDB 或已登录第三方网站。用户随后确认已启用并打开 Work，运行结果见下一节。

私有结果为 `actual-migration-verification.json`、`work-home-after-migration.json`；运行探针限定精确镜像/Guard 归属、经 Relay 的域名/TLS/HTTPS 与四类原始绕过拒绝。探针不启动、停止或修改浏览器。

## 启用后的生产运行核对

用户确认启用并从固定入口打开后，Work 为 **revision 8、enabled、ready、running**；1 record / 1 Worker / 0 orphan / 5 resources / 1 Relay / 1 Guard / 2 networks。实际 Worker 使用批准的 `sha256:895907b7cecf793db5b5b108e9a9ac371d0d381833e729d0b5cc16f8eee8e356`，共享归属 Work 的 Guard 网络命名空间，Home 与应用身份保留。

| 生产检查 | 结果与范围 |
| --- | --- |
| 12:47:02 UTC 新鲜健康 | `overall=healthy`、`stale=false`；入口、控制面、Session、Worker、浏览器进程、显示、`DIRECT_OK` 和 `REPORT_FRESH` 均通过；`DIRECT_NO_UPSTREAM` 为预期不适用 |
| 经受管 Relay 的公网路径 | 在实际 Worker 内向 `profile-relay:1080` 发起 SOCKS5 域名 CONNECT，TLS 证书校验成功，`https://example.com/` 返回 200 与预期 Example Domain 内容 |
| 原始公网 TCP / metadata | Worker 内的有界直连尝试失败；没有增加公网网卡或路由 |
| 有效 Docker DNS 查询 | 12:51:49 UTC 补测完整 29 字节 `example.com A` 请求，send 阶段明确 `EPERM`；Guard output drop 计数增加 1、规则摘要不变 |
| 有效公网 DNS 查询 | 同轮完整查询在 connect 阶段明确 `ENETUNREACH`；无直连路由，Guard 规则摘要不变；未把计数未增加写成规则命中 |

初版探针对 UDP DNS 发送无效报文，并把超时也计为 blocked，已登记并修正 [DEV-078](../../docs/deviations/DEV-2026-09-30-078-work-dns-probe-evidence.md)。原始 `work-live-result.json` 保留，两个 DNS 布尔值由 `work-dns-verified-final-result.json` 的有效请求和明确本地拒绝证据补齐；超时本身不算通过。只读观察命令的失败及首轮过严分类结果也保留，最终使用现有 Guard 的 nft 只读查询，未部署新 Guard 或修改防火墙。

上述域名/HTTPS 是 **Worker 经当前 Relay 的网络路径**验收，不等于 Firefox GUI 页面、旧站点登录或浏览器读取存储通过。用户目前只确认启用和打开；已一次性请求页面、原有数据及客户端类别反馈。生产没有执行网关故障注入、正常停止重建或实际回退；独立 R7B 的故障关闭/换代/三类存储证据仍保留原范围。

后续客户端反馈：用户在 Mac 浏览器中确认 Work 和 Personal 的 `https://example.com/` 页面均正常，补齐本次真实浏览器公网页面证据；原有书签/登录确认项为“不适用”。这不覆盖 Trilium、正常停止重建/三类存储或实际回退，详见 [客户端矩阵](../../docs/client-matrix.md#r7f-本次客户端确认--2026-09-30)。

## 实现与验证

| 验证范围 | 结果 |
| --- | --- |
| 批准目录与精确身份 | 私有普通文件、严格 JSON、accepted 状态、原 revision/Definition/完整 App、精确目标镜像与验收/备份/恢复摘要；无批准、漂移、错误镜像、公开权限或链接拒绝 |
| 停止与生命周期边界 | running、残留启动资源、unknown、DIRECT 能力缺失拒绝，零 Stop/Launch/Home 创建或归档副作用 |
| 持久迁移与回退 | 先持久 migrating 再追加 policy/PUT/读回/提交；append/PUT 失败与成功后响应丢失，经目录重新加载可同请求继续；actor/key/计划漂移拒绝；回退恢复原 App/Definition，保留 Home/journal/账号及策略历史 |
| pending 门禁 | 启动、删除及普通状态更新不能清除迁移状态；应用读回不一致不提交，未知 App 不被重试覆盖 |
| [DEV-077](../../docs/deviations/DEV-2026-09-30-077-launch-definition-lock.md) | 确定性等待锁场景覆盖停用、pending 与新应用定义；Ensure 取锁后读取目录，副作用使用当前定义 |
| 加密管理协议 | 完整 resolved App 字段保留，仅删除三个易变观测字段；不存在/重复 ID 拒绝 |
| 真实管理网关夹具 | 未登录、非管理员、错误 CSRF、跨 Origin、缺近期认证均零迁移调用；近期认证后仅传高层 ID/revision/key，客户端镜像字段不进入迁移参数 |
| 固定 Go 1.27 | 全量 test/vet/gofmt 通过；profile/sealskin/httpapi/access/control 五包 race 通过，最终回退补充后全量 test/vet 与受影响 profile/httpapi race 再通过 |
| 实际 Work 输入的隔离验证 | 真实批准目录与原 Definition/完整 App 在独立目录、fake lifecycle/admin 中迁移成功；生产没有被该检查修改 |
| 固定控制器模型 | 精确 checks 镜像的 InstalledApp 规范化前后完整目标应用一致；不是实际生产 PUT/浏览器验收 |

首轮读回漂移测试暴露共享对象可改变预期值，改为外部调用前固定目标摘要后通过，原拒绝断言未降低。首轮输入准备早于 restore 回执完成而安全拒绝，完成备份后再准备成功；没有提交不完整目录。

## 备份、批准清单与回退

- Work 本次停止时点 age 归档、verify、独立 restore 均通过，**5,195 条目**；副本 ready_to_activate=false、access_review_required=true，未激活。
- 批准清单绑定 Work revision 4、原完整应用、原镜像 ec848635… 与目标 895907b7…；精确父层、退出/显示认证/受管网络标签、R7B 四组 PASS 及匹配备份摘要通过复核。
- 迁移成功后仍 disabled；显式回退只在停止且零资源时恢复批准的原应用与 Definition，不回放旧 journal、不改 Home、不删除不可变策略。回退后的再次迁移需要以新 revision 重新准备批准条目。
- 发布时尚未迁移，可回退 Adapter 与配置；当前已完成迁移，旧 Adapter 不兼容新目录字段，须继续使用新实现的迁移/回退路径，不能用旧目录快照覆盖后续操作。
- 私有材料在被忽略的 `infra/sealskin/runtime/r7f-migration-20260930/`：固定源码快照/76 文件摘要、测试日志、批准目录、完整 App、密文/未激活恢复副本、精确旧/新二进制与配置、限定发布计划及结果。公开记录不包含私钥、凭据或 Session URL。

## 尚未完成

文档与资源收尾：发布阶段 13 份文档的 668 个相对链接/锚点、76 个源码文件与最终验证快照摘要均通过；Go/checks 临时容器已退出，解密 tmpfs 已清理。启用后更新的 12 份文档、599 个相对链接/锚点及 `git diff --check` 再通过，结果为私有 `documentation-running-check.json`；补测没有创建临时容器或改变生产生命周期。加密归档、未激活恢复副本、批准清单及回退材料保留在忽略目录。

Work 的实际回退、正常停止重建及三类存储恢复；旧管理员恢复身份拒绝证据；目标客户端完整矩阵及 r10 桌面直接用户确认。Personal 当前上游与新代次健康已由[同日后续验收](r7f-personal-recovery-acceptance-2026-09-30.md)补齐，两浏览器的 Mac 真实公网页面已确认，原有书签/登录明确不适用。Worker 网络路径与有效 DNS 拒绝已由本轮补齐；未用生产故障注入替代隔离验收。R7F 保持进行中，R7G 未部署。

同日后续：当前发布组合的独立 QA 已补齐正常重建后三类存储、网关故障关闭、实际回退和再迁移读回，完整干净复跑及清理通过，见 [恢复与回退验收](r7f-work-recovery-acceptance-2026-09-30.md)。此结果不覆盖生产 Work 真实 Home 的停止重建或目标客户端矩阵。
