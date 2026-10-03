# 设计偏差记录

- [DEV-157 长启动HTTPS响应头预算](DEV-2026-10-03-157-long-start-tls-header-timeout.md)：处理中；共享30秒Transport截断180秒启动，需独立长请求Transport及TLS回归。

- [DEV-156 同主机QA网络变化](DEV-2026-10-03-156-fresh-qa-host-network-change.md)：处理中；host网络客户端因Docker接口变化取消启动，改为隔离namespace与固定Unix转发。

- [DEV-155 显式空状态与安装就绪](DEV-2026-10-03-155-explicit-empty-install-state.md)：处理中，缺失业务目录/账号表不能充当初始化状态；安装回执需等待真实就绪。

- [DEV-154 root内置镜像校验](DEV-2026-10-03-154-root-builtin-verification.md)：处理中，安装器需以目标非root用户执行只读校验，原失败保留。

- [DEV-153 全新控制器UID绑定](DEV-2026-10-03-153-fresh-controller-uid-binding.md)：处理中，非1000系统用户需要同步配置两组UID/GID；保留首次安装失败。

- [DEV-152 1.0遗留维护入口](DEV-2026-10-03-152-v1-source-maintenance-hooks.md)：处理中，工作区已清理但旧部署仍含临时入口，1.0须重新构建和验证。

- [DEV-151 QA产物目录关联](DEV-2026-10-03-151-qa-artifact-directory-binding.md)：已完成R6AW最终24组合、适用补证/包校验及部署；原失败保留。

- [DEV-150 Firefox首次存储探针超时](DEV-2026-10-03-150-firefox-storage-probe-timeout.md)：QA分配修订及本机两项原门槛完整验收通过；异机首次建库超时限制和failed保留。

- [DEV-149 QA与冷导入I/O竞争](DEV-2026-10-03-149-qa-shutdown-io-contention.md)：执行隔离修订及原门槛完整替代验收通过；原12秒关闭失败保留。

[DEV-148 TW自动Chromix输入错序](DEV-2026-10-03-148-dynamic-input-order.md)：已完成R6AW最终24组合、适用补证/包校验及部署；原失败保留。

[DEV-147 固定Camoufox桌面证据](DEV-2026-10-02-147-fixed-camoufox-desktop-evidence.md)：已完成R6AW最终24组合、适用补证/包校验及部署；原失败保留。

[DEV-146 内置包关联校验](DEV-2026-10-02-146-builtin-package-binding.md)：已完成R6AW最终24组合、适用补证/包校验及部署；原失败保留。

[DEV-145 客户端DPR与尺寸截断](DEV-2026-10-02-145-client-dpr-resolution-clamp.md)：已完成R6AW最终24组合、适用补证/包校验及部署；原失败保留。

[DEV-144 BiDi初始文档就绪](DEV-2026-10-02-144-bidi-initial-document-readiness.md)：已完成R6AW最终24组合、适用补证/包校验及部署；原失败保留。

[DEV-143 重连输入验收](DEV-2026-10-02-143-remote-reconnect-input.md)：已完成R6AW最终24组合、适用补证/包校验及部署；原失败保留。

[DEV-142 独立机QA运行身份](DEV-2026-10-02-142-remote-qa-runtime-user.md)：已完成R6AW最终24组合、适用补证/包校验及部署；原失败保留。

- [DEV-141 旧Home归档元数据](DEV-2026-10-02-141-legacy-home-archive-metadata.md)：已解决，R6AV部署与实际清理通过。

- [DEV-140 账号初始化状态](DEV-2026-10-02-140-account-bootstrap-state.md)：已解决，R6AV部署与实际清理通过。

R6AU维护偏差DEV-133至139现均已解决，完整恢复与生产验收见[R6AU报告](../../infra/sealskin/r6au-consistent-business-backup-acceptance-2026-10-02.md)；以下早期条目保留追踪入口。

- [DEV-139 离线Worker安全配置](DEV-2026-10-02-139-offline-worker-security-options.md)：已解决，R6AU三份断网副本验证通过。

- [DEV-138 恢复内核挂载](DEV-2026-10-02-138-recovery-kernel-mount.md)：已解决，R6AU完整读回通过。

- [DEV-137 Firefox原生排序规则读回](DEV-2026-10-02-137-sqlite-native-collation-readback.md)：R6AU处理中，普通数据库完整检查与原生排序表扫描分别记录，不伪造索引通过。

- [DEV-136 大归档解压读取顺序](DEV-2026-10-02-136-backup-gzip-verification-order.md)：R6AU处理中，保持完整验证并修复重复解压开销。

- [DEV-134 整体备份作业链接](DEV-2026-10-02-134-business-backup-job-links.md)、[DEV-135 维护恢复就绪门槛](DEV-2026-10-02-135-maintenance-controller-readiness.md)：R6AU处理中，首次真实备份未生成归档，先恢复原活动浏览器。

- [DEV-133 维护容量前置遗漏](DEV-2026-10-02-133-maintenance-capacity-preflight.md)：R6AU 处理中，先恢复容量与Personal，再继续备份。

- [DEV-132 原生启动请求超时](DEV-2026-10-02-132-native-launch-request-budget.md)：R6AS 已解决并完成范围内验收。

- [DEV-131 原生 QA 控制器重建依赖](DEV-2026-10-02-131-native-qa-controller-recreation.md)：R6AS 已解决并完成范围内验收。


- [DEV-130：缩放保存当前资产覆盖](DEV-2026-10-02-130-scaling-asset-coverage.md) · R6AR 已修复并部署。
[DEV-129 Relay APK 版本留存](DEV-2026-10-02-129-relay-apk-version-retention.md)：已解决并部署，明确补丁锁、全部集成与异机镜像核对通过。

[DEV-128 灾备 QA Cookie 有效期](DEV-2026-10-02-128-recovery-cookie-lifetime.md)：已解决；一年期合成 sentinel 新检查点跨机读回/回退通过，历史过期证据保留。

[DEV-127 原生异机恢复模块冲突](DEV-2026-10-02-127-remote-recovery-module-collision.md)：已解决，独立模块名加载后 Camoufox/Chromix 跨机恢复、重开和回退通过。

- [DEV-126 控制器测试目录来源差异](DEV-2026-10-02-126-controller-test-source-provenance.md)：R6AK已解决，线上97文件匹配原发布审计，精确源码554项补测通过。

- [DEV-125 固定容量未随机器变化](DEV-2026-10-02-125-fixed-capacity-machine-sizing.md)：R6AI已解决并部署，自动资源推导及人工覆盖。

[DEV-124 删除密码确认弹窗](DEV-2026-10-02-124-delete-reauth-dialog.md)：R6AF已解决并部署。

