# R5C2 专用公开权威 DNS

## 独立递归缓存的 QA 入口

公开公共递归前端的前三轮缓存验收未通过，失败与处理见 [DEV-016](../../../../docs/deviations/DEV-2026-09-14-016-public-recursive-cache-samples.md)。后续 QA 使用独立标准 Unbound 缓存：真实查询公网根、父区和本页的公开权威，无 hosts、stub/forward zone、预取、过期回答或合成 TTL。固定 Debian 包摘要见 [递归依赖锁](recursive-dependencies.json)；包和所需库在独立运行目录解包/复制，未安装主机系统包。

[dispatch.py](dispatch.py) 将批准名称的 A/RD 请求转交回环 Unbound，将 QA 子区的其他查询交给原 CoreDNS 区域。`recursive_names` 最多八个子区名称；`delegation_names` 最多四个精确 NS 主机名，限于 QA 父区，仅批准其 A/RD 查询。后者是采样工具核对 NS 地址的必要依赖（[DEV-017](../../../../docs/deviations/DEV-2026-09-14-017-public-recursive-delegation-scope.md)）。其他区外查询、AXFR/IXFR/ANY 均拒绝；入口不缓存或改写 DNS 回答。

Unbound 只发布回环高端口。公开入口绑定 QA 公网地址的 UDP/TCP 53，初始仅保留绑定及降权所需 capabilities，绑定后永久降到 UID/GID 1000，并确认允许、有效和 ambient capabilities 全部清空。限制 64 个 UDP 任务、32 个 TCP 客户端、4 KiB 报文、4 秒后端预算、轮转日志和六小时运行期限。原 QA 权威容器/配置保留供恢复，生产域名、浏览器和主机防火墙不变。

[check-dispatch.py](check-dispatch.py) 使用已经发布的诊断名称检查真实递归/权威回答、精确 NS 依赖、区外拒绝、沉默 TCP、24 并发和后端超时。需固定 dnspython；传入 `--config`、`--diagnostic`、`--authoritative`、`--address`、`--delegation-address` 和新的 `--output`。不要提前查询新 TTL 计划的名称。服务检查通过后还必须执行公开采样、浏览器三路径、冻结、故障/恢复及清理；该入口本身不代表 R5C2 通过。

[引导 DNS 与公开验收](../../lifecycle/bootstrap-dns.md) · [R5C2 工作项](../../../../docs/work-items/R5C2-2026-09-14-approved-dns-ttl.md) · [验收报告](../../approved-dns-ttl-acceptance-2026-09-14.md)

此目录提供独立 QA zone 的权威服务配置。它使用固定 CoreDNS 镜像，提供 SOA、NS、限定区域内的记录和查询日志；不配置递归、转发、缓存或区域传送。真实端点地址确认后，按采样计划加入三条随机 A 记录，使用 SOA serial 和原子区域文件替换完成轮换。

