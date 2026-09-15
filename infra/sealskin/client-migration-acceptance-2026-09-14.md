# R4A 客户端与 Camoufox 迁移准备验收

[验收索引](../../docs/acceptance/README.md) · [工作项](../../docs/work-items/R4A-2026-09-13-client-migration-qa.md) · [客户端矩阵](../../docs/client-matrix.md)

2026-09-13 至 2026-09-14 UTC，在 Debian 12 的独立 QA 控制器、用户、Home 和 Guard 网络中完成 R4A。Linux 客户端边界、剪贴板回归、Camoufox 受管理网络和停止重建通过；迁移候选文件已生成。**未切换生产入口，未把 Linux 结果视为目标 Mac/Trilium 通过。** R4B、R2 的维护条件和整体发布门槛仍保留。

## 固定身份

| 对象 | 值 |
| --- | --- |
| QA 控制 payload | `0.3.2-lifecycle-v2-a8c7be8a22ededd3`，与当前控制服务代码一致 |
| 浏览器 | Camoufox `v152.0.4-beta.30`，正常 X11 启动入口，无调试端口 |
| Worker image | `sha256:8c9aa0a2734625f5963bb12325c62cf973ea42c70b8a23bb7c4f9d0652b20a34` |
| 环境产物 | `env-tw-camoufox-r4`；SHA-256 `09ca10fb86301fc34c7d5a352e7ecf84177c11073d671022092a48c693ad5a78` |
| 原完整环境验收 | SHA-256 `6d89721b7590a48dbed5625fe473db09e3fda475c6c3bb213a79c436d234ca4f`，本次没有覆盖该报告 |
| 客户端 | Chromium `151.0.7922.34` / Playwright `1.62.0` / Linux，执行 Mac 键位分支 |
| 非文本权限探针 | Electron `43.4.0` / Chromium `150.0.7871.224` / Linux；独立 `persist:webview` |
| 新客户端包 | `native-clipboard-c79102f832b141bd`；完整包摘要 `c79102f832b141bd9c2d7e2a43d3e3aaa25ccb5c12abe4c862242c99296af890` |
| 新前端 | `index-native-paste-f58142dbcb6aa1fa.js`；完整摘要 `f58142dbcb6aa1fa98d49e16e81fb7f4a90ad2683d10e939b390be49dd628d54` |

新包只修改固定前端的 Unicode code point 迭代和 composition 差异计数。图片/文字桥接脚本、浏览器、环境产物及 Selkies 后端未改。QA 的系统 locale 从错误的 `zh-TW` 修为 `zh_TW.UTF-8`；浏览器 BCP 47 语言仍是产物规定的 `zh-TW`。原部署说明已经使用正确的系统值，见 [DEV-004](../../docs/deviations/DEV-2026-09-13-004-unicode-input.md)。

## 客户端与存储

Session origin 的 Async Clipboard 读写权限为 denied，实际调用均为 `NotAllowedError`。客户端通过隔离控制器的真实 HTTPS/Caddy 与 WebSocket 连接，使用 QA 证书 SPKI pin；没有给被测 origin 授权剪贴板。完整矩阵及实机缺口见 [客户端矩阵](../../docs/client-matrix.md)。

