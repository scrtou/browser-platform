# 代理端点引导 DNS 与 TTL

[生命周期](README.md) · [DIRECT 网站 DNS](direct-network.md) · [R5C2 工作项](../../../docs/work-items/R5C2-2026-09-14-approved-dns-ttl.md)

R5C2 候选为代理端点增加显式批准解析器和代次 DNS 记录，已完成私有 QA 和标准 Unbound/受控公网端点的真实三路径 TTL 验收，见 [最终报告](../approved-dns-ttl-acceptance-2026-09-14.md)。生产尚未采用；`network_bootstrap_dns_version: 1` 仅表示控制器支持此契约，不能代替某个 Profile 的新鲜 DNS 观测。R7G 动态域名模式在不改变浏览器代次的前提下消费后续批准回答，使用独立 `endpoint` lease 和 `relay-v2` Guard 规则；静态数字 IP 与未声明动态能力的镜像仍走本页的冻结行为。

## 配置和兼容

策略的 `bootstrap_resolver_id` / `bootstrap_resolver_ip` 成对配置，后者为规范化数值 IPv4，端口固定为 53。示例见 [批准引导 DNS 策略](network-policy.bootstrap-dns.example.json)；示例地址和镜像摘要需要替换为实际批准值。DIRECT 禁止这两个代理字段，继续使用自己的 `approved_resolver_id` / `approved_resolver_ip`。HTTPS 上游仍按 `upstream_host` 校验证书，连接的是冻结 IPv4。

| 上游配置 | 新代次实际行为 | 记录来源 |
| --- | --- | --- |
| 规范化数值 IPv4 | 不执行 DNS，直接冻结地址；即使策略配置了解析器也不查询 | `numeric` |
| 主机名及完整批准解析器字段 | 控制器仅向指定端点查询 | `approved_resolver` |
| 主机名且两字段为空 | 保留旧系统引导解析路径，不算批准解析器通过 | `legacy_system` |

空字段不加入策略规范化快照，旧 SHA 保持。`mode=proxy_required` 本身不能证明使用了批准解析器。已有的旧代次仍按原占用与配置恢复，不补造 DNS 回答或 TTL；采用新字段须创建新策略修订，并等旧代次通过生命周期停止后启动新代次。活动代次不会随注册表变化切换端点。

批准路径不读 `/etc/hosts`、系统 resolver 或搜索域，没有应用 DNS 缓存。只查询 A，逐一验证事务、问题、rcode、CNAME 和完整 IPv4 回答；只有经过验证的 UDP 截断才转向同端点 TCP。全部交换共用 5 秒预算，最多八次 CNAME 跳转、128 条记录和 64 个 IPv4；错误、循环、分叉、无 IPv4 或混合非法地址使整次解析失败。保持代理设施可以位于私网的既有契约，拒绝 loopback、unspecified 和 multicast；这与 DIRECT 网站目标的公网 ACL 不同。

## 代次记录、失败与恢复

创建网络资源前先保存占用，再保存 `bootstrap_dns_version: 1` 与 `bootstrap_dns`。记录包含解析来源、策略中的原始主机名、实际解析器、CNAME/A 回答、各次接收时间、TTL、完整地址集合和选中端点。绑定覆盖 Home hash、operation 和策略 SHA；allocation 另存 DNS 记录、Relay 配置及网络规则配置的摘要。

`ttl_seconds` 为相关 CNAME/A 记录的最小 TTL；`expires_at` 为各记录“接收时间 + TTL”的最小值。静态模式下两者描述当时回答，**不能作为释放 Home、热改地址或恢复时重新解析的授权**。动态模式仅在每代次已持有 `dynamic_upstream_version: 1`、镜像能力标签和有效 lease 时，按该 TTL 触发有界刷新；刷新仍须候选 TCP 预检、Relay 内真实 `PROXY_OK` 探测和 Guard 的旧/新原子切换。任何 DNS、预检、探测或规则失败都保留旧 lease/阻断，不把 TTL 当作放宽 ACL 的授权。

新代理代次恢复和控制器重接前，核对 DNS 记录与 allocation、端点 lease、配置摘要及 Relay 的精确只读绑定挂载。动态 lease 还核对单调 revision、lease ID、`relay-v2` 网络摘要与只读 runtime 挂载；控制器重启后只恢复可证明的同一代次。静态代次的 DNS 到期或解析器故障不改变已经冻结的端点；动态刷新或恢复仍必须通过原上游的网络预检，不能因为 DNS 记录存在就跳过验证。

