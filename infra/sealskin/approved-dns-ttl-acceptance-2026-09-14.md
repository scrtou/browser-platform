# 批准引导 DNS 与公开 TTL 验收

日期：2026-09-14，UTC。[工作项 R5C2](../../docs/work-items/R5C2-2026-09-14-approved-dns-ttl.md) · [配置与重现](lifecycle/bootstrap-dns.md) · [验收索引](../../docs/acceptance/README.md)

**R5C2 已完成候选代码、私有/公开 QA、清理和文档收尾；未部署生产。** 第五轮在独立标准 Unbound 和两个受控公网端点通过三路径 180 秒真实 TTL、13 个页面/52 项协议、冻结端点、两轮故障/同代次恢复及新代次解析。网络与日志逐条关联，生产四容器及四份配置/绑定保持。前三轮公共前端缓存失败、第四轮白名单失败及旧网桥 PARTIAL 保留；通过范围不代表所有公共 DNS、商业上游或项目整体发布。

## 版本与环境

| 对象 | 固定版本 / 摘要 |
| --- | --- |
| 固定上游 | SealSkin `0.3.2`，commit `2b13a42483c1dc7d367d5c340437bdc8ecd84bb4` |
| 控制 payload | `0.3.2-dns-v1-742b67ce9ba53575`，20 个应用文件 |
| Runtime 镜像 | `browser-platform/sealskin:0.3.2-dns-v1-742b67ce9ba53575-pkg-ba7da090ed8a`；`sha256:e801c2b869943d8367fc1cc8c0e78b45b2a14fbfc06ffe048689240728b16cb6` |
| Checks 镜像 | 同标签加 `-checks`；`sha256:bd8f99dbead57abc7254f23021d3abeba3de8e9c22089273895cc6b41c0f7881` |
| Patch | SHA-256 `73ceb04c08f9570fc98837f4d5ccca7e987b5fb596071ac67adc02bc75f91eaf` |
| DNS 依赖 | dnspython `2.8.0`；wheel SHA-256 `01d9bbc4a2d76bf0db7c1f729812ded6d912bd318d3b1cf81d30c0f845dbf3af` |
| 临时安装器 | pip `25.3` wheel；SHA-256 `9655943313a94722b7774661c21049070f6bbb0a1516bf02f7c8d5d9201514cd`；不安装到 Runtime 系统 |
| 公开 DNS 采样工具 | 严格单样本证据版本 2 / 显式多样本版本 3；当前 SHA-256 `39bc6998460e1630b861ad0f369ed459846f03d1f926ba7fb0c7fed444e76057`；第五轮使用原单缓存校验 |
| Guard / Relay | 保留 R5C1 `guard-v1-399a552251bb0c5a`；`sha256:a785d443bf7ede16e0f4728bbcc552a17f6340e6a3fea2d01bd839776716888a` |
| 浏览器 | 正常 Camoufox r6 冻结产物；`sha256:4d70427976d5885ad157de0c57f3350df4756977c450e4df9d671bbe2e8c1b69` |

使用全新私有 QA 控制器、`network-qa` 用户/Home、专属 Docker 网络和受控 Observer；没有迁入真实 Home。`build-final` 从固定上游应用正式 patch 得到，56 个准备文件逐字节重现。最终 Runtime 的 APK 数据库摘要、Python 版本与固定基础镜像相同，系统没有安装 pip；通过临时 pip wheel 以 `--no-index --no-deps --require-hashes` 安装 dnspython。准备文件一致性不扩大为镜像逐字节重建保证。保留历史候选镜像与前序未提交改动。

## 最终候选的私有 QA 结果

