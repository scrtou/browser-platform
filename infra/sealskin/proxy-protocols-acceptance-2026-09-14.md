# R5A · 上游协议、认证与正常退出验收

[验收索引](../../docs/acceptance/README.md) · [工作项](../../docs/work-items/R5A-2026-09-14-proxy-protocols.md) · [Relay](../../relay/README.md) · [退出层](../browser-runtime/README.md)

日期：2026-09-14 UTC。**状态：代码、隔离验收、QA 清理与文档收尾完成；生产未部署。** 本报告只覆盖固定上游与独立 QA，不代替完整 P/N/S 组或项目发布门槛。

## 版本与环境

| 对象 | 本次版本 |
| --- | --- |
| SealSkin 基线 | 上游 commit `2b13a42483c1dc7d367d5c340437bdc8ecd84bb4`，固定 `0.3.2-ls58` 镜像 |
| 最终控制 payload / checks | `0.3.2-proxy-v1-f921ceefcf1e0250`；runtime ID `sha256:6079ec47ea5865179ee1a22ce4f0c859a807deb3ed01e91478d9b521d0af883e`，checks ID `sha256:0e6f499f95a731cf2f227544957b25b1e4ef7644f755cd7716edda321009ae95` |
| 版本化 patch | SHA-256 `bf3734de894b2ff8f714087c95f6d8b47de033ff4395c406c977ad87a0b62779` |
| Guard / Relay | `browser-platform/profile-relay:guard-v1-5ae5b525b2534370`；image ID `sha256:5ec9c14ca9c10ad854d1c7e68864b41e978caebd3eeec9554aa37de01d7e1045` |
| 独立 Relay | `browser-platform/profile-relay:relay-v2-3dcbb45e7233e8cf`；image ID `sha256:c786c07c653c6f2212dd53b2877d0bc41de9444c8376040fe6b503953a162636` |
| Relay 系统 CA | `ca-certificates-bundle-20260611-r0`；bundle SHA-256 `b8d837841b88bfaa1a0fa827cbca8e2576418dd47c9fc4bb7f1f9d89c83111b9` |
| 浏览器 | 固定 Camoufox Python 0.5.6 / BrowserForge 1.2.4 / browser v152.0.4-beta.30；原 r4 浏览器二进制和冻结配置不变 |
| 新退出层候选 | `browser-platform/camoufox:0.5.6-beta.30-r6-c73fa18044baad73`；image ID `sha256:4d70427976d5885ad157de0c57f3350df4756977c450e4df9d671bbe2e8c1b69` |
| 新候选产物 | `env-tw-camoufox-r6`；SHA-256 `a6b20fe6fe5deaa2c6932f172757ba0c3830f2c0b128fe2c3841fe31c472655f` |
| 完整产物验收 | `infra/camoufox/evidence/acceptance-r6-2026-09-14.json`；SHA-256 `3d15183917b6fedccc9990b47111d283bdf2d937efc28c988f9c16a94e841709`，PASS |
| QA 范围 | Debian 12、独立控制服务/Adapter/Observer、正常 X11 浏览器、独立命名 Home 与 Guard/Relay；私有权威 DNS 与私有测试证书 |

详细材料根目录为被 Git 忽略的 `infra/sealskin/runtime/r5a-proxy-protocols-2026-09-14/`，下文路径均相对该目录。运行目录包含敏感 QA 材料，公开报告只记录脱敏结论及摘要。

## 上游矩阵

内部始终为 Worker → 专属无认证 SOCKS5 → Relay。HTTP/HTTPS 上游对所有 TCP 目标使用 CONNECT，包括 HTTP 网页的 80 端口；HTTPS 在冻结的 IP 上验证原代理主机名、证书链和有效期，最低 TLS 1.2。