[DEV-123 弹窗布局与手机键盘](DEV-2026-10-02-123-dialog-password-layout.md)：R6AE已修复、验收并部署。

[DEV-120](DEV-2026-10-02-120-reference-ui-health-summary.md)：已解决并部署；R6AA健康统计、搜索/弹窗和焦点修正通过真实UI与回归，原数据保持。

[DEV-119](DEV-2026-10-01-119-chromix-fullscreen-sized-window.md)：已解决并部署；R6Z1修正同屏尺寸窗口，隔离及线上新任务完整验收通过，原失败记录保留。

[DEV-118](DEV-2026-10-01-118-browser-network-select.md)：已解决并部署，R6X 单个浏览器网络下拉与安全/回显/布局回归通过。

[DEV-117](DEV-2026-10-01-117-create-network-binding.md)：已解决并部署，创建完整绑定/持久重试/跨管理员缓存边界通过。

- [DEV-114 计划状态对账](DEV-2026-10-01-114-plan-status-reconciliation.md)：已解决，R6T当前摘要/39项规格与运行版本对账完成，历史缺证保留。

- [DEV-113 Firefox 固定小窗口输入](DEV-2026-10-01-113-firefox-fixed-input-probe.md)：已解决，R6S完整验收并限定部署；原失败证据保留。

- [DEV-112 Chromix 固定小窗口被最大化](DEV-2026-10-01-112-chromix-fixed-window-rule.md)：已解决，R6S完整验收并限定部署；原失败证据保留。

- [DEV-108 设备生成与显示尺寸耦合](DEV-2026-10-01-108-fingerprint-generation-screen-coupling.md)：已解决，R6S完整验收并限定部署；原失败证据保留。

- [DEV-107 动态显示输入几何](DEV-2026-10-01-107-dynamic-input-geometry.md)：已解决，R6S完整验收并限定部署；原失败证据保留。

- [DEV-106 空指纹页与Firefox默认组合](DEV-2026-10-01-106-template-empty-state-and-defaults.md)：已解决，R6S完整验收并限定部署；原失败证据保留。

- [DEV-104 原生窗口能力](DEV-2026-10-01-104-native-window-capability.md)、[DEV-105 空目录发布](DEV-2026-10-01-105-empty-template-catalog.md)：R6R 已解决并部署。

- [DEV-099 组合发布中断恢复](DEV-2026-10-01-099-template-publication-recovery.md)：已解决并部署，R6P；原产物/验收保持，真实中断与显式恢复通过。

[DEV-098 模板作业执行器](DEV-2026-10-01-098-template-job-runner.md)：R6P 修复中。

新增：[DEV-097 · UI scaling](DEV-2026-10-01-097-ui-scaling.md)，服务器修复已部署，待用户切换验证。

[文档导航](../README.md) · [工作流程](../workflow.md) · [工作项](../work-items/README.md) · [当前架构](../design.md)

实施或复核中发现设计与代码、配置、实际行为不一致时，立即使用 [模板](template.md) 建立记录。文件命名为 `DEV-YYYY-MM-DD-NNN-主题.md`，登记本索引并链接所属工作项。

状态使用 **待核对 / 待处理 / 处理中 / 已解决 / 待外部条件**。选择修订设计时，说明依据、影响和验收变更；选择后续处理时，写明对当前交付的影响与承接计划，不能提前标为已解决。

