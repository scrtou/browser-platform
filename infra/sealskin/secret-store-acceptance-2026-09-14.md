# R5B · Secret Store、撤销与加密恢复验收

日期：2026-09-14 UTC。工作项：[R5B](../../docs/work-items/R5B-2026-09-14-secret-store.md)。结论：**候选代码与独立 QA 通过，QA 已清理，未部署生产。** 生产仍使用 lifecycle-v2 和原浏览器绑定。

后续：R5C1 的 DIRECT、初始页分离与新的候选摘要见 [DIRECT 验收](direct-network-acceptance-2026-09-14.md)。本报告保留 R5B 当时的版本、测试和范围，不以后续 patch 覆盖历史结论。

## 版本与环境

| 对象 | 固定身份 |
| --- | --- |
| 控制 payload | `0.3.2-secrets-v1-aab221c3c29cb302`；18 个 payload 文件 |
| 控制镜像 | `sha256:9173ea5a738504e80b2d81aeb8c16c6fb89b4a29ec490c7bd560d107c23a0ad6` |
| checks 镜像 | `sha256:da38709da67c23ef744bf64149decd678d6c0216f490ecfac71f5f3c7bf20fde` |
| Guard/Relay | `guard-v1-75d02119f7c7f317`；`sha256:72a188e2f9cf2af39766dd37e579723963a93348b65f3330fb697888bdd9c305` |
| 浏览器 | 原 R5A r6：`0.5.6-beta.30-r6-c73fa18044baad73`，`sha256:4d70427976d5885ad157de0c57f3350df4756977c450e4df9d671bbe2e8c1b69` |
| 工具 | 控制 Python 3.14；Go 1.27.1；age v1.2.1 |

沿用固定 SealSkin 上游和 r6 完整产物。本项没有修改浏览器镜像，不重复扩大 r6 的既有重放结论。QA 使用独立用户、Home、网络、上游 Observer、密钥和两套控制目录；Docker 网关按精确 scope、镜像、角色、代次和只读挂载校验。没有停止生产浏览器、Docker daemon 或主机。

证据根目录为被忽略的 `infra/sealskin/runtime/r5b-secret-store-2026-09-14/`。汇总 `secret-store-final.json` 的 SHA-256：`079f441c6ca7ef61bf82496eb28f7d3818cfb79bcf5d889b429d2fb1d316a3f9`。最终 patch SHA-256：`e5989471124300c4188cf386b3978f6e60efc9ac2d0ea4baac7f150e9778e92a`。

## 结果与范围

| 要求 | 实际结果 |
| --- | --- |
| S01/S06 新凭据路径 | 普通配置、journal、Home、产物、日志、构建 payload 及候选镜像文件系统共扫描 6,472 个文件；上游凭据、Basic 编码和 Store 主密钥零命中，零不可读文件，阳性对照能命中。Note、最终入口及全层 Session 脱敏仍归 R5D |
| S02 专属注入 | 真实 Relay PID 1 为 UID 1000；主机 tmpfs 代次目录 `0700`，凭据 `0600`，Relay 只读挂整个目录；Worker 不挂载凭据/Store/主密钥，配置和环境无上游凭据。QA 挂载边界另有 11 项测试 |
| 三种认证协议 | Secret Store 下 SOCKS5 用户名/密码、HTTP Basic、HTTPS Basic 全部通过；35 项网络检查及 HTTP/HTTPS/WS/WSS 验证覆盖远端 DNS、Guard、故障阻断和 HTTPS 证书校验 |
| S03 授权拒绝 | owner/Profile/Home/App 四维拒绝均为 403；未知引用、混合版本、路径逃逸、缺失主密钥均明确失败，零新 Worker/网络资源；普通用户撤销为 403。存储篡改、链接/权限、不可变版本、恢复锁等由真实存储单元测试覆盖 |
| P05/S04 轮换 | 创建新版本不改变已有代次及其临时材料；覆盖旧版本被拒绝；正常停止并切换新策略后，新凭据认证成功 |
| S04 活跃撤销 | 从请求到 Relay 退出约 0.789 秒（本次环境观测）；已有 WebSocket 关闭，浏览器请求和直接 TCP 均受阻。关闭对话框使 API 返回 `SECRET_REVOKED_CLEANUP_PENDING`，Worker/Home/占用保留；取消后重试完成清理，已撤销引用为 409 |
| S04 并发与中断 | 在创建中的代次与撤销同时执行，未漏掉 generation，最终资源与材料为空；模拟 tombstone 提交后控制器中断，启动监测阻断原 Relay，API 重试完成清理 |
| 恢复与密钥丢失 | 正常停止 Worker/网络、删除 QA 临时材料并重启控制器；缺失主密钥拒绝 resume；恢复密钥后按原代次重建材料并恢复 Cookie/localStorage/IndexedDB。运行中移走密钥使 Relay 退出，浏览器保留且请求受阻 |
| S05 加密恢复 | 真正通过 Adapter 启动/停止形成 journal；age 归档恢复到新的 QA 控制根和 Home。恢复的服务/Adapter 身份可用，固定产物和验收文件从恢复目录挂载，新 Worker 使用恢复凭据认证，三类浏览器存储一致；错误 identity/损坏归档未创建目标；备份后的新增撤销被合并且仍拒绝解析 |
| 回归 | 最终控制 checks 镜像 226 项通过；加密备份 28 项、QA 挂载 11 项通过；Relay Go test/race/vet 通过，旧字段默认与旧策略 SHA 继续兼容 |