| 范围 | 结果与依据 |
| --- | --- |
| 控制端与兼容性 | 最终 Checks 镜像内全部 339 项测试通过，含 65 项新增 DNS/代次检查及原 274 项。旧策略规范化 SHA、DIRECT、Secret Store、启动日志、停止、健康与恢复回归通过；见 `control-tests-final.log` |
| 报文与故障 | 真实 UDP/TCP 单元夹具覆盖 ID/问题/class/opcode、压缩与尾随数据、CNAME 跨报文/上限/循环/分叉、完整混合地址集合、无 IPv4、同端点截断回退、总预算和超时；没有系统解析回退 |
| 构建与安装 | 缺少依赖、错误版本、正常版本的 3 项安装检查在最终 Checks 镜像通过；前两者在应用文件写入前拒绝。dnspython 和 pip 的错误 wheel 散列均在 Docker 构建前拒绝；Runtime 与 Checks 含同一固定依赖。五份策略示例通过最终 Runtime 模型校验 |
| 批准解析器 | 实际 QA 控制器在错误 hosts 映射下，通过指定私有数值 DNS 完成 CNAME 和 UDP/TCP 查询，记录完整回答及 3 秒 TTL；正常 HTTPS 上游仍验证原主机名 |
| 受控网站路径 | 正常 r6 浏览器 HTTP/HTTPS/WS/WSS 通过；同轮 13 项浏览器网络/故障检查通过，包含直接 DNS/网络绕过阻断。网站域名交受控上游解析，不混入引导 DNS 记录 |
| 活动代次与 Relay | 夹具已改变回答且旧 TTL 到期后，原代次和 Relay 重启继续使用冻结端点；网站连接通过，没有新的引导 DNS 查询 |
| 控制器替换 | 重建独立 QA 控制器后，原 Worker/Relay/Guard 和浏览器进程保持，按冻结地址重接，DNS 记录未改变，没有重新解析 |
| 同代次恢复 | 引导解析器丢包时，正常停止/恢复仍使用原端点。上游离线预检阻止 Worker，恢复条件后按原资源/代次启动并恢复 localStorage；DNS 记录不漂移 |
| 新代次及失败保留 | 新代次取得改变后的端点，端点不可达则没有 Worker。SERVFAIL、NXDOMAIN、超时、错误 ID、混合 loopback 回答均留下占用/启动日志，未分配网络容器或 Worker |
| 数值上游 | 批准解析器不可用时，数值 SOCKS5 上游不查询 DNS，正常浏览器协议检查通过；TTL 与解析器观测为 null |
| DIRECT 回归 | 最终 Runtime 的 7 项核心检查通过：双浏览器 HTTP/HTTPS/WS/WSS、错误 hosts 与私网重绑定、解析器故障、网页 DoH 及 UDP 旁路阻断、控制器地址证据丢失/替换、同代次 Cookie/localStorage/IndexedDB 恢复、清理中断重试；覆盖 `transports`、`dns_faults`、`recovery`、`cleanup_retry` |
| QA TLS 服务 | 2 项真实 TLS 并发/超时检查通过；沉默连接不再阻塞其他请求，原 Observer 复现中的第二个 TLS 握手由 1 秒超时变为约 4 ms 成功。最终浏览器 DoH 及引导 DNS 检查通过，见 DEV-013 |

最终依据为 `bootstrap-final/results.json` 的完整一轮 11 项，以及 `direct-regression-final/results.json` 的 7 项，均为上表最终 Runtime 镜像。同轮代理浏览器的 13 项网络/故障结果在 `bootstrap-final/approved-path/browser-network/browser-network-results.json`，属于引导检查的配套证据，不与 11 项重复累加。清理前再次核对实际 QA 控制容器内全部 20 个应用文件与最终 manifest 一致。R5A 六组协议矩阵及 R5C1 的其他场景仍引用各自原报告，本轮回归不改写其历史版本结论。

## 私有 QA 失败历史与范围

首次夹具通过主机私有 bridge 发布 53 端口，从 QA 控制器访问超时；控制器正确保留占用且没有 Worker。夹具改为同一 QA 网络的显式固定数值地址，不再发布主机 DNS 端口。第二轮完整浏览器故障测试重启 QA API 后，检查器未重新握手，后续只读请求失败；补充握手后继续。