| 检查 | 实际结果 |
| --- | --- |
| 显示与坐标 | 1920×1080/DPR1、1280×720/DPR1、1000×760/DPR2 各 5 个目标，15 次可信点击均落在目标中心 ±6 px；远程 screen 始终 1920×1080、DPR1 |
| 窗口与环境 | outer 1600×900、inner 1600×844、位置 160/90；zh-TW / Asia/Taipei；WebRTC unavailable |
| Unicode 输入 | `camoufox-繁體中文😀𠮷` 完整到达远程输入框 |
| 组合文字 | `KEEP:` 前缀后从 `😀a` 更新为 `😀𠮷` 并提交，最终 `KEEP:😀𠮷`；CDP start/update 可信，commit 的 compositionend 为 untrusted，不能证明原生 OS 输入法 |
| 导航、标签页、滚动 | 后退/前进、新建/切换/关闭测试标签页及滚动通过，测试 Cookie/LocalStorage/IndexedDB 一致 |
| Files | Linux 原生选择框自动选取、可信 CDP 文件拖放均上传 126 字节 PNG，真实 QA Home 中 SHA-256 匹配；不等同 Finder 操作 |
| 连接恢复 | 主动断开显示 WebSocket 后重载；离线重载失败后恢复网络再打开。均获得新视频帧与连接，原 Worker、Session 绑定和数据保留；不声明无操作自动重连 |
| 反向文字 | 中文/emoji、1,200,015 字节分块文本、同值确认、Edit/Copy、迟到/过期/旧回声、焦点取消、单向配置、断线和只读回归均通过 |
| 本机截图/文字 | 原有小图/分块 PNG 的完整像素校验、中文文字、面板、Command 组合、确认丢失与取消、禁用/合成事件/断线/只读回归均通过 |
| 停止重建 | 通过 SealSkin stop 确认旧代次全部释放，再由正常入口创建新代次；同一 QA Home 的 Cookie/LocalStorage/IndexedDB、固定镜像与环境恢复，新包由 init hook 自动安装 |
| 资源 | 新旧 QA Worker 均为 1536 MiB、1.5 CPU、256 MiB shm、512 PID；未把页面硬件参数当作容器资源限制 |

一次自动化导航得到不完整地址；工具增加输入连接就绪检查与地址栏聚焦等待后复测通过，该次失败没有完整键值记录，不能进一步追认根因。大写前缀改为真实 Shift 组合，CDP commit 的实际信任标记保留在报告中，没有改成“Mac 输入法通过”。早期失败目录仍保留。

## 非文本能力决定

Electron 探针采用 Trilium 对 guest 仅允许 fullscreen 的权限规则，`nodeIntegration=false`、`contextIsolation=true`、WebView `sandbox=true` 配置；**该隔离容器使用 `--no-sandbox`，没有验证实际 Chromium OS sandbox，也没有运行完整 Trilium UI**。

原生 Copy 可以写入 text/plain 和 text/html。把 PNG File 加到 `clipboardData.items`、把 Base64 文本写入 image/png、image/jpeg、image/webp、image/bmp 或 application/rtf MIME，均未产生系统可读 bitmap；选择 DOM img 再原生 Copy 得到 HTML，也没有 bitmap。MIME 名称存在不代表图片传递成功，这些结果也不证明所有平台或其他合法编码方案都不可行。

本阶段维持**远程→本机仅纯文本、单次 25 MiB 上限**。反向图片、富文本、RTF 与其他二进制未交付；HTML 探针可行不等于远程桥接支持。当前 Files 只上传，不能把它宣称为已交付的远程下载替代入口。后续若需要非文本导出，优先单独设计经授权的文件下载路径；不为此开放 Trilium 全局剪贴板权限。

## Camoufox 网络

11 项真实浏览器检查全部通过：HTTPS/WebSocket/AAAA-only 经 SOCKS5 域名请求与私有权威 DNS，页面 DoH 仍走代理；WebRTC 关闭，WebTransport 与 IPv6 literal 不建立直连；14 条直接网络路径拒绝；Relay 只允许批准的上游；offline、bad-auth、relay-stop 时后台请求和下载失败，原浏览器进程保留；SealSkin API 重启后原浏览器继续可用。

最终抓包记录 84 条出站流、826 个包，均符合 Relay TCP 或显示回复白名单；另记录 1 类收到的 IPv6 组播。采集使用 AF_PACKET 内核方向，受控的 3 个组播报文验证收到的 packetType=2 不属于 PACKET_OUTGOING。原失败包没有方向字段，不能追认其来源；本次修复采集后的完整重跑才是通过依据，见 [DEV-003](../../docs/deviations/DEV-2026-09-13-003-packet-direction.md)。

