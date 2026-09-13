# Camoufox r4 阶段验收 — 2026-09-12

[验收索引](../../docs/acceptance/README.md) · [当前进度](../../docs/progress.md)

本次完成固定 Camoufox 环境、完整重放、独立 QA Home 的存储恢复及 SealSkin 正式 X11 Worker 集成。现有 Personal/Work 应用和 Home 保留原绑定。此记录不代表整个 Profile 服务、跨版本迁移或实际 Trilium Desktop 已通过验收。

## 版本与不可变绑定

| 项目 | 本次值 |
| --- | --- |
| 主机 | Debian 12，Docker Engine 29.8.0，Compose 5.5.1 |
| Camoufox / BrowserForge | 0.5.6 / 1.2.4 |
| BrowserForge 数据包 | apify_fingerprint_datapoints 0.15.0 |
| Python / Playwright | 3.14.4 / 1.62.0 |
| 浏览器发布 | v152.0.4-beta.30，Linux x86_64 |
| 浏览器归档 SHA-256 | `5720d45b894ce1770543de024c6f10d514b38be560fa2dc3226b3d8586caf672` |
| 基础镜像摘要 | `sha256:7e3dbebd9e730952648b8c902ce90fa72c0e2be3e786ab17026c38e0909b47f7` |
| Worker 标签 | `browser-platform/camoufox:0.5.6-beta.30-r4` |
| 实际 Worker image digest | `sha256:8c9aa0a2734625f5963bb12325c62cf973ea42c70b8a23bb7c4f9d0652b20a34` |
| 环境 ID / 修订 | env-tw-camoufox-r4 / 4 |
| 环境产物 SHA-256 | `09ca10fb86301fc34c7d5a352e7ecf84177c11073d671022092a48c693ad5a78` |
| 完整成功报告 SHA-256 | `6d89721b7590a48dbed5625fe473db09e3fda475c6c3bb213a79c436d234ca4f` |
| 重放测试源码摘要 | `b8a6df5ea1d27b846778c01ae9f00ee4cfa0d92f10af3d308fe68abac4972ff0` |
| SealSkin 应用 | camoufox-personal-r4；auto_update=false，仅授权 profile-adapter 用户 |

完整重放执行于 20:25:30–20:28:13 UTC，由 `browser-platform-camoufox-acceptance-r4.service` 托管，终态退出码 0。机器报告为 `evidence/acceptance-r4-2026-09-12.json`，产物为 `artifacts/env-tw-camoufox-r4.json`。两者按精确字节绑定；这些目录被 Git 忽略，迁移部署必须单独保存原文件和镜像。

依赖锁覆盖全部 36 个 Python distribution。产物保存完整 12 个 BrowserForge 结果区段、50 个 resolvedConfig 字段、三个 seeds、80 个字体和 131 个语音，以及包版本、浏览器文件清单、适配器源码与镜像绑定。r1–r4 没有重新生成设备配置或 seeds；r4 与 r3 的完整 BrowserForge、resolvedConfig、Firefox preferences 相同。

## 核心验收