第三轮恢复 API 已通过，桌面检查把地址栏文字拼接成了错误路径；截图与失败记录保留。QA 导航现在提交前读取并核对精确 URL，第四轮真实浏览器存储恢复通过。第四轮故障检查把应保留的 `launch` 日志误算为网络资源；最终按代次验证 `reservation` / `launch` 日志，并继续要求不存在网络分配和 Worker。第五轮补验了剩余六项。这些调整修正验收工具的输入/会话/资源分类，没有降低 DNS 或生命周期条件。早期组合结果保留，但最终结论取重新执行的完整一轮。

首版 `build-1` 的 payload 为 `0.3.2-dns-v1-f4f038bfad46d256`，Runtime 标签后缀为 `pkg-0739d293face`，image ID 为 `sha256:95898ec1e509e8c6c6b393900119cc88a6955c7167a47e07f6ae17053d076cb1`。其浮动 apk 安装器不符合固定构建输入要求，登记 [DEV-012](../../docs/deviations/DEV-2026-09-14-012-dns-build-toolchain.md) 并修复为固定 pip wheel；最终构建重现、基础包保持、安装检查和完整运行补验均通过。首版的 55 文件重现与运行结果仍保留在原目录，不能充当最终镜像的验收记录。

DIRECT 首轮 `direct-regression/dns_faults-1` 的 DoH 请求超时，随后定位为 Observer 在监听 `accept()` 内同步、无期限 TLS 握手，登记 [DEV-013](../../docs/deviations/DEV-2026-09-14-013-qa-tls-accept-blocking.md)。改为各请求线程内握手，最多 5 秒，之后请求空闲最多 30 秒；同场景复现、2 项真实 TLS 检查、最终引导 DNS 全轮及 DIRECT 相关回归通过。QA 控制器重建工具同时保留原有合法只读宿主机地址挂载，即使替换时暂时没有 DIRECT 代次。这些是 QA 工具修复，没有改变产品网络 ACL。

DEV-012、DEV-013 均已解决。DNS 夹具仍是私有权威响应器，没有递归缓存；其非零 TTL、到期后冻结与下一代次看到新回答只证明本地实现。

## 公开验收准备阶段（历史）

[公开 DNS 工具](checks/check-public-dns-ttl.py) 已生成并检查示例委派、独立随机测试名和轮换前后记录，确认示例占位地址在发出查询前被拒绝，未向 DNS 服务写入任何配置。后续补充的 36 项隔离工具检查及证据校验修复见下文。该阶段尚未运行真实公开 `sample` / `verify`，当时未取得正式 QA 子域及管理方式；原 `public-tool-prepare-check.json` 仍只证明当时的准备和输入拒绝行为。

该准备阶段仍要求取得同轮公开委派链、权威查询日志、批准递归来源、非零 TTL 到期前的旧缓存与到期后的新端点；分别覆盖 DIRECT 网站 DNS、代理端点引导和真实上游网站 DNS，并结合浏览器、Worker 绕过抓包、端点故障与恢复。直接 DNS 采样即使成功也只返回 `PARTIAL`，不能代替三个实际路径。

当时公开条件未满足，工作项没有收尾，也没有开始 R5C3。后续完整结果见下方第五轮公开验收。R5D、R2 维护/恢复、R4B Mac/实际迁移和原发布门槛仍保留，本报告不作为整体可发布结论。

## 私有 QA 首阶段证据与检查点

证据根目录：`infra/sealskin/runtime/r5c2-dns-ttl-2026-09-14/`，被 Git 忽略。最终材料为 `build-final/`、`build-final-images.json`、`control-tests-final.log`、`installer-tests-final.log`、`runtime-dependencies-final.json`、`dependency-hash-rejection.json`、`pip-hash-rejection.json`、`build-reproduction-final.json`、`policy-examples-final.json`、`final-installed-payload.json`、`bootstrap-final/`、`direct-regression-final/` 和 `final-live-evidence.json`。首版 `build-1/`、对应日志/镜像记录、`build-reproduction.json`、各轮 `bootstrap-live-*`、`direct-regression/` 及 Observer 修复前后材料继续保留；`public-dns-plan-example/` 仅为未实施的准备材料。Session URL、密钥及详细浏览器证据不进入公开记录。

