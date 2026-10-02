# R7G · 动态代理端点热切换

**2026-10-02 最新授权：** 用户明确要求无供应方条件下直接部署；[R7G1](R7G1-2026-10-02-dynamic-deployment.md)已完成整合、22 组实机验证、生产发布及收尾。供应方自然漂移仍未测。下文禁止部署与等待授权均为历史时点。


**恢复执行：** 用户已明确允许仅限 eth0 → 23.19.231.152 UDP/TCP 53 的两条临时 QA 入站规则；本项恢复进行中。执行后按唯一注释核对并删除精确 handle，不持久化、不部署生产。以下等待确认记录保留为历史。

状态：进行中（临时公网 QA 入站已授权；已完成隔离增量保留）。开始日期：2026-09-27。结束日期：未结束。

## 2026-09-30：继续完成非客户端计划

用户要求暂不考虑客户端验证，先完成所有计划。本项当前补齐真实控制器重启的 pending 恢复、恢复故障/归属边界、同时存在的 Home 与生命周期并发，以及公网认证路径与发布材料；生产仍按既有范围保留，目标客户端验证单列暂缓。

- 代码地图：`api.py:lifespan` → `network_runtime.restore_controller_networks/restore_controller_attachment` → `dynamic_upstream._recover_pending/refresh`；实际副作用为原子 lease/规则更新、所属 Relay 停止、控制器重接；QA 代理/真实运行器记录中断点与 Docker 行为。
- 验证方法：独立 QA 真实 monitor 写入 pending 后，分别在过渡规则/新 lease/提交前中断 QA 控制器；重启/更换 QA 控制器，核对旧 lease/规则恢复、无错误跨代次操作、Worker/Session/容器启动身份不变和无绕过。失败记录保留，清理只针对精确 QA 资源。
- 文档清单：本项、相关偏差、组件/设计/规格、验收索引、完整计划执行表与 progress/roadmap；已有通过项不重复，无新证据不扩充结论。

恢复增量已核对：四组真实事务中断/控制器更换与首次恢复失败后重试通过，DEV-083 已解决；140 网络/DNS、557 控制器和 107 QA 工具测试通过。35 个安装文件匹配、QA 清零、生产快照一致，见[恢复验收](../../infra/sealskin/r7g-controller-recovery-acceptance-2026-09-30.md)。本项未收尾，继续公网认证路径、并发边界与发布材料；客户端暂缓，生产不部署。

## 2026-09-30：按选项 1 恢复隔离实施

用户明确选择先推进 R7G。R7F 转为待验证，原未验收条件保持；当前仅本项实施，不部署生产。

- 范围：补齐真实控制器 monitor、批准 DNS TTL、认证 SOCKS5 双端点、实际 Worker 网络路径的集成；生成独立 QA 凭据，不使用生产代理凭据。
- 完成条件：真实 DNS A→B 驱动新连接切换，旧连接保持、Worker/Session 代次不变；认证/连通性失败保留旧端点且无直连；多个隔离 Home/代次互不串用，资源可清理。供应方自然漂移与目标 Mac/Trilium 观察仍单列，不能由模拟夹具替代。
- 验证：复用固定上游准备器和已有隔离网络工具，新增可重复集成运行器；按改动运行必要回归。QA 前后只读核对生产身份，详细证据存忽略目录。
- 文档清单：本记录/工作项索引、R7F 状态、progress/roadmap、适用设计/规格与组件 README、DEV-072、新增验收及验收索引；实际发现偏差立即另行登记。

### 本轮结果与收尾

[2026-09-30 集成验收](../../infra/sealskin/r7g-controller-integration-acceptance-2026-09-30.md)：补齐 QA 命令通道（DEV-081），发现并修复 SDK 停止调用、恢复归属与 pending 保留（DEV-082）。139 网络/DNS、556 完整控制器、101 QA 工具回归和 8 组真实集成通过；两个 Home 的旧新连接、认证/DNS 故障、独立换代及所属 Relay 双失败停止/peer 健康/四类绕过拒绝均完成。35 个实际安装控制器文件与固定 manifest 一致。QA 资源清零，临时显示目录清空移除，生产前后基线完全一致。

