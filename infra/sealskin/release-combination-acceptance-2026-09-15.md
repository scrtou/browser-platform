# R5E · r7 登录、凭据与一致性组合验收

[工作项](../../docs/work-items/R5E-2026-09-15-release-combination.md) · [一致性契约](lifecycle/runtime-coherence.md) · [加密恢复](lifecycle/secret-store.md) · [验收索引](../../docs/acceptance/README.md)

日期：2026-09-15，UTC。结论：固定 C3/r7 的组合隔离验收通过，23 项实际客户端/恢复检查、101 项备份检查通过，QA 清理与文档核对完成，工作项已收尾。只使用独立 QA Home、账号、网络及两个已授权的轻量公网端点，未部署生产。

## 版本和环境

控制器、Adapter 和 r7 Worker 复用 [R5D 候选 3](entry-authentication-acceptance-2026-09-15.md#固定版本)，Guard/Relay 复用 [R5C3 候选 6](runtime-coherence-acceptance-2026-09-14.md)。本项只修改独立备份工具及 QA 工具，不改运行 payload。

| 对象 | 固定身份 |
| --- | --- |
| 控制器 | `0.3.2-entry-auth-v1-0e2bdae7d717825a-pkg-9a7e6b5738e3`；image ID `sha256:773f8f4a5e62bb91ff0cd55d9ca9eeade722835cbdd51a5be1d48946ae459cff` |
| Adapter | SHA-256 `b6c5cf217813c024e7bbac119cf2a353bf6a934b81875f247ef658b59015000a` |
| Worker | `0.5.6-beta.30-r7-entry-a434ead635a40ccc`；image ID `sha256:4baf6233f9410477937eeb4cca40e6a046b2cbed951ec3c49206c40976987d20` |
| Guard/Relay | `guard-v1-8dc8ad83bab2d1a5`；image ID `sha256:0ac7c02142fcd27e6481f2d34ef009d6782cb93cc7ff76e6fbc511f2eebb1e81` |
| r7 完整产物 | SHA-256 `bc05e61905c4bea3f2a98a035c1267b6715cbb1b01789023cc7f2b7b41bcfdf0` |
| r7 成功报告 | SHA-256 `8f9723f313e9ad20097fb35d6e9f20ff905c5f4e699e1c2c10de883af1c6bd4a` |
| GeoIP | DB-IP Lite Country 2026-09，SHA-256 `d63208f569264ee37af0c19b9df61a1e15eeb6f54209b84dec9aa306270bd382`；国家为数据库推断，城市 UNKNOWN |

本机私有证据根为 `infra/sealskin/runtime/r5e-release-combination-2026-09-15/`。原始 HTTP/Session 响应、账号、浏览器合成数据及密钥不随公开仓库分发。源环境为 `candidate-1/qa`，与已清理的 R5D QA 不同。客户端使用隔离网络命名空间中的 Chromium、私有 Unix 转发及两个真实 HTTPS origin；最多同时两个正常 r7 浏览器。

`artifact-check-1/result.json` 和恢复后的 `artifact-check-2/result.json` 均核对 32 个实际控制器文件、5 个构建输入、50 个 Go 输入、四个二进制及运行中的 Adapter、Worker/Relay 输入、镜像 ID 和三个资产摘要。既有 534 项控制测试与 Go race/vet 按 R5D 的相同版本引用，不计作本项重新运行。

## 实际组合矩阵

| 场景 | 结果与证据 |
| --- | --- |
| 入口、主体隔离与只读行为 | `base-4/` 六项 PASS：匿名/只读/跨 Profile/CSRF 不启动；登录和真实二进制显示；同代次复用；公开健康脱敏；注销隔离；两 Home 三类存储保持 |
| C01 / C03 适用组合 | `base-4/`：实际 US DIRECT、JP 认证 SOCKS5 均允许；r7 固定 `zh-TW` / `Asia/Taipei`。语言未被国家策略误当成硬约束，城市 UNKNOWN 时正常为 DEGRADED，不宣称全项 HEALTHY |
| C02 显式约束与 advisory | `policies-1/` 三项 PASS：JP 出口下设置不匹配时区或国家分别拒绝固定入口及正确私有能力；advisory 保留告警并允许；另一个 DIRECT Profile 保持允许 |
| C04 数据源故障与控制器重启 | `faults-3/` 五项完整 PASS：GeoIP 缺失时正常登录及正确私有能力均被阻断；恢复保留原绑定/数据；密封控制器重启、tmpfs 重建及到期恢复均通过，网站隧道在实际门槛到期约 1.02 秒关闭 |
| C04 到期与同代次恢复 | `resume-1/` 两项 PASS：tmpfs 材料丢失后按序重建，原登录重新交接同一 Session，旧显示 Cookie 401；停止控制器后实际网站隧道在门槛到期约 0.60 秒关闭，恢复取得新 nonce |
| C05 真实出口变化 | `rotation-2/` 四项 PASS：两个 Store Profile 共用代理入口，保持独立绑定/历史；JP → UNKNOWN → HK 后 recheck 允许、block 锁定；回到 JP 仍阻断，正常停止后新代次恢复且两 Home 数据保持 |
| Store 撤销、禁止回退、正常重试 | `revocation-3/` 三项 PASS：Relay 约 0.74 秒退出，浏览器 WS/WSS 关闭、新页面失败，5 项原生绕过失败且 Worker 抓包无直连；关闭确认使清理 pending，取消后相同撤销操作重试完成；旧版本不能创建 Worker，新版本恢复两 Home 的三类存储 |
| S05 加密新环境恢复 | `backup-restore-1/`、`recovered-client-1/` 两项真实客户端 PASS：备份后禁用账号仍拒绝；新根中的 r7、Store、资产和三类浏览器存储恢复；`backup-tests-1/` 的 101 项新/旧格式及一致性资产测试通过，0 skipped |

C02/C03 在此固定 r7 环境验证相同规则的适用变体，没有临时改写完整产物来模拟原表中的 `America/New_York` 或 `en-US`。原规格示例、其他协议、r6 的网络漂移场景及各自版本证据仍按原报告限定；本项不声称重跑所有历史用例。

## 实现修复与失败历史

[DEV-038](../../docs/deviations/DEV-2026-09-15-038-coherence-backup-assets.md)：共享备份来源此前遗漏策略所需的 `coherence-assets/`。现收集完整目录，并在创建/解密验证时校验路径、摘要、权限、成员及大小；缺失或变化仍拒绝。101 项回归及实际新根恢复通过，偏差已解决。

准备阶段及 `base-1/2/3` 的主密钥初始化、显示参数误判、剪贴板就绪和独立客户端解析失败均保留；修正 QA 后在 `base-4/` 完整重跑。`faults-1/2` 分别停在恢复状态解析及旧显示 Cookie 预期，未将前几项 PASS 改成整轮通过。`rotation-1/` 将仅在阻断时存在的可选字段当作必填，修正读取后 `rotation-2/` 四项通过。

`revocation-1/` 在 30 秒内读到等待连接超时的旧页面；`revocation-diagnose-1/` 随后观察到实际代理错误页。QA 改为最多 90 秒等待，保留浏览器原超时和同样的错误页/抓包/清理条件。`revocation-2/` 跨暂停后遇到两个端点六小时寿命到期，在新代次预检失败，未进入撤销。`expired-endpoint-before-1/`、`expired-endpoint-after-1/` 均确认已正常退出；核对 manifest、UID、旧 PID/start ticks 后重新启动同一 QA 服务，旧进程材料保留，见 `restarted-endpoint-before-1/`、`restarted-endpoint-after-1/`。

`backup-restore-1.log` 保留首次 QA 失败：账号表经过规范化序列化后字节不同，但完整 JSON 内容相同，备份后禁用仍存在。修正结构化比较后，离线继续的第一轮又在验证前因局部变量遮蔽失败；第二轮完成新根恢复，却因 QA 将容器 HTTPS 8443 误写为 443，Adapter 保持 CONTROL_UNAVAILABLE。准备器已修正，`recovery-port-fix-1/` 核对原始端口证据并仅重建没有 Worker 的精确恢复控制器，保留证书验证。上述失败均未写成通过；最终实际结果由下述真实客户端证明。

## 加密恢复的实际范围

age v1.2.1 生成的归档 SHA-256 为 `f3330729ad413c468cc4fbdce407a0ad53d5ab680a748cc7eda392266e9cde14`。创建前正常停止两个源 QA Profile，归档只包含 A 的 Home，附控制/Adapter 身份、密封 Session 密钥、Store、账号表及全部三个一致性资产。解密验证使用私有 tmpfs，暂存已清空；缺少当前账号表的 activate 按预期拒绝。

备份后额外撤销一个测试凭据版本并禁用 Bob；退役源 QA 控制器/Adapter 后离线合并最新撤销及账号。恢复目录为 `recovered-1/qa`，Home 和控制资产从解密包复制，镜像和程序使用核对过的固定输入；没有从源 Home 重新复制数据。原上游凭据可用，额外撤销保持，Bob 登录返回 401。

`recovered-client-1/` 于 12:37 UTC 完成：Alice 经真实登录/固定入口取得新 Worker/Session/operation，Home、镜像和 Cookie/localStorage/IndexedDB 内容与备份前一致；JP 实际出口、r7 环境及新鲜报告满足必需门槛，专属显示/代理材料、私有能力和二进制显示通过。B 仅建立禁用账号所对应的空 QA 占位 Home，没有启动实例，不声称恢复了 B 的数据。最后两个 Profile 正常停止，Home 留作私有证据。

## 收尾与边界

`cleanup-1/result.json` 确认源/恢复两套代次资源为零、两套进程停止、两个基础夹具及网络移除、两个匿名卷回收、四个空 tmpfs 根移除、四个 QA 端口关闭；生产四容器身份/镜像/启动时间/PID 和五份配置/绑定摘要保持。

`external-cleanup-1/result.json` 确认两端点停止且两个远端目录删除，撤销后的失败请求 nonce 未出现在端点日志；准确删除本项五条 A 记录，SOA serial 从 2026091501 增为 2026091502，UDP/TCP 权威查询及公共递归随机名称均确认不存在。基础权威、ready TXT、Corefile、用户已有委派、SSH 与端口规则保留，没有恢复整份旧配置。

文档/代码静态检查见 `static-preclose-1/` 与 `static-final-1/`：公开文件/冻结产物敏感扫描、文档链接/锚点、JSON、18 个 Python 文件语法及实际源码 whitespace 通过，Git index 保持。整体 `git diff --check` 仍报告原版本化 patch 的 65 条合法空白上下文行；已逐条核对仅为 patch 标记，展开后的实际源码和其余 diff 均通过。私有磁盘证据、QA 合成 Home、归档/解密包及其密钥保留在忽略目录，不宣称已擦除所有本地敏感副本。

本项不覆盖生产真实 Home、真实网站账号、目标 Mac/Trilium、整机重启、linger、Debian 13 或实际入口迁移。生产仍按既有部署运行；R2/R4B 条件继续阻断相关发布。QA 恢复仅使用本项加密归档、固定镜像和当前授权，不回写生产 journal。
