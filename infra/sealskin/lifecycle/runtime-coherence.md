# 运行时一致性与会话放行

状态：R5C3 候选 6 的代码、隔离验收及临时资源清理通过，历史保留/原子更新和恢复提示问题已修复；未部署生产。结果与明确版本范围见 [验收报告](../runtime-coherence-acceptance-2026-09-14.md)，工作项见 [R5C3](../../../docs/work-items/R5C3-2026-09-14-runtime-coherence.md)，要求见 [规格 47/49](../../../docs/specs/proxy-environment/specification.md#47-proxy-environment-coherence)。

控制器是观测和网络门槛的唯一所有者。可选 `coherence` 策略绑定到不可变网络修订；省略时不加入旧策略快照，旧 SHA 保持。`advisory` 把地区/允许时区差异作为告警，`strict` 将明确约束的差异判为失败；真实环境应用和网络隔离仍是必需项。严格模式至少声明一个国家或时区约束。两种模式都不修改环境或切换上游。

每次采样使用新的 nonce 和受控 HTTPS 名称，实际浏览器在隐藏标签页中加载固定的观测页面；whoami 只返回 socket 源 IP、nonce 和服务器时间。控制器分别保存冻结期望、页面实测、网络策略/拒绝探测和有来源的 GeoIP 推断。城市数据库缺失是可选 UNKNOWN；国家推断也不能当作物理位置证明。GeoIP 文件有来源、版本、SHA 和更新期限，不从代理名称推导地区。

正常 Camoufox 的 Marionette 只监听 `127.0.0.1:2828`，控制器通过 Docker exec 调用固定的有界脚本。仅启用此策略的 Worker 设置 `MOZ_MARIONETTE` 与 `MOZ_REMOTE_ALLOW_SYSTEM_ACCESS`；后者用于直接建立并隐藏独立标签页，避免引擎 NewWindow 的临时前台切换。不开网络调试端口，不操作用户键鼠/剪贴板，不读取用户页面。控制命令只进入自己创建的标签页，关闭它并释放会话；对话框保持，错误/超时为 UNKNOWN。原窗口和焦点的实际实验见被忽略的 `runtime/r5c3-coherence-2026-09-14/browser-channel-6/`，早期失败保留。

结果通道使用每代次/角色独立的私有目录，精确挂载到 `/run/browser-platform-observation`；固定脚本原子写入 `result.json`，控制器检查 regular file、0600、单链接、256 KiB 上限与本次 nonce。Guard/Relay 先以所需权限读取 nft，再以配置 UID 写结果。第一版将结果放在 `/dev/shm` 的方案因实际 Docker archive 不可见而失败，见 [DEV-021](../../../docs/deviations/DEV-2026-09-14-021-observer-result-filesystem.md)；不得把该次准备失败写成通过。

隐藏标签仅在精确 HTTPS URL 就绪后读取结果，初始空白页有界等待，其他来源拒绝。拒绝探测区分本地无路由与 nft 丢弃：明确默认路由缺失且公网尝试返回 `ENETUNREACH` 是内核拒绝；其余尝试须有当前 nft 规则和新增丢包证据，仅 UDP 无响应不算通过。实际时序和证据归因修复见 [DEV-022](../../../docs/deviations/DEV-2026-09-14-022-hidden-observer-readiness.md)、[DEV-023](../../../docs/deviations/DEV-2026-09-14-023-kernel-route-denial-evidence.md)。

Relay 只读挂载代次门槛目录。初始、过期、绑定改变、观测失败或已证实泄漏时只允许受控观测域名和端口，正常网站连接拒绝；关闭门槛时同时终止已有网站隧道。放行文件包含代次摘要、单调递增序号和最多 60 秒有效期，采用原子替换。Relay 重启后不接受启动前遗留的放行序号；新结果须绑定 Worker、Relay、Guard 的 ID/启动时间、Home/Profile/operation、策略与环境产物。控制器故障后没有持续续租，门槛自动到期，Home 和占用保持。

运行中每轮观测还须核对实际网络拓扑；已确认 Guard 多接网卡、网络 ID/地址或隔离属性漂移时，关闭门槛并暂停精确 Worker。仅因 inspector 拒绝执行而返回 UNKNOWN 不足以证明泄漏已经阻断；候选 3 的原始缺口与候选 4 修复实测见 [DEV-025](../../../docs/deviations/DEV-2026-09-14-025-runtime-network-topology.md)。

`on_exit_change=recheck` 在发现实际出口变化时重新判定；`block` 将当前代次保持阻断，需停止后启动新代次。上一实际出口须独立保留在代次 journal，包含时间、nonce、来源及稳定运行绑定摘要；UNKNOWN 和同一代次的容器恢复不能清除该比较基线。它只用于变化比较，不能续用为新鲜通过证据；新代次从空历史开始，历史损坏或归属不符保持 UNKNOWN。候选 4 的真实离线后轮换缺口及后续固定候选修复见 [DEV-028](../../../docs/deviations/DEV-2026-09-14-028-exit-history-after-unknown.md)。

后台每 30 秒开始续查，全局最多两个任务；报告仍从开始采样计最多 60 秒，过期期间严格阻断，慢采样不能续用旧证据。这不是逐连接的地区保证。公开 GET 仅呈现当前绑定缓存，内部明确操作/采样负责探测，每 Profile 同时一个任务且最短 10 秒。启动、复用、恢复和响应丢失后的认领均核对控制器门槛，未知结果不能发放可用 Session。调度修复见 [DEV-024](../../../docs/deviations/DEV-2026-09-14-024-coherence-renewal-scheduling.md)。

验证和清理全部使用独立 QA。首次版本只声明固定 Camoufox 环境、IPv4 HTTPS 页面观测、禁用 WebRTC 和阻断 IPv6 的能力；启用 ICE/TURN、HTTP/3、其他浏览器和生产迁移继续按各自计划验收。实际结果与未测范围由 R5C3 工作项及验收记录限定，不以本契约代替实际测试。

页面原始 Intl locale 使用控制端固定 Babel 2.17.0 / Unicode CLDR 46 的 likely-subtags 规范化，与冻结 locale 比较。页面的 normalized 字段不作为通过依据；显式语言、文字、地区或变体差异保持 FAIL，不支持的扩展保持 UNKNOWN，见 [DEV-026](../../../docs/deviations/DEV-2026-09-14-026-intl-locale-canonicalization.md)。

QA 国家推断使用 DB-IP Lite Country 2026-09：[IP Geolocation by DB-IP](https://db-ip.com)，数据按 [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) 提供，[官方许可与下载](https://db-ip.com/db/lite.php)。数据文件只放私有运行目录，报告保留来源、版本和摘要；显示或使用该结果的网页须保留指向 DB-IP 的署名链接。Lite 数据精度有限，国家为数据库推断，城市不提供。Babel 及其随包 CLDR 数据保留上游许可证，wheel 按依赖锁固定并离线校验。


## 配置、报告与兼容

`coherence` 位于不可变 `NetworkPolicy`，使用 snake_case 字段。`mode`、`observer_domain`、`observer_ipv4`、环境和成功验收文件及各自 SHA 必填；`observer_port` 默认 443，`on_exit_change` 默认 recheck。`allowed_countries` 使用大写两字母国家代码，`allowed_timezones` 使用可用 IANA 名称。`strict` 不能同时省略两项约束。`probe_url` 必须为该受控 HTTPS origin 的 `/health`，没有查询、fragment 或 userinfo。

环境、成功报告和 GeoIP 文件只从控制器私有 `coherence-assets/` 读取，目录 0700、普通单链接文件 0600，拒绝符号链接、超限或摘要变化。成功报告必须覆盖 unit、11 类启动拒绝、两 Home 各至少 10 次重建、稳定观测和离线恢复。GeoIP 同时固定 `geoip_file/sha256/source/version/published_at`，`geoip_max_age_days` 默认 62、最多 93；过期、缺失或校验失败为 UNKNOWN。

报告包含 `expected`、`observed`、`exit`、`network_evidence`、`locale_evidence`、分项 `checks`、完整 `binding`、`nonce`、`checked_at/expires_at`、`gate_sequence` 和保留的故障标志。环境分项涵盖 UA、平台、CPU、语言/Intl/时区、screen/DPR、WebGL、字体、Canvas、Audio、voices、WebRTC；网络分项涵盖拓扑/规则、DNS、IPv6、直接绕过和实际出口。数据库城市缺失是可选 UNKNOWN，正常实际结果因此为 DEGRADED，仍可满足必需项门槛。

代次 journal 的 `coherence_exit_history` 单独保存比较历史及稳定绑定摘要，排除容器开始时间但保留其 ID、Session/operation、Profile、Home、策略和环境修订。新历史与对应报告及阻断标志在同一次原子 journal 更新中保存。当前出口有效时，`exit.previous_observation.kind=historical_comparison` 显示前一实际出口的时间/来源/nonce；当前出口缺失时 `exit` 仍为空。历史不能延长门槛或清除故障。它不包含原始 Session/operation；公开报告另移除完整 binding 中的这两个字段。

Relay 镜像需声明 `io.browser-platform.coherence-gate=1`，控制清单使用 `coherence_runtime_version=1`。已启用策略不得通过旧能力或不完整报告降级放行。省略 coherence 的旧策略及其规范化 SHA 保持；新策略、控制器/Relay 和浏览器产物必须成套固定。退出、重建与回退先使用支持本版字段的控制器清空相关代次，保留 Home、最新 journal 和旧镜像；不恢复旧 journal 来解除占用。

加密恢复还须包含策略引用的 `coherence-assets/`。R5E 已修复此前共享备份收集器的目录遗漏，并增加路径/摘要/权限/成员验证（[DEV-038](../../../docs/deviations/DEV-2026-09-15-038-coherence-backup-assets.md)）；[R5E](../release-combination-acceptance-2026-09-15.md) 已完成 r7 登录、Store、一致性和加密新根恢复的适用组合验收，未部署生产。历史 R5B/R5D 的分项证据仍保持原有范围。

## 运维与验证

```bash
./profile-adapter -config /private/adapter.json -health-profile PROFILE
./profile-adapter -config /private/adapter.json -coherence-profile PROFILE
```

第一条只读运行中 Adapter 的健康缓存；第二条通过 0600 Unix socket 显式采样现有、精确绑定的代次。`-probe-profile` 强制刷新传统运行健康，仍受 10 秒限流；不代替 `-coherence-profile` 的真实浏览器采样。空 Home 的读取或探测不会创建 Worker；公开 `/browser/{profile}/health` 只读缓存，启动和“继续进入”仍必须通过当前控制器门槛。缓存绑定变化返回 UNKNOWN，等待后台采样或使用明确的内部重查，不能改写绑定来配合旧报告。

按序恢复可能先恢复容器、再等待真实页面就绪；首次 503 不代表 Worker 一定仍停止。保持原绑定，按 10 秒间隔重试正常 resume 或读取健康报告，最终成功仍须当前代次门槛通过，见 [DEV-029](../../../docs/deviations/DEV-2026-09-14-029-resume-pending-readiness.md)。

观测或数据库临时不可用时保留占用、阻断网站出站；恢复数据源后重新采样即可。`exit_change_blocked` 要求正常停止后新建代次。已确认拓扑/规则/绕过故障时，先在 Worker 保持 paused 的情况下恢复网络限制，再正常停止；正常停止会为浏览器退出而 unpause，不能在已知绕过仍存在时直接调用 stop。暂停未确认保持 UNHEALTHY，需处置精确资源，不可清除 journal 或以整机重启代替隔离。

隔离工具按用途分开：`check-runtime-coherence.py` 准备/操作真实 QA 代次；`check-coherence-entry.py` 验证固定入口、并发复用、公开脱敏和只读 GET；`check-coherence-recovery.py` 验证连续访问、到期、GeoIP 故障和正常恢复；`check-coherence-isolation.py` 注入精确 QA 拓扑或规则漂移并恢复限制；`check-coherence-rotation.py` 经受限 peer 桥接执行同一代理入口的 JP → UNKNOWN → HK 双 Profile 验收。每次操作使用新的私有输出目录，旧失败不覆盖。所有工具只用于明确拥有的 QA 根，不能对生产 Home 运行。

## r7 组合 QA 工具

[R5E 记录](../release-combination-acceptance-2026-09-15.md) 使用同时启用登录、Store 和一致性的独立根；以下工具对该工作项的日期、资源登记、Profile 和挂载范围有明确限制，不能替换成生产配置运行。

| 工具 | 输入与行为 |
| --- | --- |
| [准备](../checks/prepare-release-combination.py) | 已准备且为空的 QA `--root`、固定 `--candidate`、公网 `--bundle`、`--artifact`、`--acceptance`、`--geoip`；注册独立账号、应用、策略与凭据 |
| [真实客户端运行器](../checks/run-release-combination.py) | `--root`、全新 `--output`、`--phase base\|faults\|resume\|policies\|rotation\|revocation\|recovered`；每阶段保留单独结果和故障清理证据 |
| [撤销观测](../checks/check-release-revocation.py) | 由运行器调用；真实 WS/WSS、关闭确认、最多 90 秒等待浏览器网络错误、绕过尝试和 Worker 抓包，最后重试正常清理 |
| [加密恢复准备](../checks/prepare-release-recovery.py) | 源 `--root`、全新 `--output` / `--target`、已观测的 `--baseline` 和固定 `--age`；停止源 QA、创建/验证/恢复归档、合并当前授权，再将资产和 Home 重绑到新根 |
| [清理](../checks/cleanup-release-combination.py) | 恢复根、源根、备份结果、真实客户端结果及全新输出；按所有权检查回收两套代次、进程、空 tmpfs 和匿名卷，并复核生产保持 |

恢复准备保留私有 TLS 验证，QA 主机 28443 映射到控制器的 8443。账号表按解析后的完整内容比较，JSON 序列化格式不作为授权变化。`--resume-offline` 只继续已有的已验证/启用归档，要求精确源 QA 已退役、归档重新认证、当前授权再次合并、目标尚不存在；已有部分目标会被拒绝并保留供核对。该入口不替代产品恢复的校验、撤销合并或启动门槛。外部端点寿命仍为六小时，过期须核对准确旧进程并保留其证据，不能把基础设施退出当成浏览器验收通过。