| 上游 | 认证 | HTTP/HTTPS 网页及 WS/WSS | 独立网络检查 | 证据 |
| --- | --- | --- | --- | --- |
| SOCKS5 | none | PASS | 11 PASS | `matrix-v8/socks5-none/` |
| SOCKS5 | username_password | PASS | 11 PASS | `matrix-v8/socks5-username_password/` |
| HTTP | none | PASS | 11 PASS | `matrix-v8/http-none/` |
| HTTP | basic | PASS | 11 PASS | `matrix-v8/http-basic/` |
| HTTPS | none | PASS | 13 PASS | `matrix-v8/https-none/` |
| HTTPS | basic | PASS | 13 PASS；容器级即时写入恢复 PASS | `matrix-v7/https-basic/` |

70 项网络检查使用正常浏览器、Guard 规则、抓包方向和受控目标观测。覆盖直接 IPv4/IPv6、Docker/公网 DNS 报文、管理地址、跨 Profile、UDP443/STUN、上游/Relay 故障和后台请求/下载；HTTPS 额外验证不信任 CA 与名字不符。协议事件中域名请求与授权 DNS 查询匹配，没有把 Worker 本地解析当作远端 DNS。

六组统一使用本报告的最终控制、Relay 和 r6 Worker。汇总 `protocol-matrix-final.json` 保存各项证据 SHA-256，文件摘要为 `79b213463bd7801e48b3366b8e9c74855d02f723e681a23f02b802b39e4055fc`；`matrix-v8-version-check.json` 核对实际镜像及正式 patch 与展开源码一致。v1–v6 的失败与较早版本结果保留，不作为最终版本通过依据。

错误凭据使用三个新文件及新策略修订，不改原凭据或原策略；SOCKS5 username/password、HTTP Basic、HTTPS Basic 均返回预检 503，零 Worker、零目标请求，Relay 只记脱敏认证错误，最后经 204 stop 清空 reservation。三项 **PASS**，见 `credential-failures-v1/credential-failures.json`。

## 代码、兼容与镜像

| 检查 | 结果与边界 |
| --- | --- |
| Go 全套、race、vet | PASS；六种协议/认证、真实首尾空格、沉默握手、TLS 错误、异常头/状态、并发、取消、目标注入和预读隧道字节 |
| 总握手超时 | 保留旧实现失败 `relay-timeout-baseline.log`；修复验证在 `relay-tests-v1.log`、`relay-race-vet-v1.log`，见 DEV-005 |
| 策略规范化 | 原固定 SHA `08aaebc573ac1d9b72c0db4948f3362028849b8a15dbc557dabc5e06608d971a` 回归通过；只读核对两个现存生产策略，新旧规范字节和 SHA 完全相同 |
| 旧 schema 生命周期 | 新 Relay/控制代码下六项真实检查通过：并发、双 Profile、阻断、故障、控制器重启、停止清空 |
| 最终控制 payload | Python 3.14 的 181 项测试 PASS，含正常退出失败保留、重试及真实 Docker SDK 参数序列化；`python-container-tests-v4.log` |
| 镜像不覆盖 | 独立 Relay 重复构建复用；不同输入的原 `relay-v1` 标签拒绝覆盖；旧 image ID 保持；standalone/guarded 二进制 SHA 相同 |
| 凭据边界 | 文件单值/权限/链接/长度检查及准确认证字节通过；这仍是受限文件引用，不是 R5B Secret Store |

新控制策略与原 generation 不热切换。显式协议要求相应 Relay 能力标签；旧镜像拒绝接收新协议字段。TLS 不提供跳过验证选项。日志没有输出代理凭据、原始认证响应或目标完整 URL。

## 即时写入与退出偏差

[DEV-008](../../docs/deviations/DEV-2026-09-14-008-resume-storage-observation.md) 保留了恢复后最近 localStorage 标记缺失的失败。独立诊断确认：旧标记可恢复，刚写入并读回的新标记在普通 Docker stop 后缺失；延长超时或只给浏览器父进程 TERM 均不能解决，正常应用关闭则可保存。