本结果仍使用私有 QA DNS/上游，不覆盖公开权威 DNS/TTL、真实商业代理解析日志、成功 HTTP/3、启用 WebRTC/ICE/TURN、正式 Docker/VPS 重启。N01–N08 不因此整组通过。

## 迁移准备与回退

[prepare-migration.py](../camoufox/prepare-migration.py) 只读当前配置、加锁读取 journal、查询 Adapter 运维 socket 和 Docker Home 挂载，再验证固定镜像中的产物/报告，生成私有候选文件。8 项应用/迁移准备测试通过；安装器升级、幂等、旧包回退后重新升级、未知/篡改拒绝检查通过。

当前准备的 Personal 变更为：`personal` / `firefox-personal` → 新 Home `personal-camoufox-r4` / 新应用 `camoufox-personal-r4-guard`；新策略 `personal-camoufox-r4-socks5-r1`，摘要 `73e6b915d0f201153bbf9f3ff36293f2822e15e7a5e6fdaf51bc910203388052`。旧策略全部保留。候选 App、Adapter 正向/回退配置和 registry 均已写入私有目录，**没有安装或替换生产文件**。

准备报告分别记录当前定义、旧代次实际 image/启动身份、旧绑定、产物/验收摘要与新定义。旧代次实际没有 Guard，不能把当前配置中的 r2 策略视为已生效。回退配置恢复本次准备时的 Firefox 定义，并在 stop 后创建新代次；它不会复活原 Session 或回滚整个 journal。真正切换与回退均需 R4B、备份与维护核对，步骤见 [运维说明](../../docs/operations.md#camoufox-入口切换与回退准备)。

## 证据与收尾

私有根目录：`infra/sealskin/runtime/r4-client-migration-2026-09-13/`。主要文件及 SHA-256：

| 文件 | SHA-256 |
| --- | --- |
| `client-boundary-v6/client-boundary.json` | `92e78de1de7f703d9e170ecacab38e5834b2bec51ca12f714edab157f7bbaead` |
| `native-copy-unicode-v1/native-copy.json` | `14ae5dd60b0e50ab1fc3b6630598cf7e4360f9f3b17adeb5da76ccecab42d5aa` |
| `screenshot-paste-unicode-v1/screenshot-paste.json` | `4ddc47657e4335842d3c02af2de7961db317bc0af529c8a1c630119d00274b93` |
| `capabilities/clipboard-capabilities.json` | `da0c2b0c8ce0268afd5e25f8d19a1d1cbeb8933271337188041f46666b8a4ca6` |
| `rebuild-v1/rebuild.json` | `56c6c8be89718f1ffc50c958ed1667b25023c87601d838c1c66cbbf036376951` |
| `network-v2/browser-network-results.json` | `708ce7c5f69ad5e5902dc1e1bfc0049f791683e161af4be0b1d321cd60ba5025` |
| `network-v2/browser-wire.jsonl` | `9a97861255b8ebd5d21cbff9b059a9d98d28ae8b1c94e18e40c40cad7e0efd42` |

`migration-preparation-v2/` 保存当前迁移候选；`production-before.json` 与 `production-after.json` 的 4 个容器身份/启动时间/PID、Adapter 配置/journal、应用定义摘要完全一致。`qa-cleanup.json` 已确认 generation、QA 容器/网络为 0，控制器/代理停止，临时密钥和 QA 数据清除。最初清理工具假定 QA Adapter 已启动；本次仅用 SealSkin API，修正为先验证不存在对应 QA 进程，再清理。新客户端包只在 QA 使用，生产两个旧 Wayland Worker 与独立 Camoufox 应用仍保持之前的版本。23 个 Python 文件语法、30 份变更 Markdown 的 502 个本地链接/锚点与 `git diff --check` 通过，候选/回退配置加载及只读绑定检查通过。
