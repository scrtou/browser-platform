# 轻量公开 DNS 与一致性测试端点

[工作项](../../../../docs/work-items/R5C2-2026-09-14-approved-dns-ttl.md) · [权威 DNS](../public-dns-authority/README.md) · [完整 DNS 验收](../../lifecycle/bootstrap-dns.md#公开-dns-的待执行材料)

每台外部机器只运行一个 Python 3.11+ 进程，提供本次 QA 的网站和受限代理。SealSkin、Adapter、浏览器和 Home 保留在现有测试主机。程序使用标准库及固定 SHA-256 的 dnspython 2.8.0 wheel，直接从离线包加载，不安装系统包；每台压缩包约 330 KB。

## 程序与边界

| 文件 | 作用 |
| --- | --- |
| [endpoint.py](endpoint.py) | 精确来源/目标限制、认证、数值 DNS、HTTP/HTTPS/WS/WSS、SOCKS5/HTTP(S) CONNECT、故障和有界日志 |
| [prepare.py](prepare.py) | 根据公开采样计划生成两个私有部署包、短期测试 CA/叶证书、随机凭据及文件摘要；不连接远端或修改 DNS |
| [check.py](check.py) | 在两个回环地址运行实际程序，验证协议、拒绝、故障、恢复、TLS 并发和容量；合成 DNS 不算公开 TTL 证据 |
| [manage.py](manage.py) | 依据部署证据核对 SSH 主机、UID、目录、argv、PID/start ticks，收集日志、切换故障、正常停止和清理准确目录 |

公开浏览器配套工具为 [check-public-dns-browser.py](../check-public-dns-browser.py)、[持续连接/失败页面观测](../check-public-dns-fault.py) 和 [DIRECT DNS wire](../public-dns-wire.py)。均使用独立 QA Home、正常生命周期 API、正常地址栏和唯一 nonce；持续 WS/WSS 页面只写入明确归属的 QA Worker 临时目录，不启用调试接口。浏览器故障须同时核对既有连接关闭、新页面错误、DIRECT 控制路径和网络记录。

[专属 QA 网桥记录器](../public-dns-bridge-wire.py) 跨 Relay 停止/恢复采集其 L3/L4 元数据；启动器核对网络标签、唯一 Relay 连接、IPv4 和准确网桥，保留 MAC 变化及内核包类型。从 Relay 进入独占网桥的帧与主机送出的 `PACKET_OUTGOING` 分开记录，不按初始 MAC 丢弃 IPv6。普通 Worker/Relay 出站仍在各自 QA 命名空间采集。所有记录仅用于本次端点和 QA 资源的关联，不收集生产流量。

每次包只接受计划中的两个网站名称、一个代理名称和两个端点 IPv4。代理必须认证且只接受指定测试主机来源，只可连接这两个端点的网站端口；网站额外允许两个端点互访。TLS 握手之前先核对来源及并发数。只支持 SOCKS CONNECT 和 HTTP CONNECT，不提供 SOCKS UDP、任意 HTTP 转发、递归 DNS 或公开管理接口。

网站名通过指定数值 IPv4:53 查询，每次连接重新查询，无系统 resolver/hosts 回退或应用缓存。此次夹具只接受精确名称的 A 回答，整个地址集合必须属于两个批准端点；CNAME 等其他答案拒绝。UDP 截断经核对后使用同一解析器 TCP，合计最多 5 秒。日志保存请求/回答 wire、解析器、接收时间、TTL、实际选中地址和连接标识，供真实递归/权威证据关联。

默认同时最多 16 个客户端连接，包括尚未完成的 TLS 握手；TLS/HTTP 头最多 5 秒，连接最多 120 秒，每方向隧道数据最多 4 MiB。服务最多运行 6 小时；进程限制 256 个文件描述符、256 MiB 虚拟地址空间，关闭 core dump。虚拟地址上限不等于实际内存预留。事件日志每份 2 MiB，保留当前及两份轮转文件。

`/probe` 用于 TLS 预检；`/test?nonce=<32hex>` 运行四种网页协议并显示结果；`/echo`、`/ws`、`/download` 和 `/complete` 只接受测试 nonce。浏览器自行报告的 PASS 不能代替服务日志、代次绑定、抓包和完整验收。网页缓存关闭，普通 HTTP 响应后关闭连接；没有声明支持 HTTP/3 或 WebRTC。

R5E 增加 `/client?nonce=<32hex>`：只接受两个普通网站域名的 HTTPS 和唯一 nonce 参数，返回固定的 [客户端合成数据页面](../client-fixture.html)，供真实浏览器比较 Cookie、localStorage、IndexedDB。观察域名仍只接受其原有三个路径；HTTP、IP Host、缺失/重复 nonce 和额外字段拒绝。文件随 manifest 打包，端点回环检查现为 33 项；页面内容检查不代替真实浏览器恢复验收。

## 准备与隔离验证

先用 [公开采样器](../check-public-dns-ttl.py) 为实际资源生成 `plan.json`，三个路径共用两个外部 IPv4。网站目标不能是浏览器宿主机公网地址。

```bash
python3 infra/sealskin/checks/public-dns-endpoint/prepare.py \
  --plan /private/public-run/plan.json \
  --dependency-directory /private/fixed-wheels \
  --client-ipv4 BROWSER_HOST_PUBLIC_IPV4 \
  --output /private/endpoint-bundle
python3 infra/sealskin/checks/public-dns-endpoint/check.py \
  --bundle /private/endpoint-bundle --output /private/endpoint-check-1
```

输出目录必须是新的。准备器生成 `before.tar.gz`、`after.tar.gz`、各自文件 manifest 和 `bundle.json`；包内含随机代理凭据和叶证书私钥，目录 0700、文件/归档 0600，不进入 Git。CA 私钥只留在准备机，归档不包含它；证书有效期 2 天，仅导入本次隔离 QA 的信任库。

隔离检查需要本机 `curl`，不需要 Docker。它只使用 `127.0.0.0/8`、本机合成 DNS 和独立子进程；`--isolated-loopback-test` 同时要求监听、来源、解析器及目标全部为回环地址，无法据此启动公网服务。结果和失败材料保留在新目录，结束时停掉准确的子进程，移除测试副本中的凭据/叶证书私钥。

2026-09-14 首轮 29 项隔离检查通过，包括三种认证代理到 HTTP/HTTPS、WS/WSS、错误凭据/来源/域名/IP/端口拒绝、完整 DNS 集合拒绝、超时/错误事务/NXDOMAIN、UDP/TCP、端点改变、已有隧道中断及恢复。8 客户端 80 次请求通过，主要服务峰值 RSS 36,264 KiB（约 35.41 MiB），单线程；这是本程序的回环实测，不替代远端容量或公开 TTL 验收。

2026-09-14 第五轮在两台受控公网机器完成三路径真实 TTL 和正常 Camoufox 访问：13 个页面/52 项 HTTP/HTTPS/WS/WSS，两轮故障及同代次恢复、新代次解析均通过；外部代理 180 次 DNS 与连接逐条关联。公开浏览器路径使用认证 SOCKS5，不表示本轮重跑了 R5A 全协议矩阵。两个端点进程峰值分别为 34,588 KiB（约 33.78 MiB）、33,612 KiB（约 32.82 MiB）。五轮全部服务和十个远端目录已清理；详细边界和失败历史见 [完整验收](../../approved-dns-ttl-acceptance-2026-09-14.md)。

## 部署、故障与清理

先通过 SSH 核对 Python、可用资源、实际本机 IPv4 和端口。只把各自的归档传到对应机器 `temptest` 用户下新建的 0700 目录；核对归档摘要、所有文件 manifest、文件归属与权限。不要覆盖已有目录或使用整个项目的 Compose。默认监听如下，配置内地址必须是远端实际拥有的地址；NAT 机器须另行核对绑定与来源。

| TCP 端口 | 服务 |
| --- | --- |
| 18080 / 18443 | HTTP / HTTPS、WS / WSS |
| 18180 | 认证 SOCKS5 |
| 18181 / 18182 | 认证 HTTP / HTTPS CONNECT |

在远端私有目录验证配置，再启动普通用户进程：

```bash
python3 endpoint.py --config config.json --validate-only
python3 endpoint.py --config config.json
```

长时间测试可以由 SSH 启动一个脱离终端的独立进程；保存 PID、完整参数、目录、manifest 和 `state/ready.json`。程序使用 `state/run.lock` 防止同目录重复运行，无主机启动项，不重启其他服务。先验证端口从测试主机可达，再发布 QA A 记录；监听成功不等于公网可达。

故障开关只通过 SSH 原子替换远端 `state/mode.json`：`{"mode":"offline"}` 关闭已有隧道/下载并拒绝新请求，`{"mode":"online"}` 恢复；缺失、损坏或未知内容按 offline 处理。不要通过公开 HTTP 控制故障，也不要靠关闭整台机器模拟故障。

结束时先核对 `/proc/<pid>/cmdline`、UID、启动身份和目录，再向这个进程发送 SIGTERM。等待其退出、监听消失及 `state/metrics.json`，取回日志、配置摘要和清理证据；只移除准确归属的临时包、凭据和叶证书私钥，不修改其他应用、真实浏览器或用户数据。专用 SSH 公钥和 QA DNS/端口配置的撤销按其实际维护范围处理，不能恢复整份旧配置覆盖后续用户改动。

`manage.py stop` 在核对部署 manifest、进程 UID/argv/start ticks 后正常停止并收集日志；随后用同一部署记录执行 `purge`，仅删除它绑定的准确目录。示例：

```bash
python3 infra/sealskin/checks/public-dns-endpoint/manage.py purge \
  --deployment /private/deployment-before.json \
  --ssh-key /private/test-key --known-hosts /private/known_hosts \
  --output /private/purge-before-1
```

本地 bundle 中的凭据、叶证书/CA 私钥和归档也需清理；证书、manifest 与私有日志可按证据策略保留。公开 QA 的抓包和 DNS 记录器在删除前保存完整容器/Mounts，并使用准确 ID 的 `docker rm -v` 回收匿名卷。旧工具缺少该步骤的处理见 [DEV-019](../../../../docs/deviations/DEV-2026-09-14-019-qa-anonymous-volumes.md)：原始映射缺失与空卷恢复清单分别记录，不以容器数量为零推断所有卷已清空。


## R5C3 浏览器观测与实际出口轮换

打包器增加 `--coherence`，生成本次 run 专属的 `observe-<run>.<zone>` 及 nonce 子域、短期证书与固定环境观测脚本。HTTPS `/health` 供预检，`/environment-test.html` 在正常浏览器页面上下文测量，`/whoami` 只返回 socket 源 IPv4、nonce、阶段和服务时间；不使用 X-Forwarded-For，也不代替控制器作健康判定。权威 DNS 的观察名称和 wildcard A 指向同一个观测端点，时间校验保持 ±5 秒；端点时钟不合格应修时钟或保持另一观测端点，不能放宽验收。

额外 `--rotation` 启用两个已批准端点之间的受限 HTTPS CONNECT。peer 使用独立随机凭据，仅接受另一端点来源和相同 QA 目标/端口，经现有 18443 监听，目标端强制本地出站以避免循环。原 18180/18181/18182 代理的来源限制不变，不新增端口，也不开放任意转发。`manage.py rotation --exit local|peer` 只经 SSH 改准确远端目录的状态，变化时关闭旧隧道；`mode offline|online` 保持原故障语义。

这使两个独立 Profile 可以共用同一代理 IPv4/端口，却分别观测真实 JP 或 HK 出口。配套 [轮换检查](../check-coherence-rotation.py) 包含 JP → UNKNOWN → HK 与返回原出口，比较 recheck/block，核对各自 nonce、绑定、环境和故障保留。端点标准回环检查现为 32 项；轮换的国家结论来自指定 DB-IP 数据库，不能由服务器标签推断。结束后仍需精确停止、collect、purge 并核对监听与目录；本地私有证据归档含敏感副本时必须如实记录保留范围。