本轮实现、偏差、验收和组件/设计/规格/索引/进度/计划已更新；最终文档静态核对记录见报告。本轮隔离交付完成，R7G 整体未收尾：公网供应方自然漂移认证、目标客户端热切换及实机控制器重启 pending 场景仍归本项，不把 Worker 内 Python HTTPS 当作浏览器页面验收。没有开启下一项或生产部署。

## 目标与范围

- 用户要求 / 对应计划：R7F 发现动态代理域名漂移后的后续实现；对应 [R7](../roadmap.md#r7)。
- 本项交付与完成条件：为 `proxy_required` 的域名上游增加可选动态模式；控制器按批准 DNS/TTL 重新解析，先验证候选 IPv4，再通过 Relay 真实探测，Guard 以有界 A→A+B→B 原子切换，Relay 通过原子 endpoint lease 让新 TCP 连接使用新地址；失败保留旧 lease/规则并 fail closed。数值 IP、DIRECT 和旧静态策略保持兼容。
- 本次验证、部署与客户端范围：固定 SealSkin 上游离线展开、Relay 单元测试和生命周期专项测试；独立 QA 动态 DNS/两个模拟 IPv4 的真实切换、失败回滚、无直连检查和清理。生产 Personal/Work、Home、账号、Session、凭据和正式镜像本项不启动、不部署、不修改。
- 前置项及其收尾记录：R7A–R7E 已收尾；R7F 保留待验证，用户明确选择先推进本项隔离开发；本项不宣称 R7F 或生产发布完成。

## 阅读与代码核对

| 材料 / 代码入口 | 核对结论 |
| --- | --- |
| 进度、计划、设计、相关规格 | 既有设计要求静态代次冻结地址；动态模式需记录偏差并限定为域名策略的每代 endpoint lease。 |
| 组件说明、最新适用验收 | SealSkin 生命周期由 `prepare.py`、`profile-lifecycle.patch`、`network_runtime.py` 管理；Relay Guard 由 `network-guard.py` 安装 nft 规则，Relay 上游由 `upstream.go` 建连。 |
| 配置/请求入口、状态、实际副作用、测试 | 候选通过 `dynamic-upstream.patch` 启动监视器，租约和网络规则写入受控 runtime 目录；Relay 每次新连接读取 endpoint lease；动态专项已纳入固定准备器回归。 |
| 已有工作区改动、运行版本与生效范围 | 工作区已有动态候选及大量 R7F 用户改动；候选未打包、未部署，2026-09-30 的生产 Personal/Work 均已恢复，Home/Session 保留；“测试”窗口由用户主动关闭。 |

## 实施与偏差

- 先验证补丁与固定上游 commit 可应用，再补齐准备器 payload/manifest 输入和测试。
- 偏差文件：[DEV-2026-09-27-072](../deviations/DEV-2026-09-27-072-dynamic-endpoint-lease.md)。

## 验收复核

| 原要求 / 验收编号 | 实现位置 | 检查与证据 | 结果 / 未测范围 |
| --- | --- | --- | --- |
| 动态域名解析变化不重启 Worker | `dynamic_upstream.py`、Relay endpoint lease | patched tree 网络运行时/DNS 专项、完整 server/tests；固定 Go Relay 双模拟上游连接切换；公开域名权威/递归解析只读核对 | 隔离 QA 与当前委派解析核对通过；9 月 30 日已补控制器/认证 SOCKS5/Worker 集成；供应方自然漂移认证及客户端页面 QA 待独立完成 |
| Guard 过渡允许旧/新，成功后仅新地址 | `network-guard.py`、`dynamic_upstream.py` | FakeDocker A→A+B→B；独立 Docker namespace 实际 nft 旧→双→新和失败保留 | 隔离 QA 通过；真实生产网络仍未部署 |
| 探测失败回滚且无 DIRECT 绕过 | `dynamic_upstream.py`、网络隔离验收 | 探测失败、pending 恢复、Relay fail-closed 测试 | 隔离 QA 通过 |
| 数值 IP / DIRECT / 无 capability 镜像兼容 | `network_runtime.py` 分支 | 完整 server/tests 551 passed | 隔离 QA 通过 |
| stop/remove 清理 lease、并发 monitor 隔离 | 生命周期清理与锁 | 网络运行时/DNS 专项 134 passed | 9 月 30 日双 Home 并存、单 Home 换代及 peer 保持通过；压力并发未测 |

## 文档与收尾

- [x] 逐项回看原始任务、计划、设计和实际行为。
- [x] 完成本项候选验证，公开报告与私有证据范围明确。
- [x] 完成 DEV-072 及相关偏差处理；真实公网委派与客户端验收仍保持打开。
- [x] 更新设计/规格/Relay 与 SealSkin README。
- [x] 更新验收索引。
- [x] 更新开发进度与开发计划。
- [x] 核对 QA 清理、回滚材料、链接及工作区变更。
- [x] 更新本记录与工作项索引；本次按用户选项 1 调整隔离实施顺序，后续计划仍需本项收尾。

收尾结论：未收尾。候选实现、固定回归、双 A wire 轮换、nft 实机过渡/失败回滚、模拟双上游 Relay QA 和供应方自然漂移/端口可达性观察已完成；2026-09-30 已补齐独立凭据的控制器/Worker 集成；剩余为公网供应方与目标客户端观察及实机重启 pending 验证。生产 Personal/Work 不启动、不部署、不修改。

公网增量：新端点离线包和本地协议检查通过，两台授权测试机部署/HTTPS 可达。QA 权威本机 UDP/TCP 正常，公网 DNS 被当前 IPv4 入站规则阻断，见 [DEV-084](../deviations/DEV-2026-09-30-084-public-qa-dns-ingress.md)；公网轮换未执行，临时规则候选通过 dry-run，当前先继续独立工作。

审核材料增量：1,015 文件双重校验、84 控制器文件离线重现及 Relay 字节一致复建通过，见[材料验收](../../infra/sealskin/r7g-review-materials-acceptance-2026-09-30.md)。材料仍为 audit-only，未完成公网/并发/最终组合条件，不宣布 R7G 收尾。

## 生命周期并发增量（2026-09-30，当前实施）

范围：同一 QA Home 的同 operation 并发启动只允许一个实例；两个 Home 并发启动不串用；真实 monitor 持锁更新期间 stop 等待，另一个 Home 的查询/连接仍可用；停止清理后换代，旧 operation stop 被拒绝且不触及新代次。压力容量归后续 R6，不把这些边界检查写成容量上限。

代码地图：`guard_launch` 的 pending/同 Home 锁 → `endpoint_monitor` 的同 Home 锁和重读 reservation → `stop_profile_locked` 的归属/正常退出/清理；QA 用真实规则调用 gate 保留有界中断点。公网范围确认前不改防火墙；同一空 QA 环境暂时保存公网政策/凭据/应用定义并切换私有夹具，完成后在零代次状态恢复准确 QA 配置，公网证据保持未执行。

完成条件：并发响应与唯一资源对应，monitor/stop 顺序及真实旧资源消失有证据，新代次 ID/lease 不复用，陈旧请求拒绝，peer 不受影响，私有夹具清理并恢复 QA 公网准备状态，生产快照一致。结果/偏差与组件说明、验收索引、进度/路线图和完整计划表同步。

并发结果：三组实机检查通过，8 个同时启动请求为每 Home 一个 200/三个 409；monitor 持锁期间 stop 等待、peer 可用；换代后旧 stop 409 且新代次和 peer 保持。下一步同项兼容验证：以现行生产控制器/静态 Relay 精确镜像创建独立 QA 代次，在不重启 Worker 下切换候选控制器；保留一个静态 Home，另一个正常换代为动态域名路径并验证互不影响。只在动态代次正常清理后测试旧控制器回退。不得把文件一致性或此 QA 旧格式凭据解释为真实生产 Home/Secret Store 迁移已完成。

兼容结果：四组实机旧静态创建、候选重接、静态/动态并存及动态清理后的旧控制器回退通过，详见[兼容验收](../../infra/sealskin/r7g-static-upgrade-acceptance-2026-09-30.md)。实际应用 96→97 文件核对证明既有 overlay 保留；私有资源清零并恢复公网准备配置。并发/兼容条件本轮已补齐，公网自然漂移认证/最终发布条件仍待，客户端暂缓。

## 动态端点与 Secret Store 组合（2026-09-30，当前实施）

代码核对发现已有动态实机使用文件凭据，尚未覆盖生产能力中的加密 Store/tmpfs 租约分支。补齐同项发布组合：两个 Home 的独立授权、动态切换时凭据租约不变、monitor 持锁时撤销仍先阻断出站再正常清理、另一个 Home 保持、旧引用不能重启。通过官方 Store 实现生成全新 QA 密钥/版本，不访问生产凭据。

代码地图：`prepare` 的 endpoint lease + `secret_runtime.materialize/credential_guard` → Relay 两种租约校验 → `secret_runtime.revoke` 先持久 tombstone/失效 credential lease、阻断，再取 Home 锁清理；与动态 monitor 同时执行时不得复活已撤销出站。隔离 tmpfs/密钥挂载只加到精确 QA 控制器；完成后移除本轮 Store、挂载和资源并恢复公网准备。此范围不扩大成生产 Store/Home 迁移或整机备份演练。

Secret Store 组合结果：三组实机通过，含 monitor 持锁期间撤销先阻断/后清理、旧引用重启拒绝和 peer 保持；临时挂载及 tmpfs 清理，QA 公网准备恢复，私有 Store/密钥/tombstone 离线保留。见[验收](../../infra/sealskin/r7g-secret-combination-acceptance-2026-09-30.md)。产品源码未变，公网认证/最终发布仍未完成。

本轮收尾：三组并发、四组旧静态兼容/回退及三组动态/Store 组合的证据、组件/设计/规格与索引已同步；生产与 IPv4 入站规则保持。两台公网进程/目录、基础 QA/网络/代次和 tmpfs 已清理，权威恢复原停止状态，私有审计材料保留。公网复查仍超时，未应用规则；R7G 保持待公网验证/最终材料，未开始下一项计划，不缩小“所有计划”的目标。

最终静态复核：15 份文档的 568 个相对链接、86 个锚点、3 个新增 QA 运行器语法和 `git diff --check` 均通过；按专用 QA 标签再次核对容器/网络为空。三份 summary 分别为 3/4/3 组 PASS，公网保持 NOT_RUN。

阻塞复核（2026-09-30）：同一 DEV-084 条件连续三个目标执行轮次仍存在；期间可独立进行的恢复、并发、静态兼容、Store 组合与审核材料已完成。最新只读核对显示 IPv4 入站链未变化，QA 容器/网络为空、权威停止、两个远端目录已 purge。未收到临时规则范围答复，不能应用规则或将公网验收/最终发布材料标为完成；按 workflow 未收尾不启动下一项。完整目标标记为 blocked，所有后续计划和客户端暂缓状态保持。

授权后公网结果：三组受控公网 A→B→A 检查通过，见[公网验收](../../infra/sealskin/r7g-public-acceptance-2026-09-30.md)。DEV-084 临时规则回收、原链一致；DEV-085 QA 保活和 stdin 读取修复，失败保留。全量 QA/远端/显示资源清零，生产快照一致；产品候选不变。当前仅商业供应方自然漂移认证、最终材料和暂缓的客户端条件仍待，不开始下一工作项。

2026-10-01 汇总材料：1,031 文件审核候选校验通过，原密封包保持，补入并发/静态兼容/Store/公网证据与工具。见[汇总材料](../../infra/sealskin/r7g-consolidated-review-2026-10-01.md)。本轮文档、临时维护回收和 QA 交付完成；商业供应方自然漂移仍缺证，最终发布门槛和客户端暂缓条件保持，未部署生产。

本轮最终静态核对：12 份文档的 568 个本地链接目标、2 个 Python 文件语法、5 项 zone 所有权测试与 git diff --check 通过。独立管道回归覆盖连续配置/命令、原连接空闲保活、无多余标准输出及后续命令/关闭。私有 static-review.json 和 worker-command-check.json 留存；全部公网资源与临时规则已清理。下一步已提交明确选择：保留缺证并调整顺序，或授权限定供应方 QA；等待答复时不读取生产凭据或部署候选。
