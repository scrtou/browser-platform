# R6AU · 真实业务一致性备份与异机恢复验收

状态：PASS，已收尾。工作项：[R6AU](../../docs/work-items/R6AU-2026-10-02-consistent-business-backup.md)。[操作步骤](checks/consistent-business-backup.md)。本项没有发布新业务程序。

停止检查点为 **2026-10-02 19:30:56 UTC**。原三个活动浏览器经正常生命周期停止，第四个原停用浏览器保持停止；写入服务停止、Home资源归零、开放写描述符扫描为空、Adapter排他锁持有。80个显式输入根包含全部storage、完整作业spool及资产、账号/目录/密钥/Secret Store/撤销、控制配置和journal、冻结执行器/客户端、服务与Caddy状态。源内容捕获前后相同，Caddy副本另与源核对。

| 验收 | 实际结果 |
| --- | --- |
| 加密与完整恢复 | 17,539条目，文件内容3,162,715,085字节；age密文892,418,421字节。独立主机完成age认证、全部成员/摘要/权限/UID/GID/链接文本校验及恢复 |
| 数据库读回 | 16,147个普通文件再次核对；239个SQLite数据库quick_check均为ok。SQLite 3.51.1来自固定wheel，未更改系统SQLite |
| 原生排序规则 | 2个suggest.sqlite完整逐表扫描；仅声明两个Mozilla原生规则名称，比较处理器调用即失败，实际调用计数均为0。没有仿造比较器；不声明原生索引排序语义经过完整验证 |
| 状态与依赖 | journal 4个绑定均为停止时点状态；目录10条中6条删除记录保留；程序和持久挂载闭包通过。2个DIRECT内核视图记录为新主机重新提供，不从旧主机文件恢复 |
| Secret Store | 精确Controller镜像、无网络、只读挂载：2组当前授权可解密、2次错误Home授权拒绝、5条撤销均生效；不输出凭据 |
| 三份真实Home副本 | 原Camoufox、Work Firefox和Chromix镜像分别启动浏览器；本机显示认证成功、未认证拒绝，Docker network none、零公开端口、无外网路由。各自正常关闭并删除QA容器 |
| 原恢复目录保护 | 服务只运行于另复制的Home；QA后再次完整文件和数据库读回通过 |
| 生产恢复 | 原3个活动Profile全部新鲜healthy、原停用Profile仍停止且无资源。Home挂载/Worker镜像、配置/目录/账号/Secret Store、spool、runner均保持；Controller以原ID/镜像重启，服务恢复。Session按正常生命周期重新生成 |
| 工具与临时清理 | 本机/独立机各11项真实age测试及4项SQLite回归通过；修正工具独立传输并核对SHA。失败QA与成功QA的临时Home副本、显示秘密、旧验证器遗留明文压缩文件均删除，日志保留；独立机原停止容器保持 |

密文SHA-256：`6d67547bfabb725198120ae4e8e36c816f07e36431ea2c78e346bbe57cdb0560`。manifest SHA-256：`8077b39f8dc31f1dc65d0b72f8980a3c40be2852dac4721241c9bdbadf1c0c16`。

恢复点保留于独立机私有R6AU目录：`business.tar.gz.age`、独立收据、`restored/`和单独传输的解密身份；本机保留身份和收据。密文经异机完整验证后才移除本机副本。密钥与密文同在独立机的不同私有目录，不代表已经实现离机密钥托管。原始恢复目录不得作为生产目录直接启动；按操作说明审查撤销、路径和网络，并使用副本。

运行版本仍为Adapter `63d88d1e…`、Controller `sha256:33a6d2fc…`及原三个Worker镜像；详细完整摘要保存在私有元数据和`.3`版本材料。业务归档内嵌的是捕获时工具；实际恢复须使用另存的修正工具及`final-recovery-tool-manifest.json`，避免旧gzip遍历性能问题。

本轮失败及处理完整保留：[DEV-133](../../docs/deviations/DEV-2026-10-02-133-maintenance-capacity-preflight.md)容量前置、[DEV-134](../../docs/deviations/DEV-2026-10-02-134-business-backup-job-links.md)作业链接、[DEV-135](../../docs/deviations/DEV-2026-10-02-135-maintenance-controller-readiness.md)认证就绪、[DEV-136](../../docs/deviations/DEV-2026-10-02-136-backup-gzip-verification-order.md)gzip遍历、[DEV-137](../../docs/deviations/DEV-2026-10-02-137-sqlite-native-collation-readback.md)SQLite、[DEV-138](../../docs/deviations/DEV-2026-10-02-138-recovery-kernel-mount.md)内核输入和[DEV-139](../../docs/deviations/DEV-2026-10-02-139-offline-worker-security-options.md)原安全配置。初次归档未生成、两次自动恢复就绪失败和首次Chromix副本沙箱失败均未改写成通过；最终完整重试和生产核对通过。

范围限制：没有向第三方网站验证真实登录，也没有将独立机切为生产。完整Controller网络生命周期异机证据仍按R6AP/R6AS各自合成数据范围引用。Personal本轮为静态旧端点恢复，不是供应方动态热切换验收；供应方自然漂移仍未测。

私有证据根：`infra/sealskin/runtime/r6au-consistent-backup-20261002/`。关键证据为`backup-checkpoint.json`、`business-receipt.json`、`remote-recovery-result.json`、三份`remote-*-result.json`、`backup-maintenance-result.json`、`remote-cleanup-result.json`及完整失败/重试日志。后续按[1.0计划](../../docs/v1.0-delivery-plan.md)另立工作项清理用户指定测试数据；本项未删除这些业务对象。