| 检查 | 结果 | 实际证据 |
| --- | --- | --- |
| 产物与版本测试 | PASS | 17 项 unittest，包含完整字段、固定种子、版本、摘要与报告门禁 |
| 正常入口负向检查 | PASS | 11 类错误均在 `/init` 前被拒绝 |
| Home A / B 隔离 | PASS | 首次访问均为空，各写入不同 Cookie、LocalStorage、IndexedDB 标记 |
| 每个 Home 删除重建 10 次 | PASS | 两个 Home 共 22 次初始/重建观测，存储标记分别恢复，环境差异列表为空 |
| 离线备份恢复 | PASS | 停止测试 Worker 后复制 Home，恢复到第三个路径；第 23 次浏览器运行读取原标记且环境一致 |
| 启动不调用生成器 | PASS | 重放导入保护拒绝 Camoufox、BrowserForge、数据生成包；实际无生成器导入 |
| 浏览器导航 | PASS | 自建页面的后退、前进、新标签页与存储读取 |
| 浏览器代理路径 | PASS | 初始 A/B 的真实 HTTPS example.com 返回 200 |
| Worker 网络基线 | PASS | Relay 别名可解析；公网 DNS、直接 IPv4/IPv6 数值地址连接失败 |
| 正式 SealSkin GUI | PASS | 使用未覆盖的镜像入口；正常 `/init`、Openbox、Selkies、Camoufox 启动并打开请求的 example.com |
| 正式 GUI 环境 | PASS | `check-gui.py` 在页面执行域观测，全部字段与重放参考一致 |
| 正式挂载/资源 | PASS | 产物与报告只读，保留单一独立 `/config` Home；1536 MiB、1.5 CPU、256 MiB shm、512 PID、no-new-privileges |
| 公网授权跳转与 TLS | PASS | 修正前置 Caddy 的 Host 转发后，授权链全程保持 mysession.azhen.de，HTTPS 校验开启，Session UI 返回 200 |
| Selkies 真实串流 | PASS | 独立 Chromium 151.0.7922.34 客户端接收画面；保存截图，报告计数为 2 个 WebSocket 连接、638 个接收帧，其中 614 个二进制帧 |
| Unicode 输入/剪贴板往返 | PASS | 使用 Selkies 虚拟键盘输入接口、剪贴板面板和实际键盘事件，服务器返回完整 `camoufox-繁體中文剪貼簿` 文本 |
| Web 客户端缩放与重连 | PASS | 客户端 1920×1080 → 1280×720 → 1920×1080，刷新后重新接收画面；随后复验 Worker 全部环境字段仍与冻结参考一致 |
| 原会话保留与清理 | PASS | 原两个应用记录及 Worker ID、配置、启动时间摘要一致；所有 Camoufox smoke 容器和临时 Session URL 文件已清理 |

11 类拒绝为：缺失产物、错误 SHA、时区漂移、Wayland 漂移、版本不匹配、缺失 Audio seed、直连代理配置、未支持能力、缺少完整成功报告、启用 baseline fingerprinting 随机化、启用异步字体回退。

重放测试通过显式 QA 入口访问候选产物；正常镜像入口和 GUI 启动器都要求成功报告。单独 unit/negative/replay 阶段或少于 10 次重建的报告不能启用 Worker。

## 页面观测

| 字段 | 实测 |
| --- | --- |
| locale / languages | zh-TW / zh-TW, zh, en-US, en |
| Accept-Language | zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7 |
| Intl timezone | Asia/Taipei |
| OS / UA | Linux x86_64 / Firefox 152.0 |
| screen / DPR | 1920×1080 / 1 |
| 初始 outer / inner | 1600×900 / 1600×844，正式 X11 与重放一致 |
| hardwareConcurrency | 8；与 1.5 CPU quota 分开记录 |
| navigator.deviceMemory | undefined，不把 Docker 内存额度伪装成网页 RAM 字段 |
| WebRTC | RTCPeerConnection 为 undefined |
| WebGL | Intel / Intel(R) HD Graphics 400, or similar；maxTextureSize 8192 |
| 语音 | 等待完整加载后 131 项，逐项一致 |
| 繁体文字形 | 文本宽度 230，像素及编码结果一致 |
| Canvas PNG SHA-256 | `191a587c6c7d2dad2ecbc9a936d35cafca1041db47d628a92a951e9b69aea475` |
| Canvas 像素 SHA-256 | `03f67fdb424d6f020c0b6c1c990505bbdfd0bcf8dc313d3739d6bf5a0043cb5b` |
| Audio SHA-256 | `85ea7c65d60279c87ac64ce95790a933f6b0404633276d9408c47d78e7faa10e` |

这些是固定版本、资源和受控页面下的观测，不保证跨引擎升级、任意硬件或第三方网站策略仍完全相同。出口 IP 属于实时网络观测，没有写回产物或公开到文档。

## 已定位并修正的问题