`NETWORK_BOOTSTRAP_DNS_TIMEOUT`、`SERVFAIL`、`NXDOMAIN`、`REFUSED`、`INVALID`、`NO_IPV4`、`UNAVAILABLE` 以完整 `NETWORK_BOOTSTRAP_DNS_` 前缀返回；非法端点集合使用 `NETWORK_UPSTREAM_ADDRESS_INVALID`。失败留下 `preparing` 占用及脱敏错误记录，不创建 Worker，也不临时放宽 ACL。新配置或挂载漂移使用 `NETWORK_BOOTSTRAP_CONFIG_CHANGED` / `NETWORK_BOOTSTRAP_CONFIG_MOUNT_CHANGED`，DNS 记录损坏为 `NETWORK_RESERVATION_INVALID`；保留占用供对账。

## 构建和回退

固定依赖为 [python-dependencies.json](python-dependencies.json) 中的 dnspython 2.8.0，SHA-256 为 `01d9bbc4a2d76bf0db7c1f729812ded6d912bd318d3b1cf81d30c0f845dbf3af`；安装器另固定 pip 25.3 wheel，SHA-256 为 `9655943313a94722b7774661c21049070f6bbb0a1516bf02f7c8d5d9201514cd`。准备器可下载两个 wheel，或用 `--dependency-directory /private/wheels` 离线准备，均核对散列。Runtime 以临时 `PYTHONPATH` 运行 pip wheel，从构建内 wheel 使用 `--no-index --no-deps --require-hashes` 安装 dnspython，不执行 apk 或向系统安装 pip；checks 继承同一 Runtime，再添加测试工具。首版浮动 apk 安装器偏差见 [DEV-012](../../../docs/deviations/DEV-2026-09-14-012-dns-build-toolchain.md)。

安装器在任何应用文件写入前核对发行包版本、模块版本及 DNS wire/transport 导入；缺少或错误依赖拒绝安装。payload release 覆盖应用文件与依赖锁，镜像 `pkg` 摘要另外覆盖 patch、准备器、安装器及上游摘要，测试或安装包装改变不会覆盖旧候选标签。

回退旧控制器前，必须用支持新契约的控制器清空使用新策略字段的代次并保留 Home，恢复匹配的策略引用与候选镜像。旧控制器不支持新字段，不能直接拿它对账新代次；不能覆盖最新 journal。生产维护仍按已授权的实际范围执行，本项没有部署生产。

## 隔离检查

