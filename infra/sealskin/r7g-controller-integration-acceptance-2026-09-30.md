# R7G 控制器动态上游集成验收（2026-09-30）

状态：本轮隔离开发与验证通过，QA 已清理；R7G 整体待验证，未部署生产。用户明确选择选项 1，允许先推进本项，R7F 原客户端未测/数据不适用条件保持。

## 实现与版本

本轮把真实控制器监视器、批准 DNS、认证 SOCKS5、Relay、nft 和两个 API 创建的浏览器 Worker 连通。HTTPS 请求由 Worker 内独立 Python 客户端发出；没有把它记作 Firefox 页面、Mac 或 Trilium 视觉验收。

- 控制器基于固定上游 `2b13a42483c1dc7d367d5c340437bdc8ecd84bb4`，依次应用三个版本化补丁；修复后候选为 `sha256:43d517cabf37b7f914495409d7ba39998ed38fdb797a15f408c2fbe926f7fc36`，35 个实际安装文件与新 manifest 一致。
- 动态 Relay 为 `sha256:9d3928f045dd95a0eb41d3a280f388b8b11dca82c4619fad6eb56fc36f27db4f`；浏览器 Worker 使用现有受管理 Work 镜像 `sha256:895907b7cecf793db5b5b108e9a9ac371d0d381833e729d0b5cc16f8eee8e356`，独立 Home、Session 和显示材料。
- [DEV-081](../../docs/deviations/DEV-2026-09-30-081-dynamic-qa-exec.md)：QA Docker 代理只允许已批准镜像、所属代次 Relay 的固定 root 规则命令，重新校验 exec 归属并有界转发 Docker upgrade 输出，不开放 stdin 或任意 shell。夹具使用独立随机凭据、TLS CA 和两个测试地址；完整 PUT 去掉旧夹具启动覆盖，保留 Session 认证门槛。
- [DEV-082](../../docs/deviations/DEV-2026-09-30-082-dynamic-fail-closed-stop.md)：修复真实 Docker SDK 的关键字 `timeout=10` 调用；pending 恢复只能停止已证明归属的 Relay，恢复失败保留 pending。未修改生产控制器或 Relay。

## 结果

| 验证 | 证据与结论 |
| --- | --- |
| QA 命令边界 | 101 项测试通过；真实 socket 拒绝 Worker 目标、错误用户及任意 shell 命令 |
| 批准 DNS 与真实切换 | 私有 UDP DNS 夹具 TTL=2 秒，实际监视器按生产下限 15 秒调度；两个 Home 的 lease 从 A/revision 1 更新为 B/revision 2，未手工修改 lease 或刷新时间 |
| 旧连接与新连接 | 持续 HTTPS 连接仍读到 A，新建连接读到 B；两个 Home 的 Worker 与 Session 代次记录保持，各自 lease ID 不同 |
| Guard 与绕过 | 读取真实 nft JSON 并断言只允许当前端点的新连接；公共 TCP、Docker DNS、公共 DNS、metadata 四条绕过均明确本地拒绝，不以超时算通过 |
| 认证失败 | A 拒绝 SOCKS5 认证，真实 Relay 探测失败；两个 Home 回滚并继续经 B 建连，既有 A 长连接保持 |
| DNS 故障与恢复 | SERVFAIL 保留 B；解除故障后自动回到 A/revision 3 |
| 代次隔离与清理 | 正常停止 Home A，重新启动产生新 operation/Session/Worker 和 revision 1 新 lease；Home B 身份保持可用 |
| 规则更新和回滚双失败 | 仅对新 Home A 的精确 Relay 注入两次规则调用失败；真实 Relay 进入 exited，pending 与错误证据保留，Worker 身份保持且四类绕过拒绝。Home B 正常切换到 B/revision 4，HTTPS 200 |
| 回归 | 网络/DNS 专项 139 passed；完整 `server/tests` 556 passed（2 条依赖弃用 warning）；上述 101 项 QA 工具测试通过 |
| 缺陷复现 | 新增的 5 项回归对旧候选为 4 failed / 1 passed，修复后全部通过，覆盖 SDK 签名、停止失败保留意图和未证实归属资源保护 |
| 生产保持 | QA 清理后，生产 Profile/容器身份与关键配置摘要和本轮开始快照完全一致；没有生产部署、停止或 Home 操作 |

最终运行器输出 8 组集成 PASS；夹具准备另有独立 PASS。原候选的分离测试结果仍按 [9 月 27 日报告](r7g-dynamic-upstream-acceptance-2026-09-27.md) 的范围引用，不能覆盖 DEV-082 的真实停止缺陷。

## 重现与清理

入口为 [check-dynamic-upstream.py](checks/check-dynamic-upstream.py)。先用当前 `prepare.py` 准备固定候选，并用 `prepare-network-qa.py` 建立全新 QA，必须传入独立 `--display-runtime-root`；三个辅助二进制按既有网络 QA 流程准备。随后传 `--root`、精确 `--worker-image` 执行 `prepare`，再执行 `run`。运行器仅使用 `network-qa` 的两个 Home 和固定 QA 服务名；先确认这些专用名称没有被其他任务占用。

失败时执行运行器 `stop` 释放记录中的 QA 代次和夹具，保留失败证据；只有实际 PASS 后才可执行 `cleanup-network-qa.py --completed-evidence <dynamic/summary.json>`。本轮正常清理后代次资源、QA 容器/网络均为 0，QA 控制器/代理已停止，显示 tmpfs 已空并移除。候选镜像和私有证据保留用于审阅；独立测试端点目录中的测试凭据按私有运行材料保存。

详细证据：忽略目录 `runtime/r7g-integration-20260930/`，包括各失败尝试、`dynamic/` 最终结果、固定构建/安装 manifest、回归日志、清理回执及生产前后快照。夹具修正和失败历史均保留；没有降低原断言来获得 PASS。

## 未测范围与后续

本轮没有真实公网供应方自然 A 漂移的认证流量，也没有 Firefox 页面或目标 Mac/Trilium 的热切换观察；私有权威夹具不代表公网委派或递归缓存。未实施生产发布、控制器重启实机 pending 故障恢复或大规模并发压力测试；pending 恢复本轮为模型回归，两个真实 Home 为并存隔离证据。上述后续由 R7G 继续承接，R7F 原验收条件保持待验证。


文档收尾：18 份更新文档的 795 个相对链接/锚点、5 个 QA Python 文件语法与 `git diff --check` 通过；最终动态补丁摘要与已验证安装 manifest 一致。QA 容器/网络按专用标签再次确认均为空。

后续补充：同日[真实控制器恢复验收](r7g-controller-recovery-acceptance-2026-09-30.md)已补齐三个 pending 中断点及首次恢复失败后的重试；原报告的公网、客户端和压力范围不变。