13:52 UTC，本轮 QA 清理与生产保留核对通过：生命周期清单中的 Session、Worker、reservation 和启动日志均已清空；QA 控制器、上游、Observer、DNS 夹具、专属网络与代理/卷观察进程已清理，临时运行凭据/密钥已移除。70 个有本轮实际挂载/事件归属记录的匿名卷中，54 个经无容器引用复核后删除，16 个此前已删除；未执行全局 prune。四个生产容器的 ID、镜像、启动时间和 PID，以及四份配置/绑定 SHA 均与本轮前一致。证据为 `qa-cleanup.json`、`qa-volume-cleanup.json`、`cleanup-and-production.json` 与 `production-before.json` / `production-after.json`。

14:03 UTC 首阶段静态核对通过：74 份 Markdown、1,030 个相对链接/锚点、12 份 JSON 示例、110 个 Python 文件语法均通过；20 个应用文件与 source/payload/实际 QA 安装证据一致，5 个构建输入与最终 manifest 一致，patch 摘要和 `git diff --check` 通过。公开文件的私钥、凭据 URL 和长授权参数字面量扫描无命中；这不替代 R5D 的全层脱敏验收。结果在原 `static-checks.json`，包含当时文档摘要；后续追加核对使用独立文件，不覆盖此记录。