1. r2 的 Canvas PNG 含随机 `deBG` 元数据。Firefox 152 的 `privacy.baselineFingerprintingProtection` 独立于旧 RFP/FPP 开关，r3 起在原生 preferences 中关闭这组额外随机化；Camoufox 自身设备参数和 seeds 继续冻结。
2. 异步 CJK 字体回退会产生缺字方框与文本宽度差异，固定 `gfx.font_rendering.fallback.async=false` 后通过新 Home 完整重建。语音列表在探测中等待 131 项就绪后再采样。
3. Playwright 默认隔离执行域不能代替网站执行域。测试改为自建页面脚本计算结果，通过 DOM 读取；没有新增永久 navigator/fingerprint hooks。
4. r3 的 Openbox 通配规则强制最大化，造成真实 innerWidth=1920、冻结 outerWidth=1600。r4 增加 Camoufox 原生窗口规则，正式桌面和重放均回到 1600×900 / 1600×844。

r2 失败记录、r3 核心通过但窗口不匹配的诊断仍保留为历史证据；当前应用只绑定 r4 成功报告。

真实 HTTPS 客户端验收还发现前置 Caddy 2.11 的 HTTPS 上游 Host 重写问题：SealSkin token 交换生成 `https://127.0.0.1:8443/...` 跳转。只检查公网根路径 200 无法发现该错误。已在 `/etc/caddy/Caddyfile` 的 Session 反代增加 `header_up Host {host}`，保留内部 CA 校验，备份原配置、验证并热加载。旧配置备份为 `/etc/caddy/Caddyfile.browser-platform-before-host-fix-20260912`；记录见 `evidence/caddy-host-fix.json`。修正后没有关闭浏览器 TLS 校验。

最终 Web 客户端报告为 `evidence/stream-r4d/stream.json`，截图为同目录 `session.png`；实际执行时间为 21:23:55–21:24:08 UTC。正式 GUI 初验和缩放后的复验分别为 `evidence/sealskin-gui-r4d-2026-09-12.json`、`evidence/sealskin-gui-r4-after-stream-2026-09-12.json`。这里验证的是 Chromium Web 客户端与 Selkies 虚拟键盘路径，没有把它扩写为用户系统 IME 或 Trilium Desktop 已通过。

## 接入与保留边界

应用通过加密管理员 API 创建为新 ID；现有 Firefox 应用没有被覆盖。额外 Docker `mounts` 保留 SealSkin 原有 Home `volumes`，并只接 Personal internal 网络。当前 Camoufox smoke 使用专用 ephemeral Home；没有创建长期 Camoufox Profile 入口或迁移真实用户数据。

`evidence/pre-sealskin-integration.json` 保存原 Personal/Work 应用记录和两个运行中 Worker 配置的摘要，用于接入后的保留检查，不包含密钥或 token。smoke 工具只输出 Session ID；自动化消费 URL 的临时文件权限为 0600，退出时删除。每次停止后需核对 Docker 中对应 Worker 已消失。

最终核对见 `evidence/integration-final-2026-09-12.json`：原应用/Worker 摘要一致，新增应用只有 `camoufox-personal-r4`，临时 Camoufox Worker 和 Session URL 文件均为 0。Adapter `/readyz`、Personal/Work 公网 GET 均为 200，Relay 和 SealSkin 持续运行。

## 尚不能由本次结果证明

- 实际 Trilium Desktop/Electron 的 cookie/SameSite、系统输入法、剪贴板、缩放和重连行为。
- 随机 DNS 权威日志、浏览器 IPv6/STUN、跨 Profile、Docker/SealSkin/VPS 重启窗口的完整网络矩阵。
- 可靠自动 stop、空闲回收、动态 Relay generation、健康 API/Dashboard 和代理轮换一致性策略。
- 真实 Personal/Work Home 的迁移、跨版本升级/回退及第三方登录保持。
- 主机退出登录或重启后的 Adapter 可用性；用户服务已启用，但主机仍为 Linger=no。

下一阶段按 [开发计划](../../docs/roadmap.md) 执行。构建、准备独立应用和重现检查的命令见 [README](README.md)。