| 编号 | 工作项 | 差异 | 处理方式 | 状态 |
| --- | --- | --- | --- | --- |
| DEV-2026-10-01-088 | R6K | [Adapter 恢复依赖](DEV-2026-10-01-088-adapter-recovery-dependencies.md) | 补齐归档依赖及显式重绑检查 | 已解决（管理依赖范围） |
| DEV-2026-10-01-087 | R6J1 | [日志候选目录权限](DEV-2026-10-01-087-log-candidate-directory-mode.md) | 逐文件复制并重验 | 已解决 |
| [DEV-085 公网 WSS 空闲](DEV-2026-09-30-085-public-wss-idle.md) | [R7G](../work-items/R7G-2026-09-27-dynamic-upstream-hot-switch.md) | QA 等待超过端点 15 秒空闲限制 | 原连接定期 nonce 回显，无重连 | 已解决 |
| [DEV-084 公网 QA DNS 入站](DEV-2026-09-30-084-public-qa-dns-ingress.md) | [R7G](../work-items/R7G-2026-09-27-dynamic-upstream-hot-switch.md) | IPv4 UDP 53 规则在 return 后不可达，TCP 53 未放行 | 用户已允许两条临时精确规则，执行并按 handle 回收 | 已解决 |
| [DEV-083 恢复残留错误](DEV-2026-09-30-083-dynamic-recovery-stale-error.md) | [R7G](../work-items/R7G-2026-09-27-dynamic-upstream-hot-switch.md) | 旧回滚错误导致成功恢复后仍拒绝控制器接入 | 成功恢复后清除当前错误，失败保持 pending；四组实机恢复及 557/107 项回归通过 | 已解决（隔离候选） |
| [DEV-082 动态回滚停止](DEV-2026-09-30-082-dynamic-fail-closed-stop.md) | [R7G](../work-items/R7G-2026-09-27-dynamic-upstream-hot-switch.md) | SDK 停止调用不兼容，恢复失败分支可能触及归属未证实资源 | 修复调用/归属/pending 并验证真实故障关闭 | 已解决（隔离候选） |
| [DEV-081 动态 QA 执行通道](DEV-2026-09-30-081-dynamic-qa-exec.md) | [R7G](../work-items/R7G-2026-09-27-dynamic-upstream-hot-switch.md) | 既有 QA 未支持动态规则命令和 attached 回执 | 限定代次、镜像与命令，补齐真实集成 | 已解决（隔离候选） |
| [DEV-2026-09-30-080](DEV-2026-09-30-080-final-source-snapshot-drift.md) | [R7F](../work-items/R7F-2026-09-23-production-release.md) | 旧发布源码副本的 4 个文件与最终 76 文件清单不符，当前仓库匹配 | 保留旧副本，新 76 文件源码以原工具链复建与运行二进制逐字节相同；109 文件材料校验通过 | 已解决（最终源码副本） |
| [DEV-2026-09-30-079](DEV-2026-09-30-079-display-template-effect-label.md) | [R7F](../work-items/R7F-2026-09-23-production-release.md) | 显示模板仍以 X11/Selkies 命名，与效果名称契约不符 | 真实 Chromium 9 组复验通过，生产只修正 label；ID/revision、缩放和运行绑定保持 | 已解决（展示元数据） |
| [DEV-2026-09-30-077](DEV-2026-09-30-077-launch-definition-lock.md) | [R7F](../work-items/R7F-2026-09-23-production-release.md) | Ensure 取锁前读取目录，等待期间可能跨过配置变更门禁 | 锁内读取目录与状态，确定性并发回归、全量 Go/race 与限定发布通过 | 已解决（已部署） |
| [DEV-2026-09-29-076](DEV-2026-09-29-076-direct-capability-observation.md) | [R7F](../work-items/R7F-2026-09-23-production-release.md) | 控制器返回 DIRECT 能力，但 Adapter 解码与 inspect 映射漏掉字段 | 保留实际版本，旧控制器缺字段仍为 0；加密协议回归及限定 Adapter 发布复核 | 已解决（已部署） |
| [DEV-2026-09-29-075](DEV-2026-09-29-075-release-status-drift.md) | [R7F](../work-items/R7F-2026-09-23-production-release.md) | 当前部署说明混杂旧 Adapter、Personal 状态和目录未部署结论 | 只读核对实际版本、资源、备份和绑定，更新现行入口并保留历史范围 | 已解决（当前摘要已同步） |
| [DEV-2026-09-29-074](DEV-2026-09-29-074-environment-registration-template-metadata.md) | [R7F](../work-items/R7F-2026-09-23-production-release.md) | R6E 环境登记器未写 R7D 要求的浏览器模板一致性元数据，r10 直接登记后不能进入兼容目录 | 显式绑定模板及共用登记路径已修复；已有九项回归、r10 实际登记/绑定/启动，三个 accepted 条目七字段与原 artifact 派生值一致；客户端缺项归 DEV-073/R7F | 已解决（登记器元数据） |
| [DEV-2026-09-29-073](DEV-2026-09-29-073-managed-browser-desktop-recovery.md) | [R7F](../work-items/R7F-2026-09-23-production-release.md) | 模板化 Camoufox 退出后，通用恢复提示错误引导从桌面启动未受管的系统 Firefox | 模板化 Profile 改用安全关闭与固定入口重建；r10 已部署，Mac 用户确认实际右键无 Firefox，Trilium 0.106.0 菜单无法检查；16:55 UTC “测试”BROWSER_EXITED，用户已确认主动关闭，当前状态保留 | 处理中 |
| [DEV-2026-09-27-072](DEV-2026-09-27-072-dynamic-endpoint-lease.md) | [R7G](../work-items/R7G-2026-09-27-dynamic-upstream-hot-switch.md) | 既有规格冻结单 IP；动态 DNS 需要同一代次按 TTL 更新端点 | 增加显式动态 endpoint lease 与 Guard 原子切换；隔离 QA、公开解析和一次自然漂移/端口观察通过，生产前仍需 SOCKS5/客户端 QA | 候选及隔离 QA 已处理，客户端 QA 待完成 |
| [DEV-2026-09-27-070](DEV-2026-09-27-070-private-recovery-key-transcript-exposure.md) | [R7F](../work-items/R7F-2026-09-23-production-release.md) | 旧管理员恢复 JSON 被完整读取，私钥进入本次私有操作会话输出 | 原 age 备份认证旧身份，现行接口明确 401；新恢复身份与 profile-admin 为 200，临时明文已清理、生产身份保持 | 已解决（旧身份拒绝已验证） |
| [DEV-2026-09-30-078](DEV-2026-09-30-078-work-dns-probe-evidence.md) | [R7F](../work-items/R7F-2026-09-23-production-release.md) | Work 私有运行探针的 UDP DNS 报文无效，超时不能证明被阻止 | 有效查询得到明确拒绝；共享探针修正、3 项回归和当前组合正常/故障 QA 通过，失败与原证据保留 | 已解决（私有/共享工具及实际 QA） |
| [DEV-2026-09-27-071](DEV-2026-09-27-071-legacy-managed-network-binding.md) | [R7F](../work-items/R7F-2026-09-23-production-release.md) | R6 旧目录的受管理策略缺少显式 `network_mode`，R7C 绑定被错误拒绝 | 仅对有效旧策略兼容迁为显式 `proxy_required`；代码/QA 与生产绑定通过，9 月 30 日 Personal 新代次 PROXY_OK、Worker HTTPS 通过 | 已解决（代码/QA/生产） |
| [DEV-2026-09-27-069](DEV-2026-09-27-069-proxy-dns-address-drift.md) | [R7F](../work-items/R7F-2026-09-23-production-release.md) | Personal 旧数值代理地址漂移后不可达，当前原策略探针仍超时 | 经新备份/授权绑定现有 tw r1 恢复新代次 PROXY_OK，Mac 公网页面通过，原有书签/登录确认项不适用；后续动态轮换归 R7G | 已解决（本次生产恢复） |
| [DEV-2026-09-23-068](DEV-2026-09-23-068-network-probe-time.md) | [R7E](../work-items/R7E-2026-09-23-management-network-home-ui.md) | R7C 未保存失败探针的结果时间 | 增加可选 `probe_at`，仅实际探针写入；旧记录不补造时间 | 已解决（候选未部署） |
| [DEV-2026-09-22-067](DEV-2026-09-22-067-network-profile-mutation-boundaries.md) | [R7C](../work-items/R7C-2026-09-21-network-profile-catalog.md) | 停用/撤销表单要求幂等键但服务未使用；绑定与撤销缺少共享串行边界；创建/探测未执行方案要求的近期确认密码 | 持久幂等审计、统一目录变更互斥、所有敏感代理写入口重新认证；重复/冲突/并发/网关回归通过 | 已解决（候选未部署） |
| [DEV-2026-09-21-066](DEV-2026-09-21-066-focused-network-qa-cleanup-evidence.md) | [R7B](../work-items/R7B-2026-09-21-managed-work-egress.md) | 网络 QA 清理器已支持浏览器专用运行，却只接受完整矩阵的固定 `live-results.json` 文件名 | 接受同证据根内显式、非链接且 `result=PASS` 的聚焦摘要；R7B 实际清理归零 | 已解决 |
| [DEV-2026-09-21-065](DEV-2026-09-21-065-work-firefox-proxy-policy.md) | [R7B](../work-items/R7B-2026-09-21-managed-work-egress.md) | 现行 Work 镜像没有 Firefox SOCKS/远端 DNS 锁定配置；只绑定策略时浏览器直连并被 Guard 正确阻断 | 精确 Work 父层增加最小受管理网络层并完成隔离验收；生产绑定归 R7F | 已解决（候选未部署） |
| [DEV-2026-09-21-064](DEV-2026-09-21-064-work-qa-launch-context.md) | [R7B](../work-items/R7B-2026-09-21-managed-work-egress.md) | 直接调用生命周期 API 后，QA 把 Launch Context URL 误当作 legacy Firefox 已完成导航，实际仍为 `about:blank` | 保持应用定义；进程就绪后用本机 BiDi 有界等待并显式导航；第六轮通过 | 已解决 |
| [DEV-2026-09-21-063](DEV-2026-09-21-063-work-qa-firefox-argument.md) | [R7B](../work-items/R7B-2026-09-21-managed-work-egress.md) | R7B QA 未识别 Firefox 两种调试参数形式，且 root 无权读取普通用户进程环境时跳过整个进程 | 兼容参数形式；按进程 UID 验证 Wayland 环境/资源；第六轮与清理通过 | 已解决 |
| [DEV-2026-09-20-061](DEV-2026-09-20-061-work-egress-unobserved.md) | [R7-DESIGN](../work-items/R7-DESIGN-2026-09-20-browser-workspace.md) / [R7A](../work-items/R7A-2026-09-21-work-egress-diagnosis.md) / [R7B](../work-items/R7B-2026-09-21-managed-work-egress.md) | 用户反馈 Work 无公网；无受管理策略/路由且旧镜像也缺少 Relay 锁定，healthy 未覆盖公网 | R7F 已部署，Work 新代次 DIRECT healthy、Worker HTTPS 与有效 DNS 拒绝通过；Mac 公网页面及当前组合独立重建/三类存储/实际回退通过；生产原 Home 正常重建/文件一致性与用户页面确认已补齐，原数据项不适用；完整客户端矩阵仍待验收 | 部分处理 |
| [DEV-2026-09-20-062](DEV-2026-09-20-062-network-apply-implicit-stop.md) | [R7-DESIGN](../work-items/R7-DESIGN-2026-09-20-browser-workspace.md) / [R7C](../work-items/R7C-2026-09-21-network-profile-catalog.md) | 规格要求运行中拒绝网络应用，但 emptyRuntime 实际调用 Stop；现有测试仅覆盖 foreign Session | 改为只读空闲门槛并在整个绑定变更窗口持生命周期锁；运行中零 Stop/append/patch 回归及全量 race 通过 | 已解决（候选未部署） |
| [DEV-2026-09-20-060](DEV-2026-09-20-060-ui-deployment-journal-time.md) | [R6H](../work-items/R6H-2026-09-20-management-ui-deployment.md) | Tab UI 发布的日志采集时间格式被 journalctl 拒绝，健康/绑定通过后仍触发自动回退 | 修复 UTC 时间格式，保留首轮与精确回退证据；attempt-2 全部检查通过，Tab 第二版已上线 | 已解决 |
| [DEV-2026-09-20-058](DEV-2026-09-20-058-r4b-live-check-overlay-drift.md) | [R6F](../work-items/R6F-2026-09-19-release-combination.md) | R4B 只读生产检查器仍绑定历史控制器镜像；R6F overlay 已合法替换该镜像，检查器在镜像比对处拒绝 | 保留 R4B 检查器的严格历史范围；以当前 overlay 的明确手工 health/生命周期/回退/客户端证据完成 R6F，不伪造旧检查器通过 | 已解决（版本边界） |
| [DEV-2026-09-20-059](DEV-2026-09-20-059-custom-profile-policy-binding.md) | [R6F](../work-items/R6F-2026-09-19-release-combination.md) | 新建自定义 Profile 复用 Personal 网络策略，控制器按 Profile/Application/Home 绑定返回 HTTP 422，固定入口显示 502；失败时资源归零 | 已追加独立策略并通过服务器及 Mac/Trilium 验收；Profile 随后资源归零、归档删除，应用/授权/secret 清理完成 | 已解决 |
| [DEV-2026-09-20-057](DEV-2026-09-20-057-fixed-runtime-backup-evidence.md) | [R6F](../work-items/R6F-2026-09-19-release-combination.md) | 当前 Work 已固定并验收兼容镜像，但应用定义没有 Camoufox 环境 artifact/acceptance 字段；新格式备份会安全拒绝，旧格式又不允许当前 Store/账号/Session | 保留两种既有路径，增加显式固定运行证据模式；118 项回归及 Work 5,174 条目创建/verify/隔离 restore 通过，未激活恢复副本 | 已解决（工具/生产备份阶段） |
| [DEV-2026-09-20-056](DEV-2026-09-20-056-control-cli-error-classification.md) | [R6F](../work-items/R6F-2026-09-19-release-combination.md) | 私有 control CLI 将 `resume` 的正常拒绝统一输出为 `profile adapter stopped`，无法区分 stopped 与 dormant，且误导服务运行态判断 | 增加稳定 control 错误码和独立命令失败日志，保留最终脱敏与旧 reply 兼容；固定 Go test/vet/gofmt/race 及新 CLI 对旧生产 reply 的 `PROFILE_NOT_DORMANT` 拒绝通过 | 已解决（候选，未部署） |
| [DEV-2026-09-19-055](DEV-2026-09-19-055-encrypted-backup-account-version.md) | [R6F](../work-items/R6F-2026-09-19-release-combination.md) | `secure-backup.py` 只接受 version 1 账号表，当前 R6F 生产账号表已含 `role` 的 version 2 | 校验器接受 version 1/2 并按现行 admin/user 授权规则验证；固定 checks 回归及当前控制根 age 加密/verify/离线 restore 通过，真实生产 Home 备份仍需单独维护窗口 | 已解决（工具/组合 QA） |
| [DEV-2026-09-19-053](DEV-2026-09-19-053-management-production-gating.md) | [R6F](../work-items/R6F-2026-09-19-release-combination.md) | 现有账号缺少不更换密码的角色升级 CLI；未配置控制器管理后端时页面仍显示新增/删除入口 | 无损角色修改与页面/写入口能力门控已回归并部署；生产安全子集启用，完整创建/删除/代理/指纹保持关闭 | 已解决（部分生产启用） |
| [DEV-2026-09-19-054](DEV-2026-09-19-054-r6f-combination-runner-scope.md) | [R6F](../work-items/R6F-2026-09-19-release-combination.md) | 现有组合运行器硬编码旧 R5E QA 根、资源注册表和控制器身份，不能直接验证当前 R6F/r9 组合 | 按用户授权改为现有环境受控手工组合；overlay 已安装并完成固化/自定义指纹、代理探测和清理，自动运行器改造列为后续独立范围 | 已解决（现有环境范围） |
| [DEV-2026-09-19-052](DEV-2026-09-19-052-stale-release-package.md) | [R6F](../work-items/R6F-2026-09-19-release-combination.md) | R4B `release-ready-2` 准备摘要早于当前 r9 生产配置/状态写入，旧包复核拒绝 live input drift | 保留旧包为回退材料；R6F 已重新构建并绑定当前输入，candidate-10/12 摘要核对一致 | 已解决（历史包隔离） |
| [DEV-2026-09-18-051](DEV-2026-09-18-051-environment-job-runner.md) | [R6E](../work-items/R6E-2026-09-18-custom-fingerprint-jobs.md) | 规格要求“服务端”在隔离容器中生成/验收自定义指纹；Adapter 无 Docker 权限且不应成为第二个容器所有者，完整验收需要一次性网络与 QA 夹具 | Adapter 只写私有 spool 请求并读状态；主机执行器持 Docker 组一次处理一个作业（只读根/无网络/限额生成、有界重试、完整验收、镜像 verify 后原子追加目录），失败保留证据不发布 | 已解决（候选，未部署） |
| [DEV-2026-09-18-050](DEV-2026-09-18-050-proxy-draft-probe-scope.md) | [R6D](../work-items/R6D-2026-09-18-proxy-drafts.md) | 规格要求草稿探针在隔离网络中验证并给出出口地区；草稿阶段没有 generation/Guard/Relay，出口地区依赖运行中代次的一致性报告 | 修订实现范围：控制器进程内有界协议/TLS 探针，冻结公网 IPv4、拒绝私网；启动门槛仍由 Guard 探针与一致性策略承担 | 已解决（候选补丁，真实上游未测） |
| [DEV-2026-09-18-049](DEV-2026-09-18-049-proxy-secret-import-channel.md) | [R6D](../work-items/R6D-2026-09-18-proxy-drafts.md) | 规格要求 Adapter 经 tmpfs 调用同一导入路径并写策略注册表；Store/注册表只在控制器容器内，Adapter 无挂载也不应持有主密钥 | 第二层补丁增加管理员加密接口：Store 导入只返回引用、策略只追加并按控制器规则计算摘要；Adapter 不落盘凭据 | 已解决（候选补丁，未部署） |
| [DEV-2026-09-18-048](DEV-2026-09-18-048-home-archive-controller-api.md) | [R6C](../work-items/R6C-2026-09-18-create-delete-launch.md) | 固定上游只有 Home 创建/删除接口，未提供保留内容的归档操作 | 增加版本化 `environment-management.patch`，由控制器在 Home 锁内原子移动并提供幂等清单；Adapter 不直接操作 Home，生产未部署补丁 | 已解决（候选补丁，未部署） |
| [DEV-2026-09-18-047](DEV-2026-09-18-047-profile-directory-lock-contract.md) | [R6B](../work-items/R6B-2026-09-17-directory-roles-stop.md) / [R6](../work-items/R6-2026-09-16-environment-management.md) | 规格把 Profile 目录并发保护写成目录文件独立 `flock`，实现使用 Adapter 全局服务锁保证单写者并以进程内互斥串行更新 | 修订设计：明确服务锁 + 进程内互斥 + 0600/fsync/原子替换；既有服务锁/目录测试及全模块回归通过 | 已解决 |
| [DEV-2026-09-18-046](DEV-2026-09-18-046-profile-directory-cli-grants.md) | [R6B](../work-items/R6B-2026-09-17-directory-roles-stop.md) / [R6](../work-items/R6-2026-09-16-environment-management.md) | 账号 CLI 在持久化目录启用时把权威目录与静态种子 Profile 合并，目录读取失败也退回种子，可能写出运行中 Adapter 会拒绝的授权表 | 修复实现：目录 ID 完全取代种子，目录读取失败即拒绝；新增回归后 147 项测试与全模块 race 通过，候选未部署 | 已解决 |
| [DEV-2026-09-17-045](DEV-2026-09-17-045-manage-list-role.md) | [R6A](../work-items/R6A-2026-09-17-environment-list.md) / [R6](../work-items/R6-2026-09-16-environment-management.md) | R6A 候选对任意登录账号放行 `/manage/`，用户 2026-09-17 补充要求管理面板仅管理员、浏览器入口用各自账号 | 修复实现（R6B）：账号表 v2 `role`、网关按角色放行、旧账号视为 `user`、最后管理员保护；Go 测试通过，候选未部署 | 已解决 |
| [DEV-2026-09-17-044](DEV-2026-09-17-044-production-maintenance-runner.md) | [R4B](../work-items/R4B-2026-09-14-target-client-migration.md) | 维护执行器错误复用 QA 管理端口，并误判控制 socket 配置、多 Cookie、根路径状态和 `embedded` 参数 | 保留两次维护失败，按生产端口/同配置指纹和精确授权契约续接；两个目标代次及公网认证通过 | 已解决（生产续接） |
| [DEV-2026-09-17-043](DEV-2026-09-17-043-caddy-api-config-persistence.md) | [R4B](../work-items/R4B-2026-09-14-target-client-migration.md) | API 加载的入口候选会在 Caddy/主机重启后被旧磁盘直达路由覆盖 | `--resume`/autosave drop-in 已安装；正式 Caddy/Docker/VPS 重启后候选、认证边界与两 Profile 恢复通过 | 已解决 |
| [DEV-2026-09-15-042](DEV-2026-09-15-042-work-wayland-shutdown.md) | [R4B](../work-items/R4B-2026-09-14-target-client-migration.md) | Work 原生 Wayland 无法使用现有 X11 正常退出层，阻止共享控制器后的兼容新建 | 固定 labwc/Firefox 原生关闭；控制器/s6、恢复、入口、五类错误材料、秘密边界和清理通过，兼容镜像已随 R4B 部署 | 已解决（已部署） |
| [DEV-2026-09-15-041](DEV-2026-09-15-041-camoufox-window-size.md) | [R4B](../work-items/R4B-2026-09-14-target-client-migration.md) | Mac 实机反馈 r7 窗口偏小；r8 正常桌面仍有边框；r9 固定 16:9 画面在 Trilium 视区留边 | r9 窗口/去边框桌面层与 fill-r10 全视区客户端、Linux 坐标/截图/文件/断线通过；Mac QA 与生产均确认铺满、点击和图片预览，窄视区字体非等比拉伸作为固定分辨率取舍保留 | 已解决（已部署/实机通过） |
| [DEV-2026-09-15-040](DEV-2026-09-15-040-migration-controller-capabilities.md) | [R4B](../work-items/R4B-2026-09-14-target-client-migration.md) | r7 迁移准备未核对旧控制器能力，实际切换后失败代次为 unknown，文档未同步 | 准备/启动能力拒绝、原生命周期清理、生产保护、最终组合切换与服务器端复核通过 | 已解决（已部署） |
| [DEV-2026-09-15-039](DEV-2026-09-15-039-legacy-wayland-backup-socket.md) | [R2B](../work-items/R2B-2026-09-15-legacy-browser-recovery.md) | 停止后的旧 Wayland socket 使 Home 加密备份失败 | 精确排除已识别运行时 socket，保留源和其余类型拒绝；115 项回归及真实旧浏览器恢复通过 | 已解决（代码/QA） |
| [DEV-2026-09-15-038](DEV-2026-09-15-038-coherence-backup-assets.md) | [R5E](../work-items/R5E-2026-09-15-release-combination.md) | 加密控制状态未收集 coherence 策略引用的资产目录，既有恢复 QA 未覆盖此组合 | 补完整资产/引用校验，101 项回归及实际 r7 新根浏览器恢复通过 | 已解决（代码/QA，未部署） |
| [DEV-2026-09-15-037](DEV-2026-09-15-037-legacy-encrypted-backup.md) | [R2A](../work-items/R2A-2026-09-15-legacy-backup-preparation.md) | 加密备份强制 Store/冻结产物，旧生产不具备；旧 journal/公钥权限兼容与明文备份说明不符 | 独立旧格式、实际运行快照、80 项测试及生产只读前置检查通过；保持新格式保护并修正文档 | 已解决（工具/只读准备） |
| [DEV-2026-09-15-036](DEV-2026-09-15-036-client-host-network-change.md) | [R5D](../work-items/R5D-2026-09-14-entry-authentication.md) | QA Chromium 共用宿主网络，创建代次网络触发请求取消 | 独立网络命名空间与校验对端 UID 的专属 Unix socket 转发；保留 TLS/授权验收 | 已解决（隔离 QA） |
| [DEV-2026-09-14-035](DEV-2026-09-14-035-handoff-backend-capability.md) | [R5D](../work-items/R5D-2026-09-14-entry-authentication.md) | ticket 兑换仍重定向到后端能力 URL，重复交接撤销原显示 | 网关内存持有能力、私有头认证、干净跳转及同登录复用 | 已解决（代码/QA，未部署） |
| [DEV-2026-09-14-034](DEV-2026-09-14-034-private-tls-qa-certificate.md) | [R5D](../work-items/R5D-2026-09-14-entry-authentication.md) | QA 私有上游证书缺少配置服务名称，严格 TLS 拒绝连接 | 生成精确 SAN 的隔离证书，补准备/发布校验，保留严格验证 | 已解决（代码/QA，未部署） |
| [DEV-2026-09-14-033](DEV-2026-09-14-033-worker-display-secrets.md) | [R5D](../work-items/R5D-2026-09-14-entry-authentication.md) | Worker 显示密码及协作 token 进入 Docker 环境 | 保留认证，改专属运行材料并核对恢复、Home 和清理 | 已解决（代码/QA，未部署） |
| [DEV-2026-09-14-032](DEV-2026-09-14-032-entry-url-validation.md) | [R5D](../work-items/R5D-2026-09-14-entry-authentication.md) | Session URL 和 Origin 校验未覆盖完整结构与当前 Session | 收紧 URL/Origin/绑定并补一次性交接与 CSRF 验证 | 已解决（代码/QA，未部署） |
| [DEV-2026-09-14-031](DEV-2026-09-14-031-session-state-secrets.md) | [R5D](../work-items/R5D-2026-09-14-entry-authentication.md) | Session 状态包含明文访问材料，读取失败可继续空状态 | 独立私有密钥密封状态，原子迁移，错误时拒绝恢复 | 已解决（代码/QA，未部署） |
| [DEV-2026-09-14-030](DEV-2026-09-14-030-untrusted-error-logging.md) | [R5D](../work-items/R5D-2026-09-14-entry-authentication.md) | 后端/第三方错误详情经普通日志传播 | 稳定错误分类、最终输出边界和各层异常验收 | 已解决（代码/QA，未部署） |
| [DEV-2026-09-14-029](DEV-2026-09-14-029-resume-pending-readiness.md) | [R5C3](../work-items/R5C3-2026-09-14-runtime-coherence.md) | 恢复后等待一致性观测的 503 误称 Worker 仍停止，QA 未处理就绪重试 | 修正错误分类/措辞，原绑定正常重试后核对全部身份和数据 | 已解决（代码/QA，未部署） |
| [DEV-2026-09-14-028](DEV-2026-09-14-028-exit-history-after-unknown.md) | [R5C3](../work-items/R5C3-2026-09-14-runtime-coherence.md) | 离线 UNKNOWN 清除上一实际出口，恢复为另一出口后 block 错误放行 | 候选 6 原子保存历史/锁定，484 项控制与真实双 Profile 离线/轮换/新代次通过 | 已解决（候选 6 代码/QA，未部署） |
| [DEV-2026-09-14-027](DEV-2026-09-14-027-coherence-request-idempotency.md) | [R5C3](../work-items/R5C3-2026-09-14-runtime-coherence.md) | 一致性 POST 缺少调用标识，被 Go 加密客户端在本地拒绝 | 每次逻辑调用生成标识，补真实加密协议测试和固定入口验收 | 已解决（代码/隔离验收，未部署） |
| [DEV-2026-09-14-026](DEV-2026-09-14-026-intl-locale-canonicalization.md) | [R5C3](../work-items/R5C3-2026-09-14-runtime-coherence.md) | Camoufox 页面 maximize 未扩展标签，en 与 en-US 被错误判为冲突 | 固定 CLDR 依赖，在控制端规范化并与冻结 locale 比较，真实差异仍拒绝 | 已解决（代码/隔离验收，未部署） |
| [DEV-2026-09-14-025](DEV-2026-09-14-025-runtime-network-topology.md) | [R5C3](../work-items/R5C3-2026-09-14-runtime-coherence.md) | 额外网卡使 inspector 拒绝执行，但 UNKNOWN 未必暂停已能绕过的 Worker | 补逐次实际拓扑检查，已确认漂移返回 FAIL 并暂停精确实例；新候选重新验收 | 已解决（代码/隔离验收，未部署） |
| [DEV-2026-09-14-024](DEV-2026-09-14-024-coherence-renewal-scheduling.md) | [R5C3](../work-items/R5C3-2026-09-14-runtime-coherence.md) | 60 秒串行采样没有预留观测时间，正常租约也会到期关闭 | 提前 30 秒续查、每 Home 互斥及全局两个后台任务，保持 60 秒证据上限 | 已解决（代码/隔离验收，未部署） |
| [DEV-2026-09-14-023](DEV-2026-09-14-023-kernel-route-denial-evidence.md) | [R5C3](../work-items/R5C3-2026-09-14-runtime-coherence.md) | 无默认路由的请求在进入 nft 前被内核拒绝，固定丢包数量不适用 | 保留 errno 和路由证据，其余尝试仍须有规则与新增丢包证明 | 已解决（代码/隔离验收，未部署） |
| [DEV-2026-09-14-022](DEV-2026-09-14-022-hidden-observer-readiness.md) | [R5C3](../work-items/R5C3-2026-09-14-runtime-coherence.md) | 隐藏标签导航返回后仍短暂处于初始空白页 | 有界等待精确 HTTPS 来源，保留重定向拒绝和清理要求 | 已解决（代码/隔离验收，未部署） |
| [DEV-2026-09-14-021](DEV-2026-09-14-021-observer-result-filesystem.md) | [R5C3](../work-items/R5C3-2026-09-14-runtime-coherence.md) | 固定脚本在共享内存写出结果，但实际 Docker archive/cp 均不可见 | 改用按代次和角色隔离的私有结果目录，保留失败并重新验收 | 已解决（代码/隔离验收，未部署） |
| [DEV-2026-09-14-020](DEV-2026-09-14-020-health-cache-generation.md) | [R5C3](../work-items/R5C3-2026-09-14-runtime-coherence.md) | 健康缓存命中未复核当前 journal，换代后可能返回旧报告 | 修复完整绑定校验，新增严格门槛使用控制器的当前代次证据 | 已解决（代码/隔离验收，未部署） |
| [DEV-2026-09-14-019](DEV-2026-09-14-019-qa-anonymous-volumes.md) | [R5C2](../work-items/R5C2-2026-09-14-approved-dns-ttl.md) | 公开 QA 记录器删除容器时未回收镜像声明的匿名卷，部分旧挂载证据缺失 | 补 Mounts 留证和带卷删除；120 个空卷逐个清理并保存恢复清单，六个新匿名卷清理复测通过 | 已解决（范围见记录） |
| [DEV-2026-09-14-018](DEV-2026-09-14-018-transition-capture-mac.md) | [R5C2](../work-items/R5C2-2026-09-14-approved-dns-ttl.md) | Docker 重启改变 MAC，网桥工具初始 MAC 的 IPv6 过滤不能覆盖整个恢复窗口 | 四项实际帧检查及同一冻结代次补验通过，旧 PARTIAL 保留 | 已解决（范围见记录） |
| [DEV-2026-09-14-017](DEV-2026-09-14-017-public-recursive-delegation-scope.md) | [R5C2](../work-items/R5C2-2026-09-14-approved-dns-ttl.md) | QA 精确递归白名单遗漏采样所需的区外 NS 主机名 | 27 项服务检查、外部复测及第五轮完整公开采样通过，第四轮失败保留 | 已解决（范围见记录） |
| [DEV-2026-09-14-016](DEV-2026-09-14-016-public-recursive-cache-samples.md) | [R5C2](../work-items/R5C2-2026-09-14-approved-dns-ttl.md) | 公共递归前端有多个缓存期限，单次回答不能代表整个前端 | 多样本工具 50 项通过；标准 Unbound 第五轮按原期限规则通过，公共前端限制保留 | 已解决（范围见记录） |
| [DEV-2026-09-14-015](DEV-2026-09-14-015-public-browser-observation.md) | [R5C2](../work-items/R5C2-2026-09-14-approved-dns-ttl.md) | 公开 QA 导航立即读取剪贴板、假定 Worker 有 scrot | 有界等待 UTF-8 结果，使用镜像已有 xwd；两个实际浏览器四协议与截图通过 | 已解决（工具/实际 QA） |
| [DEV-2026-09-14-014](DEV-2026-09-14-014-public-dns-evidence-validation.md) | [R5C2](../work-items/R5C2-2026-09-14-approved-dns-ttl.md) | 公开 DNS verify 可在委派/权威/wire 缺失、缓存 TTL 不递减时把子结果写为 PASS | 证据版本 2、wire/端点/阶段/来源与 TTL 时间复核；36 项工具检查和四组前后对照通过 | 已解决（工具/隔离验证，非公开验收） |
| [DEV-2026-09-14-013](DEV-2026-09-14-013-qa-tls-accept-blocking.md) | [R5C2](../work-items/R5C2-2026-09-14-approved-dns-ttl.md) | QA TLS 在监听 accept 中无期限握手，一个沉默客户端阻止其他 HTTPS/DoH 请求 | 线程内有界握手，2 项真实 TLS 检查、原夹具复现和最终浏览器复测通过 | 已解决（QA 工具/隔离验证） |
| [DEV-2026-09-14-012](DEV-2026-09-14-012-dns-build-toolchain.md) | [R5C2](../work-items/R5C2-2026-09-14-approved-dns-ttl.md) | DNS wheel 已固定，但首版 Runtime 用浮动 apk 包补 pip，构建可能改变系统依赖 | 固定 pip wheel；Runtime 基础包保持、散列拒绝、56 文件重现及最终候选补验通过 | 已解决（代码/QA，未部署） |
| [DEV-2026-09-13-001](DEV-2026-09-13-001-health-endpoint-path.md) | [R1](../work-items/R1-2026-09-13-runtime-health.md) | 健康查询公网路径为 `/browser/{profile}/health`，强制探测仅限本机 socket，与规格 45.5 的 `/api/v1` 草案不同 | 修订设计（规格增加当前映射） | 已解决 |
| [DEV-2026-09-13-002](DEV-2026-09-13-002-worker-auto-remove.md) | [R2](../work-items/R2-2026-09-13-boot-recovery.md) | 生产 Worker 以 Docker AutoRemove 创建，daemon/主机重启后被删除，无法按代次恢复；v2“`restart=no` 保持停止”结论只对合成 Worker 成立 | 修复实现（Profile Worker `remove=False` + 按序 resume，已随 `0.3.2-resume-v1` 上线）；旧代次需停止后新建才具备可恢复性 | 已解决（旧代次切换待用户决定） |
| [DEV-2026-09-13-003](DEV-2026-09-13-003-packet-direction.md) | [R4A](../work-items/R4A-2026-09-13-client-migration-qa.md) | AF_PACKET 将收到的 IPv6 组播也算为出站，旧记录缺少方向 | 修复内核方向采集，受控组播验证与完整网络重跑通过；保留旧失败和原 IPv6 断言 | 已解决 |
| [DEV-2026-09-13-004](DEV-2026-09-13-004-unicode-input.md) | [R4A](../work-items/R4A-2026-09-13-client-migration-qa.md) | UTF-16 拆分补充平面字符，QA 又误用 BCP 47 作为系统 locale | 修复 code point/composition 与 QA POSIX locale，完整输入和剪贴板回归通过 | 已解决（新包仅 QA，生产切换归 R4B） |
| [DEV-2026-09-14-005](DEV-2026-09-14-005-relay-handshake-timeout.md) | [R5A](../work-items/R5A-2026-09-14-proxy-protocols.md) | 上游 TCP 建连后没有 SOCKS5 握手 deadline，沉默端点可能无限等待 | 修复总握手超时、服务取消与连接等待，失败回归和 Go/race/vet 留证 | 已解决（代码/QA，未部署） |
| [DEV-2026-09-14-006](DEV-2026-09-14-006-internal-proxy-protocol.md) | [R5A](../work-items/R5A-2026-09-14-proxy-protocols.md) | 45.2 内部 HTTP CONNECT 草案与当前内部 SOCKS5 不一致 | 设计映射与六种实际协议一致，完整父条件保留 | 已解决（设计/QA，未部署） |
| [DEV-2026-09-14-007](DEV-2026-09-14-007-relay-secret-bytes.md) | [R5A](../work-items/R5A-2026-09-14-proxy-protocols.md) | Relay `TrimSpace` 静默改变凭据，读取缺少字节上限且跟随末级链接 | 修复单值文件契约并验证真实认证字节；Secret Store 仍归 R5B | 已解决（代码/QA，未部署） |
| [DEV-2026-09-14-008](DEV-2026-09-14-008-resume-storage-observation.md) | [R5A](../work-items/R5A-2026-09-14-proxy-protocols.md) | TERM 与 longrun finish 不能保证最近 localStorage 已保存 | r6 oneshot 在桌面停止前关闭浏览器；容器恢复、显式失败保留/重试与即时存储恢复通过 | 已解决（代码/QA，未部署） |
| [DEV-2026-09-14-009](DEV-2026-09-14-009-backup-key-paths.md) | [R5B](../work-items/R5B-2026-09-14-secret-store.md) | 旧备份查找错误 SSL 目录；加密草稿缺少 Adapter 独立密钥 | 修复路径并补齐必要恢复材料，缺失拒绝，实际恢复验证 | 已解决（代码/QA，未部署） |
| [DEV-2026-09-14-010](DEV-2026-09-14-010-direct-reply-filter.md) | [R5C1](../work-items/R5C1-2026-09-14-direct-isolation.md) | DIRECT 私网目标拒绝也误挡发回 Worker 的 SOCKS5 响应 | 修复回复方向规则，双 Home 实际双向流量、私网拒绝及抓包通过 | 已解决（代码/QA，未部署） |
| [DEV-2026-09-14-011](DEV-2026-09-14-011-direct-bootstrap-url.md) | [R5C1](../work-items/R5C1-2026-09-14-direct-isolation.md) | Adapter 将宿主机 bootstrap 同时用作浏览器起始 URL，DIRECT 正确拒绝后无法跳转 | 控制能力区分标记与初始 URL，两个实际入口、复用及存储恢复通过 | 已解决（代码/QA，未部署） |