历史阶段记录 `checkpoint.json` 为 `PARTIAL`：本地实现、所列私有 QA、清理和阶段文档核对已完成，公开部分仍待外部条件，不能生成完整 R5C2 PASS。配置与回退顺序见 [引导 DNS 说明](lifecycle/bootstrap-dns.md#构建和回退)；禁止用旧 journal 覆盖尚未完成的操作。

## 公开工具证据校验补验

首阶段检查点之后发现并修复 [DEV-014](../../docs/deviations/DEV-2026-09-14-014-public-dns-evidence-validation.md)：缺失委派/权威/wire 或不递减的 TTL 材料可被旧 verify 接受为子结果 PASS。证据版本 2 现在复核请求/回答 wire、父区及全部配置权威、端点/问题/阶段/采样来源，并以查询时间和一秒取整误差核对 TTL 递减及到期区间；旧采样不能直接升级为通过记录。失败留证和覆盖拒绝也有检查。

36 项工具检查通过，包含完整 prepare → sample → verify、回环 UDP/TCP、材料缺失/错配、优化解释器、总预算、失败保留与禁止覆盖。四组对照材料（缺失权威、TTL 不递减、记录与 wire 不符、错误权威端点）在旧脚本均取得子结果 PASS，新脚本均拒绝；有效材料仍仅返回 PARTIAL。对照使用 48 次回环 UDP、3 次回环 TCP，DNS 内容和 TTL 时钟为合成数据，没有公网查询或真实递归缓存。

证据在 `public-tool-review/tests-final.log`、`before-after-comparison.json`、`synthetic-roundtrip/` 与各对照目录。首轮 glue 完整域名错误导致测试夹具无法序列化的失败日志 `tests-1.log`、后续 `tests-2.log` 和原缺陷复现继续保留。14:23 UTC 四个生产容器/四份摘要再次保持，见 `public-tool-review/production-preserved.json`；临时测试目录、回环监听已退出，没有创建 Docker QA 资源。本次只修改验收工具，原 Runtime/Checks、339 项控制端与实际浏览器结果继续适用。

追加静态核对通过：75 份文档、1,043 个相对链接/锚点、12 份 JSON 示例、111 个 Python 文件语法；公开敏感字面量扫描无命中，20 个应用文件及 5 个构建输入与原最终 manifest 一致，`git diff --check` 通过。独立 `public-tool-review/static-checks.json` 与 `checkpoint.json` 保存本次摘要，原阶段检查点及其证据保持不变。追加检查点仍为 PARTIAL；真实公开条件未满足，本项未收尾。

## 专用权威 DNS 准备与外部可达性（15:01 历史阶段）

用户随后接受使用 `dns-qa.azhen.de` 并在 Cloudflare 手动添加记录。此方案已落实为[固定 CoreDNS 配置、记录清单和维护提案](checks/public-dns-authority/README.md)，不再等待子域选择或管理方式答复。产品 Runtime/Checks、DNS/代次契约、DIRECT ACL 和此前验收版本保持。

| 范围 | 本阶段事实与结果 |
| --- | --- |
| 专用服务 | CoreDNS 1.13.2，`coredns/coredns@sha256:94caebb89dcfb9d2c4be45bfda34410a3e1092458fbbbc0284365c9e4c9a7818`；仅承载 QA zone，绑定 `23.19.231.152:53` TCP/UDP；无递归/转发/区域传送配置 |
| 本机检查 | 14 项 UDP/TCP SOA/NS/TXT、NODATA/NXDOMAIN、区外拒绝与 AXFR 拒绝通过；记录实际 DNS wire、AA/RA 和正确 NS/serial |
| 区域更新 | serial `2026091401 → 2026091402 → 2026091403`，两次原子文件替换均经 UDP/TCP 确认；只修改准备状态 TXT，不计入端点轮换或真实缓存 TTL |
| 父区只读准备 | 21 次查询取得父区 NS/A 与尚无子域 NS 的回答，根 → `.de` → `azhen.de` 跟踪完成；未形成 QA 子区委派证据 |
| 公网可达性 | 两个欧洲、两个北美节点的直接查询均超时，其中 UDP/TCP 各两个；保留外部原始结果。主机 INPUT 默认丢弃，`VPS-BASELINE` 没有 53 入站允许规则 |
| 维护与委派 | 两条临时规则提案通过 `nft --check`，校验前后规则保持；没有应用、持久化或重启。Cloudflare DNS only A 与子域 NS 的精确清单已准备，尚未由用户添加 |
| 端点资源 | 还需两个外部受控、真实路由的公网 IPv4，可来自一台双 IPv4 QA 服务器或两台单 IPv4 QA 服务器。DIRECT 拒绝本机原生公网地址，现有地址不能填充网站端点；没有用第三方站点或私有 `/32` 夹具代替 |
| 生产与资源 | 15:01 UTC 四个生产容器及四份配置/绑定 SHA 与准备前一致；仅保留带 R5C2 标签的权威 DNS 容器，临时读取/校验容器均退出；没有新浏览器、Home 或 Docker 网络 |

新证据位于 `public-authority-setup/`：`image.json`、`launch-command.json`、`local-checks-1.json`、`zone-reload-checks.json`、各版本区域文件、`parent-dns-before-2.json`、`parent-trace-before-2.txt`、`public-{udp,tcp}-probe-*`、`host-nft-*.json`、`firewall-proposal-check.json`、`cloudflare-records.json`、`resource-plan.json` 与 `service-and-production.json`。准备脚本的初次 DNS 超时和本地解析器路径类型错误记在 `preparation-attempts.jsonl`；后续独立查询/检查通过，没有覆盖失败历史。权威查询日志与两份旧阶段检查点继续保留。

本阶段静态核对和检查点另存该目录，结论为 PARTIAL。当时等待 DNS/53 与外部端点条件，权威服务保留；该历史结果不能记成完整 QA 清理或 R5C2 收尾。后续用户配置后的结果见下节。

## 用户配置后的公开委派与轻量原型测量

用户完成 Cloudflare A/NS 和 53 端口配置后，15:26 UTC 的 `public-delegation-check/delegation-validation.json` 为 PASS。该结论仅覆盖委派、可达性和查询日志关联，未运行 A 地址轮换、递归缓存阶段或三个浏览器路径。

| 范围 | 实际结果 |
| --- | --- |
| 公开委派 | 20 次 DNS 查询通过：两个 Cloudflare 父权威 A/NS、子权威 SOA/NS 的 UDP/TCP，以及 `1.1.1.1` / `8.8.8.8` 的递归 A/NS/TXT；根 → `.de` → `azhen.de` → `dns-qa.azhen.de` 跟踪留证 |
| 外部端口 | 欧洲/北美各两个探测，UDP/TCP 各两个，全部返回正确 SOA、AA/无 RA；协议、事务 ID 和问题与 CoreDNS 日志精确对应 |
| 递归来源 | 两个随机 `delegation-<nonce>` 名称的 NXDOMAIN 与权威日志对应，分别观察到 Cloudflare 和 Google 递归出口；仅证明本次查询实际到达 |
| 原型功能 | 独立无外网容器中的 Python 私有 Observer，10 项 HTTP/HTTPS/SOCKS、认证拒绝、区外目标拒绝、offline 关闭旧隧道/拒绝新目标及恢复检查通过 |
| 原型容量 | 8 并发、80 次负载请求约 2.69 秒；服务 VmHWM 23,052 KiB（约 22.51 MiB），容器含客户端峰值 41,123,840 bytes（约 39.22 MiB）；128 MiB、0.25 CPU、64 PIDs 限额下无 OOM |
| 清理与生产 | 15:27 UTC 测量容器、两份准确归属的匿名卷、临时叶证书私钥和代理凭据已清理；生产四容器/四配置绑定摘要保持，仅留专用权威 DNS |

外部探测标识为 UDP `2iZbPZysiwEdhFFmK000218PG`、TCP `2FBVyakw98GjOKvoj000218PG`。详细材料位于独立 `public-delegation-check/`：`delegation-queries.json`、`delegation-trace.txt`、`authority-log.txt`、`delegation-validation.json`、`public-*-probe-*`、`footprint/fixture/measurement.json` 和 `cleanup-and-production.json`。历史外部超时、区域版本及旧检查点均保留。助手没有修改 Cloudflare 或主机防火墙，不再重复应用已无必要的提案。

容量测量没有启动 SealSkin、Adapter 或浏览器，只用于估算外部临时服务需求。原 Observer 固定私有 zone 和本机 DNS，不能直接公开部署；该结果不证明新公开端点程序已经实现或达到相同容量。

历史 SSH 准备阶段：用户随后提供两个外部公网 IPv4、`temptest` 用户和 65522 端口。15:35 UTC 只读 SSH 连接均到达服务，但公钥认证失败。测试专用公钥已交用户添加，私钥仅保留在被忽略的 `public-endpoints-setup/ssh/`。正在同一 R5C2 范围内准备独立轻量端点与验证；远端系统/资源尚未读取，服务未部署。真实缓存/TTL、浏览器三路径和故障恢复仍必须完成，R5C3/R5D 尚未开始。

## 第五轮公开验收

用户添加公钥、开放临时端口后，两台远端以普通用户运行独立 Python 轻量网站/受限代理，没有部署 SealSkin、Adapter 或浏览器。端点固定脚本 SHA-256 为 `933ccc5fb747e2544470953de460fab896e66498748fe5dd864223147908bf76`；29 项回环协议/拒绝/恢复检查通过，远端第五轮峰值分别 34,588 KiB（约 33.78 MiB）、33,612 KiB（约 32.82 MiB）。端点来源、认证、目标名称/地址/端口均受限，没有开放任意代理。

前三轮使用公共前端 `1.1.1.1`，实际存在多个缓存期限或未命中；没有通过放宽一秒取整或删除异常样本来获得 PASS。最终使用标准 Unbound 1.17.1，在独立 QA 设施中实际访问公网根、父区和公开权威，无 hosts、stub/forward zone、prefetch、serve-expired 或合成 TTL。固定依赖见 [递归锁](checks/public-dns-authority/recursive-dependencies.json)。公开 dispatcher 只批准三个测试 A 名和必要的精确 NS A/RD 依赖，其余子区问题交权威，区外和 AXFR/IXFR/ANY 拒绝；绑定后永久降权且 capabilities 清空。27 项实际检查和两台外部机器各 12 项复测通过。

第五轮 run ID 为 `cca287af01a4431a`，计划 SHA-256 为 `11a721dcc7a95a8cd2933226012b35c416e1cb784e8d40e01294af7a1b89b9c2`，批准解析器为 `r5c2-controlled-recursive`。三条随机 A 记录 TTL 为 180 秒，权威 serial `2026091411 → 2026091412`。计划内容、采样 wire、发布和实际浏览器/代次结果均独立留证。

| 要求 | 实际结果与证据 |
| --- | --- |
| 公开委派与权威来源 | 根 → `.de` → `azhen.de` → QA 子区完整跟踪；Unbound 的 10 次实际缓存未命中与 dispatcher wire、CoreDNS 查询 ID/名称对应。Unbound 的有效日志在 `r5c2-public-dns-recursive-stderr.log`，不是空的 stdout 文件 |
| 三路径缓存和 TTL | DIRECT 网站、控制器引导、外部上游网站三路径的 before/cached/expired 全部按原一秒取整规则通过；cached 为权威新地址/递归旧地址和可匹配剩余 TTL，expired 为真实期限后新地址 |
| DIRECT 实际 DNS | 从实际 Relay 命名空间记录 66 次查询，逐条匹配批准入口请求/回答；没有用采样进程代替浏览器路径 |
| 外部代理网站 DNS | 180 次解析与实际目标连接逐条对应，before 端点 153、after 端点 27；远端时钟偏移用本地 SSH 请求区间约束，after 机器快约 21–24 秒，没有修改服务器时钟 |
| 引导与代次冻结 | 控制器实际仅两次引导查询：原代次和正常停止后的新代次。TTL 到期、Relay 重启和两次同代次恢复均不重新解析，allocation/DNS 记录保持；新代次取得 after 地址 |
| 正常浏览器 | 13 个真实 Camoufox 页面/52 项 HTTP、HTTPS、WS、WSS 通过；页面 nonce、端点日志和代次互相对应 |
| 旧端点故障与恢复 | 两轮故障中已有 WS/WSS 关闭，新页面出现真实 “Unable to connect”，DIRECT 控制路径正常；两次离线 resume 为 503 且 Worker 未启动；在线后原 Worker、allocation 和 DNS 记录恢复 |
| Worker 绕过 | 100 次直接 DNS、IP/协议等绕过尝试全部阻断；相应随机名称没有到达权威 |
| 出站包关联 | 16 个命名空间窗口/612 条流量，2 个有效跨重启网桥窗口/72 条流量，所检查窗口均无禁止出站；网桥中同代次补测 46 条、新代次 26 条 |
| 固定候选与生产 | 使用上表最终 Runtime、Guard/Relay 与 r6；生产四容器 ID/镜像/启动时间/PID 及四份配置/绑定 SHA 保持，没有部署候选或操作真实 Home |

完整交叉核对位于 `public-browser-5/correlation-2/result.json` 和 `browser-correlations.json`，由 `public-browser-5/verify-correlations.py` 复核；103 份引用证据在清理后 SHA 保持。单独 DNS `verification.json` 仍按工具契约返回 PARTIAL；完整公开 PASS 来自这些实际路径的关联，资源清理和文档收尾另见下节。

| 历史轮次 | 保留的结论 |
| --- | --- |
| 1 · `66de6b1a05db451f` | 公共递归 cached 阶段出现新地址，失败 |
| 2 · `a046b51ebe654735` | 浏览器三阶段通过，严格单样本期限不匹配，整轮失败 |
| 3 · `070a5d490b484ca6` | 32 样本 cached 中出现新地址，整轮失败 |
| 4 · `dcafb8ed637e400e` | 独立递归入口遗漏 NS 主机名依赖，before 委派检查失败 |
| 5 · `cca287af01a4431a` | 完整公开关联通过；旧网桥过滤依赖初始 MAC 的记录保留为 PARTIAL，同一冻结代次完整补测通过 |

[DEV-015](../../docs/deviations/DEV-2026-09-14-015-public-browser-observation.md) 修复 UTF-8 观测时序/XWD；[DEV-016](../../docs/deviations/DEV-2026-09-14-016-public-recursive-cache-samples.md) 保留公共缓存失败并加入 50 项多样本工具检查；[DEV-017](../../docs/deviations/DEV-2026-09-14-017-public-recursive-delegation-scope.md) 补精确 NS 依赖；[DEV-018](../../docs/deviations/DEV-2026-09-14-018-transition-capture-mac.md) 以独占 QA 网桥和内核方向记录全部 IPv4/IPv6，不把 Docker MAC 变化误判成端点漂移。原 `resume-1/failure.json` 与前三/四轮失败均未改写。

本轮公开浏览器代理路径使用认证 SOCKS5；HTTP/HTTPS 代理等其他协议引用 R5A 和端点隔离检查，没有声称此次全部公网重跑。控制器替换、解析器故障下的恢复和存储恢复等仍引用前述私有 11 项检查。关闭 WebRTC 的既有范围不代表启用 ICE/TURN，UDP443 拒绝也不代表 HTTP/3 可用。完整运行时环境/地区/DNS/WebRTC 报告归 R5C3，入口鉴权归 R5D，生产恢复与目标客户端条件归 R2/R4B。

## 清理恢复与最终收尾

所有五轮外部端点均正常停止并收集日志/metrics，十个远端部署目录经 UID、manifest、argv/PID/start ticks 核对后移除；本地 35 份代理凭据、叶证书/CA 私钥和含密钥归档已删除。私有详细日志、公开证书、manifest 和失败证据保留，SSH 测试访问暂留后续工作，不能把“测试服务已移除”写成已撤销 SSH。

五轮浏览器 QA 已通过正常生命周期清空，控制器/上游、抓包容器和专网已清理。七个临时递归/dispatcher/后端容器及递归专网移除；原 `r5c2-public-dns-authority` 容器恢复，Corefile 保持，删除五轮 15 条 A 记录，serial 增至 `2026091413`。恢复后本机 12 项与外部 24 项 UDP/TCP、SOA/NS/TXT、NXDOMAIN、区外/AXFR 拒绝检查通过。

资源审计另发现旧记录器删除容器时遗漏匿名卷，见 [DEV-019](../../docs/deviations/DEV-2026-09-14-019-qa-anonymous-volumes.md)。本次时段的 120 个卷经两次只读挂载确认为空且无容器引用，保存按原名称/驱动/标签/选项重建空卷的清单后逐个删除；10 个另有精确旧挂载/事件，110 个的旧映射无法从已滚动的 Docker 事件恢复，这一缺口未伪造为已取得。362 个此前已有卷保持，没有全局 prune。工具已补完整 Mounts 留证及准确 ID 的 `rm -v`；实际网桥清理复测确认六个新匿名卷随三个测试容器消失。

清理证据为 `public-browser-*/qa-cleanup.json`、`public-endpoints-setup/round-*-purge-*/`、`local-sensitive-material-cleanup.json`、`external-restoration-checks-1/`、`controlled-recursive-setup/cleanup-1/`、`public-volume-cleanup-1.json` 和 `bridge-wire-cleanup-checks-3/`。第五轮清理包装器曾重复创建已存在的结果文件而报错，实际清理成功，说明另存 `qa-cleanup-wrapper-note.json`；未为修饰日志重跑清理。

基础 QA 权威/委派、专用 SSH 访问及用户开放的 53/临时端点规则明确保留给后续 R5C3 验证；没有正在运行的外部网站或代理。助手没有修改用户 INPUT/云安全组规则或 Cloudflare。所有验证结束后按实际归属处理这些保留项，不用旧防火墙快照覆盖用户改动。

最终静态检查包括文档相对链接/锚点、JSON 示例、Python 语法、公开敏感字面量、固定构建/安装证据和 `git diff --check`，结果另存 `closeout-static-checks.json`。最终生产身份/配置核对为 `public-final-production.json`。`closeout.json` 标为本工作项范围 PASS，历史 PARTIAL 检查点保持；R5C3 可以按计划启动，R5 及项目整体尚未通过发布验收。
