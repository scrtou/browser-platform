# R7G · 真实控制器中断与恢复验收

日期：2026-09-30。结论：四组独立 Docker QA 通过，DEV-083 已修复；未部署生产。延续[前轮集成](r7g-controller-integration-acceptance-2026-09-30.md)，只补充真实 pending 恢复范围，不替代公网供应方、客户端或整机灾备验收。

## 固定版本

| 材料 | 身份 |
| --- | --- |
| 控制器 release | `0.3.2-entry-auth-v1-7757290001e94bdc` |
| 控制器镜像 | `sha256:37345e2fa5d92379719ffb8398795fb12d115d76e0f583df361e35db8793130a` |
| 动态补丁 | `bde06133d136c15258545cc9578aae14d84f8bb1e2840cda6fde0940cd6df2c4` |
| Relay | `sha256:9d3928f045dd95a0eb41d3a280f388b8b11dca82c4619fad6eb56fc36f27db4f` |
| Worker | `sha256:895907b7cecf793db5b5b108e9a9ac371d0d381833e729d0b5cc16f8eee8e356` |

实际安装的 35 个控制器文件逐一匹配固定 payload manifest，补丁摘要匹配；展开源码经同一准备器构建。Relay/Worker 沿用前轮精确镜像。

## 实测结果

正常监视器读取批准 DNS、创建 pending、写入 lease 并调用实际 nft。QA 通道只在已证明归属的 Relay、指定规则地址与调用阶段暂停请求，最长 30 秒；解除后旧请求返回失败，不能迟到写入。未伪造 pending 或手写 lease。中断前直接读取已核对路径的持久日志，避免等待持有 Home 锁的监视器。

| 中断点 / 恢复场景 | 实际状态及结果 |
| --- | --- |
| pending 已落盘、过渡规则尚未应用；重启控制器 | lease A、内核 A；恢复旧 revision、规则 A，删除 pending 并重新接入 |
| lease 已改 B、最终规则尚未应用；更换控制器 | lease B、内核 A+B；恢复原 lease/revision、规则 A并重接新控制器 |
| 最终规则已应用、回执尚未返回；重启控制器 | lease B、内核 B；恢复旧 lease/revision、规则 A，无晚到规则覆盖 |
| 首次启动恢复的规则操作失败，随后修复并更换控制器重试 | 首次只停止所属 Relay，保留 pending/错误，另一个 Home 正常；明确启动该 QA Relay 后重试，成功清除当前错误并重新接入 |

前三组均核对两个 Home 的 Session 记录、Worker/Relay/Guard ID、镜像、PID、StartedAt 和网络模式不变；既有 HTTPS 长连接及新连接正常。第四组仅被明确修复的 Relay 重新启动，其他进程和 Session 身份保持。各组都核对实际 nft 和 Worker 四类绕过明确拒绝；不是只检查容器 running 或 HTTP 状态。

[DEV-083](../../docs/deviations/DEV-2026-09-30-083-dynamic-recovery-stale-error.md) 的旧候选回归失败：成功重试后仍残留 `NETWORK_DYNAMIC_ENDPOINT_ROLLBACK_FAILED`，导致接入被拒绝。修复只在旧 lease/规则成功恢复后清除当前 `last_error`；失败继续保留 pending。修复后网络/DNS **140 passed**、QA 工具 **107 passed**、完整控制器 **557 passed**（两条依赖弃用 warning）。四组实机检查全部 PASS。

## 重现、清理和范围

先按[生命周期说明](lifecycle/README.md#r7g-动态上游隔离集成)准备全新 QA 和独立显示 tmpfs，执行 `check-dynamic-upstream.py prepare`；再执行 `check-dynamic-recovery.py --root <private-run>/qa`。运行器中断的控制器必须同时匹配 QA 名称、标签和配置/存储挂载。失败材料保留；正常完成先通过生命周期停止代次和夹具，再将真实 `recovery/summary.json` 交给 `cleanup-network-qa.py --completed-evidence`。

本轮 QA 代次资源、容器和网络均清零，控制器/代理停止，基础 QA 临时凭据清理；动态夹具私钥/凭据副本仍保存在私有运行证据目录；独立显示目录确认空后移除。生产 Profile/容器身份及关键文件摘要与开始前完全一致，Adapter 二进制仍为 `7f4e2a1a…`。没有停止生产浏览器、操作真实 Home 或替换生产控制器。

详细证据在忽略目录 `runtime/r7g-recovery-20260930/`：四组 `recovery/`、红/绿回归日志、安装 manifest、清理与生产前后快照。首次 QA 在持锁点错误使用普通 GET 导致超时的材料保留于 `recovery-attempt1/`；修正观测方式后的前三组原版本结果保留于 `recovery-pre-fix-pass/`。这些失败没有改写为通过。

本报告不包括商业供应方自然漂移认证、公网递归缓存、浏览器页面/Mac/Trilium观察、大规模压力或生产发布。客户端按用户要求暂缓；R7G 继续公网认证路径、并发边界与发布材料准备，整体保持进行中。