已登记的偏差不表示已经完成全部代码与设计核对。计划内尚未实现的能力通常记录为工作项缺口；历史证据与现行行为差异先核对版本和适用范围。

记录只保存脱敏事实、代码/规格链接和证据路径，不包含真实网页内容、凭据、私钥或授权 URL。解决后保留原问题与证据，补充最终处理，不覆盖历史失败。

| [DEV-086 容量准入竞争](DEV-2026-10-01-086-capacity-admission-race.md) | [R6I](../work-items/R6I-2026-10-01-capacity.md) | 跨 Profile 检查/占用不原子 | 全局短准入锁、竞争回归与真实 HTTP 验证 | 已解决（未部署） |

- [DEV-089 Chromix 候选继承旧引擎入口](DEV-2026-10-01-089-chromix-inherited-entrypoint.md)：已解决，专用入口修复后真实 Worker/管理创建通过。

- [DEV-090 Chromix 包目录权限](DEV-2026-10-01-090-chromix-package-directory-mode.md)：已解决，软件目录 0755 修复后非 root 浏览器与持久化验收通过。

- [DEV-091 部署就绪检查 Host](DEV-2026-10-01-091-deployment-readiness-host.md)：已解决；首次自动回退，正式 Host 修正后部署通过。

- [DEV-092 创建表单不兼容组合](DEV-2026-10-01-092-create-template-combination.md)：已解决，R6U 两下拉联动、服务端显示派生与明确错误提示已验收部署；不追认原用户失败原因。

