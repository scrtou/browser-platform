# R5C3 运行时网络与浏览器环境一致性验收

日期：2026-09-14。范围：固定候选、独立 QA Home/网络/控制器/Adapter、正常 Camoufox r6 浏览器和两台授权轻量端点。**状态：代码、隔离验收、版本核对、临时资源清理及文档检查已完成，R5C3 已收尾；未部署生产。**

[工作项](../../docs/work-items/R5C3-2026-09-14-runtime-coherence.md) · [运行契约](lifecycle/runtime-coherence.md) · [规格](../../docs/specs/proxy-environment/specification.md#47-proxy-environment-coherence) · [验收索引](../../docs/acceptance/README.md)

## 固定版本与输入

| 项目 | 本次版本 / SHA256 |
| --- | --- |
| 上游 commit | `2b13a42483c1dc7d367d5c340437bdc8ecd84bb4` |
| 最终候选控制器 release | `0.3.2-coherence-v1-92ac2edb24572f5c`（候选 6） |
| 保留镜像标签 | `browser-platform/sealskin:0.3.2-coherence-v1-92ac2edb24572f5c-pkg-47d9a3994f8e` |
| 控制器 image ID | `sha256:306ad32baa7de0f72dc1a49f354721b01c37bebf5fdecdeb60235a40ee4364d0` |
| checks image ID | `sha256:1d726af4be427a856d0674c8a74cf175f8d74c3d3fa06a1bea28726b704839ce` |
| 正式 patch | `98d13af50bc53add092366f4f6c42923d7ec33086bfadcc61411383d9bad96b7` |
| QA Adapter 二进制 | `31b3c57395ae054491ad7baaa14f1e2c57f40b01f3f607fb3c9cc7da58467b72` |
| Guard/Relay 镜像 | `guard-v1-8dc8ad83bab2d1a5`，`sha256:0ac7c02142fcd27e6481f2d34ef009d6782cb93cc7ff76e6fbc511f2eebb1e81` |
| US 冻结环境 | `env-us-r5c3-qa-r1`，`5154cb6a2f85a67c093016ed102ab15979e572bb8cd275d326d85205ddc56ce7` |
| 正常浏览器 image ID | `sha256:4d70427976d5885ad157de0c57f3350df4756977c450e4df9d671bbe2e8c1b69` |
| DB-IP Lite Country 2026-09 CSV | `d63208f569264ee37af0c19b9df61a1e15eeb6f54209b84dec9aa306270bd382` |
| Intl 规范化 | Babel 2.17.0 / Unicode CLDR 46；wheel `4d0b53093fdfb4b21c92b5213dba5a1b23885afa8383709427046b21c366e5f2` |

`candidate-6/version-check-3/` 在独立临时目录重放正式 patch，26 个运行文件与源码、payload manifest 和运行控制器逐一相同，20 个测试文件与固定 checks 输入一致，安装器依赖前置检查通过。54 个 Go 源文件、正在运行的 QA Adapter 和 Guard 构建输入核对通过。Adapter 完整 race/vet 见 `go-race-checks-5/`；Relay 与已通过的 `go-race-checks-3/` 输入逐一相同。完整测试为 **484 项控制端 PASS**、**63 项依赖/QA 挂载/exec/Guard PASS**、**32 项轻量端点回环 PASS**；相关 123 项聚焦测试包含在控制端总数中，不重复计数。US 环境另完成两 Home 各 10 次重建、22 份页面观测和存储/离线恢复。

IP 地区数据：[IP Geolocation by DB-IP](https://db-ip.com)，[官方 Lite 许可](https://db-ip.com/db/lite.php)，[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)。CSV 内容未修改，仅解析 IPv4 国家区间用于推断；这不是服务器物理位置证明。没有城市数据库，城市为 UNKNOWN；显示这些结果的网页须保留 DB-IP 署名链接。Babel/CLDR 随固定 wheel 保留上游许可。

## C/H 矩阵

详细证据根为被忽略的 `infra/sealskin/runtime/r5c3-coherence-2026-09-14/`。表中的候选编号明确限定版本；旧候选已通过的范围不冒充当时完整工作项通过。

| 项目 | 已取得事实 | 证据与状态 |
| --- | --- | --- |
| C01 | 实际 US DIRECT、en-US、America/New_York；新启动首次 503，观测就绪后同代次 303，8 次并发复用；仅城市未知 | 候选 6 `c01-entry-1/`、`c01-entry-2/` PASS；后者为更新 Adapter 后原代次复用，未重复执行空 Home 启动检查。候选 4 的首次 303 仅为其历史时序 |
| C02 | 实际 JP、显式要求 Asia/Tokyo；冻结和实测保持纽约，UNHEALTHY，固定入口 503，无 Location/Set-Cookie | 候选 6 `c02-entry-1/` PASS，空 Home 读/探测不创建，停止清理 PASS；候选 4 历史证据为 `c02-entry-3/` |
| C03 | 实际 JP、en-US，不声明对应时区限制；不因语言/地区不同失败，环境不变 | 候选 6 `c03-entry-1/` PASS，首次 503 后同代次 303、DEGRADED，停止清理 PASS；候选 4 历史证据为 `c03-entry-2/` |
| C04 / H03 | GeoIP 文件不可用为 UNKNOWN，同 Session token 换 Cookie 从 303 到 503 无 Cookie，再恢复 303；控制器停止后门槛真实到期关闭已有连接 | 候选 6 `geoip-unavailable-1/`、`expiry-1/` PASS；到期后约 0.681 秒关闭，原绑定恢复。候选 4 对应历史测试也通过 |
| C05 | 两个独立 Profile 共用 `188.253.118.223:18180`；分别取得 JP，离线 UNKNOWN 后实际出口变 HK。recheck 放行、block 保持 UNHEALTHY，返回 JP 仍阻断；正常停止/新代次重新允许 | **候选 6 `rotation-1/` PASS**，历史/绑定/环境及新身份核对通过，清理 PASS |
| H01 | 所有必需项及可选项均通过时聚合 HEALTHY；完整绑定和新鲜度必需 | 固定控制测试 PASS，城市为明确合成夹具；实际正常报告属于 H02，未声称实测全项 HEALTHY |
| H02 | 城市 UNKNOWN 是可选项，其他必需环境/网络项通过时 DEGRADED / allowed=true | 候选 6 US/JP 入口及 C05 PASS |
| H04 环境 | 页面值与冻结环境不符必须失败，不自动重随机；显式时区限制同样拒绝 | 页面错误为控制测试；真实 C02 见上行 |
| H04 隔离 | 给精确 QA Guard 加自身 egress 并仅放行受控 HTTPS，原生 socket 真实绕过后自动暂停 Worker；后续 UNKNOWN 不清除故障，恢复限制后正常停止 | 候选 6 `topology-fault-1/` PASS；仅规则漂移及其停止顺序引用候选 4 `rules-fault-1/` PASS，未重复计作候选 6 实测 |
| advisory | 实际 JP 配不符的国家/允许时区，仅 WARN，环境仍 en-US/纽约，正常放行 | 候选 4 `advisory-1/` PASS |

控制检查覆盖未知/过期/错误 nonce、绑定漂移、文件/门槛破坏、并发与限流、跨 Profile、等价 Intl 标签及真实语言/文字/地区差异、出口历史在四类 UNKNOWN 后保留、同代次恢复/新代次重置、历史损坏拒绝，以及每个 journal 保存点的历史/锁定一致性。

## 连续访问、恢复与入口边界

候选 6 `continuity-1/` 在 95.307 秒取得 86 次 WebSocket echo 和 4 个新 nonce；证据有效期保持 60 秒。`expiry-1/` 仅停止 QA 控制器，Worker/Guard/Relay 保持；既有连接在 57.624 秒、52 次 echo 后关闭，即门槛到期约 0.681 秒后，控制器恢复后同绑定重新允许。`resume-2/` 经正常 Adapter resume 恢复原三容器/Home/Session/operation/产物，开始时间和 nonce 更新，Home marker 保留；本轮第 1 次请求即成功。最终串行 runner 的 9 步均 PASS，见 `core-regressions-2/`。候选 4 的 95.666 秒连续访问、到期后约 0.664 秒关闭及原代次恢复作为历史证据保留。

候选 6 首轮 `resume-1/` 在等待新观测时返回 503，旧文案误称 Worker 停止；DEV-029 修正并通过正常 resume 接回原实例，原失败、旧二进制及 `core-regressions-1/` 部分结果保留。QA 工具允许有界重试，但 `resume-2/` 没有实际触发多次重试。

入口、并发复用和私有命令均通过真实 RSA/AES/JWT 客户端。公开 GET 只呈现绑定缓存，暂停 QA 控制器后 GET 仍不改 journal，私有 GET coherence 返回 405；空 Home 的读/探测不创建 Worker。公开健康移除 operation/Session，完整私有报告和能力 URL 仅留私有证据。最终用户登录、跨主体 Session 授权与全层日志脱敏仍归 R5D。

## 失败历史与修复

| 候选 | 保留的事实与处理 |
| --- | --- |
| 1 | 私有结果原放共享内存，Docker archive/cp 不可读；准备阶段阻断，DEV-021 改用角色专属目录 |
| 2 | 隐藏标签初始空白就绪时序、无路由请求未增加 nft 丢弃计数；DEV-022/023 修复时序与证据归因 |
| 3 | 424 项控制及部分实际范围通过；额外网卡真实 HTTPS 绕过未自动暂停为 CONFIRMED_GAP，Intl en/en-US 误判；DEV-025/026 修复 |
| 4 | 458 项控制及上表 C01–C04/H 范围通过；原 Adapter 的 POST 缺少调用标识导致六次 503，DEV-027 修复后保留原代次复验通过；C05 的 JP → UNKNOWN → HK 丢掉上一出口，block 错误放行，为 DEV-028 CONFIRMED_GAP |
| 5 | 483 项固定镜像测试通过；新增持久化中断测试失败，历史可先于锁定保存。未启动浏览器代次，候选和失败日志保留，基础 QA 已清理 |
| 6 | 新历史及报告/锁定原子保存，484 项控制测试、C01–C05、连续访问/到期/恢复和实际拓扑隔离回归通过；临时资源清理完成 |

DEV-020 的缓存完整绑定和 DEV-024 的提前续查也在本项修复。DEV-029 修正等待就绪时的恢复措辞及 QA 有界重试，未放宽门槛；配套新 Adapter 的控制错误分类/脱敏测试和 race/vet 通过。所有偏差见 [索引](../../docs/deviations/README.md)。候选 4 C03 首轮 KeyError 来自 QA 脚本未等待合法 BINDING_CHANGED 缓存更新，同代次重验通过；C02 过早读取或触发 429 的早期工具结果也保留。候选 6 `version-check-2/` 因主机 Python 不支持 tar 解包的 `filter` 参数而中止；显式检查目录/普通文件后，独立新目录 `version-check-3/` 完整通过。工具失败均保留，不改写为旧版本通过。

## 清理、生产保持与未覆盖范围

候选 1–6 基础 QA 已清理；候选 6 的 8 个 case 均核对无 Session、Worker 和网络占用后，才移除 QA 控制器、上游、Adapter、Docker 代理、网桥与私有 socket。证据为 `candidate-6/qa-closeout-1/`、`qa-cleanup.json` 和清理前完整容器 Mounts。QA Home 和活动凭据已移除；用于追溯的私有归档及详细证据仍含敏感副本，不宣称本地所有秘密副本已删除。

两轮远端服务都按准确 PID/start ticks 正常停止、collect、purge，共四个部署目录已移除；两台主机的五个临时端口均无监听且公网不能建立连接，见 `endpoints-1/closeout-1/`、`endpoints-2/closeout-1/` 和 `infrastructure-closeout-1/`。只移除 R5C3 的两个 DNS 标记块、10 条 A 记录，SOA serial 从 2026091415 递增到 2026091416；权威 TCP/UDP 和公共解析器的新随机名均无记录，原 ready TXT 与 Corefile 保持，见 `dns-cleanup-1/`。基础权威、用户配置的 A/NS、53、SSH 访问及防火墙规则仍保留，未宣称撤销这些基础设施。

本地两轮 bundle 的 14 份部署材料（凭据、叶证书/CA 私钥及归档）和两份本项 Python 缓存已精确删除，见 `local-material-cleanup-1/`；证书、manifest、详细私有日志与前述证据归档保留。此清理结论仅指列明的部署材料，不表示所有私有证据已脱密。

`infrastructure-closeout-1/production-after.json` 与候选 6 开始前核对，生产 `sealskin`、`profile-relay-personal`、`blissful_tesla`、`elastic_nightingale` 的 ID/image/StartedAt/PID，以及四份配置/绑定摘要全部保持；没有部署本候选或切换用户 Home。

`static-final-1/` 对 33 份 Markdown、688 个本地链接/锚点、5 个 QA Python 文件以及普通工作文件/暂存区/展开源码 diff 的核对通过。清理前从本项私有证据取 81 个实际敏感字面量及密钥片段，扫描 310 个公开工作文件，未发现泄露；检查过程不输出这些值。收尾文字更新后的复核另存 `static-final-2/`。

原始 `git diff --check` 仍返回 2：正式 patch 中的 52 个提示逐一确认都是严格等于单个空格的统一差异上下文标记。普通文件与展开源码检查为零退出，正式 patch 已在 `version-check-3/` 成功重放并与固定运行版本一致；原始提示保留，没有为消除提示改写发布字节。

能力只覆盖固定 Camoufox、IPv4 HTTPS 实测、禁用 WebRTC、阻断 IPv6，以及当前受控上游/观察服务。DNS 上游路径和真实 TTL 的范围沿用 [R5C2](approved-dns-ttl-acceptance-2026-09-14.md)，不扩充为所有公共缓存或商业上游。ICE/TURN、HTTP/3、其他浏览器、生产迁移、正式 VPS 重启、Mac/Trilium 实机和 R5D 入口鉴权均未由本报告证明。轮询不保证每次连接的物理地区或出口不变；城市 UNKNOWN 保持可见。