显式 API 的新关闭步骤已通过真实检查：页面 `beforeunload` 阻止关闭时，12 秒后返回 503，Worker/Guard/Relay 与占用保留；取消对话框后重试正常退出，再创建新 Worker，立即写入的 Cookie/localStorage/IndexedDB 全部恢复。最终证据为 `browser-shutdown-v2/`，使用 r6 和最终控制 payload；较早的 r5 `browser-shutdown-v1/` 结果单独保留。

r5 的 longrun `finish` 钩子仍不能保证桌面依赖在浏览器保存期间存活，`matrix-v6` 保留失败。r6 改为依赖桌面/D-Bus 的 s6-rc oneshot `down`，原桌面退出脚本保持不变。`matrix-v7` 验证服务已启用，即时写入后真实 `docker stop -t 30`；离线上游阻止 Worker 恢复，恢复上游后同一 Worker/Guard/Relay 按序启动，最近 localStorage 标记仍在，PASS。进程消失、容器退出码 0 或钩子成功均未被单独用作数据恢复证据。

r6 完整产物验收包括 17 项测试、11 类启动拒绝、两 Home 各 10 次删除重建及离线恢复；环境差异为空，浏览器二进制、BrowserForge 结果、resolvedConfig、preferences 和 seeds 保持。该重放使用原工具的静态 `browser-platform-personal` 网络、既有 Relay 和独立 QA Home；它与上面的独立 Guard 协议矩阵是两套拓扑，不互相替代。部署准备器另在宿主机运行测试，Worker 单元阶段只运行环境产物测试，不挂入完整仓库。

## 边界、生产与收尾

- DIRECT、公开权威 DNS/真实 TTL、出口地区/环境一致性实时报告仍属 R5C；未声明成功 HTTP/3、启用的 WebRTC/ICE/TURN、SOCKS UDP/BIND、NTLM/Kerberos/Digest 或客户端证书。
- Secret Store 授权/轮换/撤销/加密恢复属 R5B，后续候选代码和独立 QA 结果见 [R5B 验收](secret-store-acceptance-2026-09-14.md)，不改变本报告当时的文件引用范围。最终入口及 Session 授权/各层脱敏属 R5D；相关 S 组尚未整组通过。
- R2 的生产维护、真实 Home 备份、linger、整机启动窗口与 Debian 13，R4B 的 Mac/Trilium 和真实入口切换仍未完成；原 v0.1 Chromium 要求仍保留。
- 本次未部署生产。2026-09-14 06:15 UTC 的 `production-comparison.json` 确认四个生产容器的 ID、image ID、启动时间与 PID，以及 Adapter 配置、安装应用、策略 registry 和 journal 的 SHA 与开始前完全一致；原 Worker、真实 Home 与绑定保留，旧镜像仍可查找。
- `qa-cleanup.json` 与 `qa-extra-cleanup.json` 确认 Session/generation/网络占用清空，QA Controller、Adapter、proxy、上游与 Observer 已移除，临时密钥、QA 存储及匿名卷清理；六个重放 QA Home 删除前已核对无容器挂载。报告、日志及失败历史保留在私有证据目录。
- 文档相对链接/锚点、示例、`git diff --check` 与公开变更的敏感字面值检查通过。R5A 收尾后开始 R5B；R5 父条件和全部发布限制继续保留。

复现使用 [网络 QA 准备与约束](lifecycle/README.md#验证与范围)、`checks/check-proxy-protocols.py`、`checks/check-proxy-credentials.py` 与 `checks/check-browser-shutdown.py`；同一桌面的检查顺序执行。恢复镜像时保留原产物与成功报告；回退新控制 payload 前先以支持新协议/正常退出的版本确认相关 generation 清空，再恢复匹配的旧 schema 和应用引用，不恢复旧 journal 来解除占用。
