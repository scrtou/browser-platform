# R7G · 存量静态代次升级与受控回退

日期：2026-09-30。结论：四组真实 QA 检查通过。使用当前生产镜像字节和全新 QA 配置/数据，没有挂载或操作生产 Home、凭据或 Session。

| 版本 | 精确镜像 |
| --- | --- |
| 现行控制器基线 | `sha256:bfcd878f693578b65d2911015aedd3a6a79cc25f20619c0c36525f8e19dd90e3` |
| 现行静态 Relay 基线 | `sha256:a785d443bf7ede16e0f4728bbcc552a17f6340e6a3fea2d01bd839776716888a` |
| R7G 控制器 | `sha256:37345e2fa5d92379719ffb8398795fb12d115d76e0f583df361e35db8793130a` |
| R7G 动态 Relay | `sha256:9d3928f045dd95a0eb41d3a280f388b8b11dca82c4619fad6eb56fc36f27db4f` |
| QA Worker | `sha256:895907b7cecf793db5b5b108e9a9ac371d0d381833e729d0b5cc16f8eee8e356` |

## 结果

| 场景 | 实测 |
| --- | --- |
| 基线创建两个静态代次 | 基线控制器/Relay、两个独立命名 Home、数值上游及独立 QA 文件凭据创建正常 Session/Worker；均无 endpoint lease |
| 候选控制器接入存量代次 | 只替换已核对名称、标签和挂载的 QA 控制器；两个 Home 的 Session、Worker/Guard/Relay ID、PID、StartedAt、镜像及网络模式不变，原 HTTPS 连接保持，新连接正常，四类 Worker 绕过明确拒绝；未凭空生成动态 lease |
| 静态与动态并存 | 保留 Home A；Home B 正常停止清理后使用新不可变策略、动态 Relay 和新 operation 启动。真实 monitor 驱动 B 从地址 A/revision 1 切到 B/revision 2；Home A 继续使用原数值上游，无 lease，进程/Session 身份保持且新旧连接正常 |
| 动态清理后的旧控制器回退 | 先经生命周期清理 Home B，确认没有动态 reservation，再替换回基线控制器；Home A 重新接入而不重启 Worker/Guard/Relay，原长连接与新连接正常，绕过仍拒绝。随后正常清理 A，恢复空 QA 的候选控制器 |

源码兼容额外核对：生产运行容器的完整 96 个应用文件与候选的 97 个文件比较，只改变 `api.py`、`network_dns.py`、`network_runtime.py`，新增 `dynamic_upstream.py`；没有删除文件，其他应用/静态资源完全一致。因此当前四文件 overlay 没有因候选构建丢失。该文件核对不单独证明运行兼容，运行结论来自上表。

## 重现和证据

[check-dynamic-compatibility.py](checks/check-dynamic-compatibility.py) 在私有动态夹具准备后运行，传入明确的 `--baseline-controller` 和 `--baseline-relay`。候选镜像取自准备记录，不能因为重试时当前控制器已回到基线而误认候选。旧控制器切换前要求所有 reservation 都没有动态 endpoint，防止把包含 pending/lease 的状态交给不理解它的代码。

首次准备把空 bootstrap 字段写进原始策略摘要，而现有兼容序列化会省略这些字段，因此原校验正确拒绝 422 `NETWORK_POLICY_REFERENCE_MISMATCH`，尚未创建代次。运行器改为使用符合既有规范的旧格式策略；原失败材料保留，没有放宽产品校验或修改控制器。最终四组全部通过。

详细材料位于忽略目录 `runtime/r7g-public-20260930/compatibility/`、`private-compatibility-dynamic/`、`compatibility-run.log`；失败记录在 `compatibility-attempt1/` 和对应日志。完整应用摘要比较另存 `runtime/r7g-release-review-20260930/installed-overlay-compatibility.json`。

私有代次和三个私有夹具已清理；公网准备的策略、凭据、allow 和应用定义在零资源状态下准确恢复。基础 QA 控制器/公网权威/受限端点继续等待 DEV-084 范围答复，不能记为公网已清理。产品源码保持[557 项控制器回归候选](r7g-controller-recovery-acceptance-2026-09-30.md)，本轮没有重复运行全量测试。

范围限制：证明独立 QA 的数值静态代次与动态域名代次兼容及注明顺序的回退，不代表真实生产 Home/Secret Store 迁移、活跃动态状态直接降级、浏览器页面/Mac/Trilium或公网供应方自然漂移通过。生产发布仍未授权、未执行；公网认证与最终组合材料仍由 R7G 承接，客户端暂缓。

本轮最终清理：公网 DNS UDP/TCP 外部复查仍超时，未应用主机规则。随后删除本轮 QA 名称并递增 serial、恢复权威原停止状态；两个公网进程正常停止并精确 purge，基础 QA 容器/网络/代次均清零，显示 tmpfs 移除。本地公网 bundle 的凭据/私钥/归档删除，私有测试证据及退役 Store 密钥保留。IPv4 入站规则与生产快照均保持，见私有 `final-status.json`；公网验收仍为 NOT_RUN。