2026-09-14 当前结果：第五轮完整公开验收已通过，包括标准 Unbound 的三路径 180 秒 TTL、真实浏览器、冻结/故障/恢复和日志关联，详见 [验收报告](../../approved-dns-ttl-acceptance-2026-09-14.md#第五轮公开验收)。临时递归/dispatcher/后端已移除，原 `r5c2-public-dns-authority` 容器恢复，Corefile 保持，serial 为 `2026091413`；五轮 15 条临时 A 记录已删除，只留 SOA/NS/ready TXT。恢复后本机 12 项、两台外部机器共 24 项 UDP/TCP 及拒绝检查通过。

## 固定输入与运行方式

| 输入 | 用途 |
| --- | --- |
| [image.json](image.json) | CoreDNS 1.13.2，固定完整镜像摘要，平台 `linux/amd64` |
| [Corefile.example](Corefile.example) | 绑定单个数值 IPv4:53，指定唯一 QA zone；每秒检查 SOA serial |
| [db.zone.example](db.zone.example) | SOA/NS 与准备状态 TXT；实际 TTL 轮换名称/地址由后续采样计划生成 |
| [firewall-proposal.nft](firewall-proposal.nft) | 历史临时入站提案，助手未应用；用户已另行开放端口，不再执行 |

实际配置与详细证据位于被忽略的 `infra/sealskin/runtime/r5c2-dns-ttl-2026-09-14/public-authority-setup/`。运行容器为 `r5c2-public-dns-authority`，带 R5C2 与 QA 归属标签；`launch-command.json` 保存精确命令，`image.json` 保存实测摘要。

容器使用 host network，并在 Corefile 中显式绑定 `23.19.231.152`，不创建端口映射或 Docker 网络。以 UID/GID 1000 运行，只保留 `NET_BIND_SERVICE`，使用只读根文件系统和只读 QA 配置目录；限制 128 MiB 内存、0.5 CPU、64 个进程与 1,024 个文件描述符。日志最多三份、每份 10 MiB。`restart=no`，本轮不包含主机重启后的自动恢复。

生成配置时把示例区域替换为 `dns-qa.azhen.de`，NS 替换为 `dns-qa-ns1.azhen.de`，地址替换为 `23.19.231.152`。配置目录归 UID/GID 1000，目录模式 0750、文件 0640；整个目录只读挂载到 `/qa`。目录挂载使宿主机原子替换后的新区域文件对容器可见。启动前检查精确监听地址/端口空闲，并以 `image.json` 中的摘要启动。

## Cloudflare 记录

用户已在 Cloudflare 的 **azhen.de → DNS → Records** 添加下列两条记录，Auto 的实际 TTL 为 300 秒：

| 类型 | 名称 | 内容 | 代理状态 |
| --- | --- | --- | --- |
| A | `dns-qa-ns1` | `23.19.231.152` | DNS only（灰云） |
| NS | `dns-qa` | `dns-qa-ns1.azhen.de` | 不适用 |

NS 主机名位于父区，A 记录也由父区提供；该配置无需在被委派子域内设置 glue。准备时该 NS 名称和一个随机未配置名称都返回 Cloudflare 代理地址，因此这里需要显式 DNS only A 记录。两条记录对应的完整文本保存在 `parent-delegation.txt`；没有执行任何 Cloudflare 写入。

两个父权威服务器中的 NS/A、根到子区委派链以及 `1.1.1.1` / `8.8.8.8` 对 `ready.dns-qa.azhen.de TXT` 的回答已核对；随机递归名称与权威日志关联通过。证据位于独立 `public-delegation-check/`，早先无委派的查询记录保持。父区 300 秒 TTL 与实际轮换 A 记录的 TTL 分开核对；第五轮 A 记录为 180 秒，基础 zone 默认 60 秒。

## 防火墙提案与回退

历史准备阶段的 Globalping 欧洲/北美探测均超时，当时只读规则快照没有 53 入站规则。用户随后报告已开放端口；新一轮两个 UDP 和两个 TCP 探测全部通过，正确 SOA、AA/无 RA 与日志事务对应。无需再次请求该端口的维护授权。

提案仅允许 `eth0` 收到的、目标为 `23.19.231.152` 的 UDP/TCP 53，使用唯一注释 `r5c2-public-dns-udp` / `r5c2-public-dns-tcp`。`nft --check --file` 已在主机网络命名空间通过；校验前后规则内容一致，实时包/字节计数不参与比较。没有执行规则应用、持久化或服务重启。

助手没有应用上述提案，不能把用户配置的现有规则当作本次生成的规则回退。DNS 服务停止使用后按精确容器 ID/标签停止，保留配置、区域历史与日志；如需撤销用户的端口或 Cloudflare 配置，应按当时的实际维护范围核对，不恢复整份历史规则快照。

## 区域轮换与复用

每次修改先生成新区域文件，校验语法和完整内容；增加 SOA serial，保存带摘要的版本，然后在同一目录原子替换 `db.zone`。用直接 UDP/TCP SOA/TXT/A 查询确认新 serial 和数据实际生效，再进行递归缓存阶段采样。2026-09-14 的 serial `2026091401 → 2026091402 → 2026091403` 只改变准备状态 TXT，证明本机区域重载，不能计作端点地址轮换或缓存到期证据。

完整三路径验收使用两个不同、受控且真实路由的公网 IPv4，分别承载轮换前后的网站与代理。用户提供的两台机器已经完成 SSH 登录、轻量服务部署和公网验收，五轮服务及十个部署目录均已清理。外部机器没有运行浏览器、SealSkin 或 Adapter；DIRECT 网站目标仍不能使用浏览器宿主机原生公网地址。后续工作使用新随机计划和临时凭据复用已授权资源。

公开采样器、浏览器路径和网络抓包按 [完整验收步骤](../../lifecycle/bootstrap-dns.md#公开-dns-的待执行材料) 执行。准备状态、端口探测或单独 DNS 采样不能代替三条实际路径。原基础权威和用户 DNS/端口配置暂留给 R5C3；结束全部验证后按精确归属撤销，不恢复历史防火墙快照。

2026-09-30 R7G 复用检查：当前 IPv4 基线的 UDP 53 放行位于无条件 return 之后，TCP 53 无有效放行；本机权威正常，外部超时。历史开放状态不代表当前可用，见 [DEV-084](../../../../docs/deviations/DEV-2026-09-30-084-public-qa-dns-ingress.md)。两条本轮精确临时规则已 dry-run，尚未应用；不会重放旧规则表。