- [DEV-093 Chromix CJK 配置遗漏](DEV-2026-10-01-093-chromix-cjk-fontconfig.md)：已解决；生产应用 cjk-r2，用户确认中文正常。

- [DEV-094 编辑模板回显](DEV-2026-10-01-094-edit-template-selection.md)：已解决/已部署；按行级绑定选中，缺失绑定明确占位。

- [DEV-095 旧 Work 显示偏好](DEV-2026-10-01-095-legacy-display-preference.md)：旧自动分辨率支持待后续；当前页面/提交明确限制固定模板。

- [DEV-096 自动分辨率上限](DEV-2026-10-01-096-auto-resolution-limit.md)：已解决并部署；前后端同步实际尺寸，超大 Retina 画面与输入重验通过。

- [DEV-100 有数据的模板组合窄窗口布局](DEV-2026-10-01-100-template-combination-responsive.md)：已解决并部署，有数据的六组页面检查通过。

- [DEV-101 Chromix 自定义多语言](DEV-2026-10-01-101-chromix-custom-languages.md)：R6R 已解决并部署。

- [DEV-102 原生 Firefox 窗口放置](DEV-2026-10-01-102-native-firefox-window-placement.md)：R6R 已解决并部署。

- [DEV-103 生成器镜像标签复用](DEV-2026-10-01-103-generator-image-tag-reuse.md)：R6R 构建器修复已验收并部署。

- [DEV-109 冻结执行器客户端依赖](DEV-2026-10-01-109-frozen-runner-client-cache.md)：已解决，R6S完整验收并限定部署；原失败证据保留。

- [DEV-110 浏览器探针就绪](DEV-2026-10-01-110-browser-probe-readiness.md)：已解决，R6S完整验收并限定部署；原失败证据保留。

- [DEV-111 Chromix缩放画布观察](DEV-2026-10-01-111-chromix-scaling-canvas-observation.md)：已解决，R6S完整验收并限定部署；原失败证据保留。

- [DEV-115 UI跳转验收传输](DEV-2026-10-01-115-ui-redirect-fixture.md)：已解决；隔离回环HTTP服务完整提交/303/GET、前后导航验收通过。

- [DEV-116 数字输入样式](DEV-2026-10-01-116-display-number-input-style.md)：已解决；显示模板数字输入样式补齐，三宽度高度及截图复查通过。

- [DEV-121：侧栏折叠布局与键盘可达性](DEV-2026-10-02-121-workspace-sidebar-collapse.md) · R6AB已修复部署。

- [DEV-122：列表管理弹窗渐进增强与焦点](DEV-2026-10-02-122-management-list-dialog.md) · R6AC已修复部署。