按 [QA 准备说明](README.md#验证与范围) 在新的私有目录准备控制器、正常 r6 Camoufox、NSS 工具和 Observer，再执行：

```bash
python3 infra/sealskin/checks/check-bootstrap-dns.py \
  --root /private/dns-check/qa \
  --build /private/dns-check/build \
  --output /private/dns-check/bootstrap-1
```

检查器只操作 `network-qa` 用户/Home、已核对的 QA 控制器和专属网络。DNS 夹具固定在 QA bridge 的数值地址，不发布主机 53 端口。它用真实 UDP/TCP、CNAME、非零 TTL、故意错误的 QA hosts 映射及故障回答验证批准路径；检查活动代次、Relay 重启、控制器替换、正常浏览器恢复、新代次重新解析及数值地址绕过 DNS。HTTP/HTTPS/WS/WSS、Worker DNS 绕过及受控上游的网站域名请求分开核对。

QA 导航会在提交前核对精确地址，避免恢复窗口中的输入拼接。Observer 的 TLS 握手在独立请求线程内完成，5 秒超时；不会让沉默连接阻塞所有 HTTPS/DoH 请求，见 [DEV-013](../../../docs/deviations/DEV-2026-09-14-013-qa-tls-accept-blocking.md)。这些是验收工具行为，不改变浏览器或产品网络策略。

`bootstrap-dns-fixture.py` 是私有权威夹具，**没有递归缓存或公开委派**。其中的非零 TTL 和到期后冻结检查不能算公开 TTL 轮换。检查器失败保留代次与每轮输出，只自动移除其 DNS 夹具；重新运行使用新输出目录，先通过受验证的生命周期停止已有 QA 代次。`--faults-only` 仅继续故障与数值场景，完整结论还须保留并核对前序阶段证据；最终候选已另行完成全轮。完成后按 [清理器](cleanup-network-qa.py) 的归属检查清理，匿名卷仅依实际挂载/事件证据逐个移除，不执行全局 prune。

<a id="公开-dns-的待执行材料"></a>
## 公开 DNS 的执行与证据

公开工具的离线 verify 证据完整性缺陷 [DEV-014](../../../docs/deviations/DEV-2026-09-14-014-public-dns-evidence-validation.md) 已修复，最初 36 项工具检查和后续多样本扩展的 50 项检查通过。回环/合成 DNS 只证明工具行为；第五轮真实公开结果单独见报告。

[公开采样器](../checks/check-public-dns-ttl.py) 可先生成可审阅的 NS/glue 与轮换前后 A 记录，不写 DNS zone。输入 [配置示例](../checks/public-dns-ttl.example.json) 中的解析器、权威和端点必须替换为实际批准资源；示例 `.invalid` 与文档地址会在公开采样前被拒绝。所有采样使用固定 dnspython 依赖和显式数值端点。

```bash
python3 infra/sealskin/checks/check-public-dns-ttl.py prepare \
  --config /private/public-dns-config.json --output /private/public-dns-run
python3 infra/sealskin/checks/check-public-dns-ttl.py sample \
  --run /private/public-dns-run --phase before
# 在批准的独立 QA zone 应用 after-records.txt，保持递归缓存。
python3 infra/sealskin/checks/check-public-dns-ttl.py sample \
  --run /private/public-dns-run --phase cached
# 等待三个路径首次回答接收时间 + 实际 TTL + 1 秒取整余量。
python3 infra/sealskin/checks/check-public-dns-ttl.py sample \
  --run /private/public-dns-run --phase expired
python3 infra/sealskin/checks/check-public-dns-ttl.py verify \
  --run /private/public-dns-run
```

每次运行生成三个独立随机名称，分别对应 DIRECT、代理引导和上游网站 DNS。默认单样本为计划版本 1/证据版本 2；`prepare --cache-observations 32` 等显式多样本模式为计划版本 2/证据版本 3，样本数为 2–32，保存在计划的 `cache_observations` 字段。全部样本逐条验证，不丢弃异常回答。旧证据不补造缺失 wire，须用新随机名称重新采样。每次记录请求/回答/截断 wire、父区 NS 和必要 glue、全部配置权威的地址/SOA/NS/A、批准递归回答及采样来源；verify 重解析 wire 并核对完整集合、计划/阶段/来源。

权威 A 记录的 TTL 须与已审阅计划相同。`cached` 必须在各路径首次递归查询“开始时间 + TTL”之前完成，看到权威新地址和递归旧地址；两次递归回答的可能到期区间须重叠，不能把未递减的完整 TTL 当作旧缓存证据。`expired` 查询须在首次回答“接收时间 + TTL + 1 秒”之后开始，以容纳网络耗时和 DNS 整秒取整。递归回答须有 RA 且无 AA；权威日志仍须另行证明实际递归来源。

输出不覆盖旧阶段或验证结果。采样失败保存 `<phase>.failed.json` 及已取得的材料，重试该阶段在查询前拒绝；保留整轮并准备新随机名称，不能删除失败文件后拼接成通过记录。通过验证时保存实际已验证阶段文件的摘要。工具检查可在装有固定 dnspython 的独立 Python 环境中运行 `python3 infra/sealskin/checks/test_public_dns_ttl.py`。

直接 DNS 采样不能证明三个浏览器路径，成功时仍只返回 `PARTIAL`。完整 R5C2 另核对同轮根/父区委派、权威实际递归来源、正常 DIRECT 浏览器、控制器代次绑定、真实上游网站解析、Worker 绕过抓包及端点轮换/故障/恢复。第五轮已全部取得这些证据，使用 180 秒 TTL 和原一秒取整校验；13 个页面/52 项协议、两轮故障恢复、新代次、66 次 DIRECT DNS 与 180 次外部代理解析/连接关联通过。

公共递归前端可能有多个缓存期限或命中未预热的节点；前三轮失败见 [DEV-016](../../../docs/deviations/DEV-2026-09-14-016-public-recursive-cache-samples.md)，不扩大为公共 DNS 保证。第五轮的[独立标准递归入口](../checks/public-dns-authority/README.md) 没有 hosts、stub/forward zone、预取或合成 TTL，真实经公网根/父区解析。原始失败和第五轮旧网桥 PARTIAL 均保留。

[浏览器工具](../checks/check-public-dns-browser.py) 驱动正常生命周期和页面，[故障工具](../checks/check-public-dns-fault.py) 同时观测 WS/WSS 关闭及真实失败页，[DIRECT wire](../checks/public-dns-wire.py) 和[专属网桥](../checks/public-dns-bridge-wire.py) 关联 DNS/跨重启出站。记录器结束前保存完整容器/Mounts，按精确 ID 执行带卷清理。五轮服务/包已清理，原基础权威恢复，本机/外部复测通过；基础 QA 委派和 SSH 暂留后续验证。


R7G 失败恢复约束（2026-09-30）：动态 pending 恢复只能停止已证实属于当前 Home/operation 的 Relay；归属未证实不执行停止，恢复失败保留 pending 和错误证据，不能宣称回滚成功。真实 SDK 停止调用及双失败隔离证据见 [集成验收](../r7g-controller-integration-acceptance-2026-09-30.md)；该增量未部署生产，公网供应方和目标客户端范围仍待验证。

2026-09-30 动态增量：两个隔离 Home 的公共递归 DNS 和认证 SOCKS5 完成 A→B→A，旧 WSS 保持、新连接真实来源变化，见[公网验收](../r7g-public-acceptance-2026-09-30.md)。仅受控公网 QA，商业供应方自然漂移和客户端仍单列；临时 DNS 入站规则已回收。