本项的核心运行检查共 18 项，另有加密恢复及扫描。测试步骤与操作契约见 [Secret Store](lifecycle/secret-store.md)。100 ms 是 Relay 的检查间隔，0.789 秒是此次 QA 观测，均不宣称主机故障或 CPU 饥饿下的硬实时上限。

加密归档 SHA-256：`bb162199e5cfc772132242d3dec4d3713d66b1df4c93ce14f980619eede8e550`。验证先在 tmpfs 完成认证和全部成员检查；恢复 Store 保持禁用，直到原/目标均无容器挂载并合并当前撤销。启用记录先持久化，再解除恢复锁；中断重试测试通过。恢复目录不覆盖原控制状态，工具不自动启动 Worker。

## 证据分组与失败历史

- `python-tests-final-v2.log`、`backup-and-mount-tests-v4.log`、`relay-tests.log`、`relay-race-v3.log`、`relay-vet.log`：最终对应代码的回归。
- `live-v2` 的三组协议结果、`live-v3` 的授权结果、`live-v4` 的轮换结果、`live-v5` 的完整撤销/恢复结果、`live-v6` 的并发/中断结果共同组成最终汇总；没有把这些目录内的早期失败整体标为 PASS。
- QA 修正包括：从真实 PID 1 读取 UID；拒绝用残留的无效策略污染后续场景；等待正常启动器完成导航后再操作桌面；将网络超时异常识别为阻断；控制器重启后恢复私有测试主机名映射。失败日志和截图保留，最终场景分别重跑。
- `backup-live-v1` 因测试 Adapter 尚未生成 journal 而拒绝归档；后续通过真实 Adapter 周期形成状态，工具新增明确的缺失错误码，未伪造空 journal。`backup-live-v2` 完成全部加密恢复，`artifact-audit-v1` 完成扫描。
- [DEV-009](../../docs/deviations/DEV-2026-09-14-009-backup-key-paths.md) 修复旧备份错误的 SSL 路径，补齐 Adapter、服务与管理员恢复材料；旧 R2 报告仍保留原范围。

## 收尾与发布边界

07:37 UTC：两套 QA generation/网络均为空；Controller、Adapter、代理网关、Observer、upstream 与四个匿名卷已清理。原/恢复 QA Home、明文恢复包、临时凭据/私钥、tmpfs 目录及 74 个本项 pytest 暂存目录已删除；脱敏报告、私有历史日志和加密 QA 归档保留。旧 R5A 控制/Relay 与 r6 镜像仍可查。

`production-comparison.json` 核对四个生产容器的 ID、image、启动时间和 PID，以及 Adapter 配置、应用配置、策略 registry、journal 四个 SHA，前后全部一致。清理证据为 `qa-cleanup.json`。本项没有生产部署，也没有真实 Home 备份或主机重启验收。

DIRECT、公开 DNS/TTL 和环境/网络一致性归 R5C；最终入口/Session 鉴权和全层脱敏归 R5D；linger、真实 Home/正式重启归 R2；Mac 实机与实际迁移归 R4B。原 v0.1 的 Chromium 和其他发布条件保持未完成。回退需先以新控制器清空引用型 generation，保留最新 journal、加密 Store 和撤销记录，见 [回退说明](lifecycle/secret-store.md#验证与回退)。
