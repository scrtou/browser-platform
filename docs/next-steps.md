# 下一步：完成 Profile 服务的生产与客户端验收

2026-09-12 已完成 Personal 原生 Firefox 代理基线，以及独立 Camoufox 应用的冻结、重放和正式 X11 启动验收。2026-09-13 已完成 Trilium 主要交互、可靠停止与状态对账、按 generation 分配 Relay／Guard／网络，以及浏览器网络故障和控制容器重建验收；原 Work/Personal 会话保持上线。接下来优先完善健康报告与浏览器退出恢复提示，并安排正式主机重启的维护窗口。独立测试不能替代整个 Profile 服务的生产验收。

## 已完成的当前阶段

| 项目 | 实际结果 |
| --- | --- |
| 固定入口与控制面 | Personal/Work 固定入口、加密 SealSkin API、启动占用、bootstrap 对账、20 路并发复用已实现；Adapter 由 systemd 用户服务托管 |
| Personal 代理基线 | SOCKS5 Relay、远端 DNS、internal 网络、直接 IPv4/IPv6/公网 DNS 阻断；Relay 停止和上游断网时无直连回退 |
| 原生 Firefox 环境 | `env-tw-firefox-baseline-r1`，zh-TW、Asia/Taipei、1920×1080、DPR 1；启动前校验；固定 X11 |
| Camoufox 版本 | Python 包 0.5.6、BrowserForge 1.2.4、浏览器 v152.0.4-beta.30；全部 36 个 Python distribution 及浏览器归档哈希固定 |
| 完整环境产物 | `env-tw-camoufox-r4`；完整 BrowserForge、完整 resolvedConfig、三个 seeds、字体、语音、WebGL 与版本/镜像绑定；启动不再导入生成器 |
| 拒绝错误配置 | 17 项产物测试和 11 类正常入口拒绝测试通过；缺失/失败/不匹配验收报告在 `/init` 前被拒绝 |
| Home 与重建 | 两个专用 QA Home 各删除重建 10 次；Cookie、LocalStorage、IndexedDB 隔离和恢复通过；另一次离线备份恢复通过 |
| 稳定性 | 23 次浏览器运行中逐字段观测一致；Canvas、繁体字体、Audio、WebGL、131 项语音均保留检查 |
| 正式桌面 | SealSkin 创建的独立 Camoufox cleanroom 使用正常入口和 X11/Selkies；screen 1920×1080，outer 1600×900，inner 1600×844，DPR 1，与重放一致 |
| 应用集成 | `camoufox-personal-r4` 绑定实际镜像摘要、只读产物/成功报告、Personal internal 网络和指定 Session origin；使用独立 Home，禁止自动更新 |
| GUI 资源限制 | 独立 Camoufox 应用设为 1536 MiB、1.5 CPU quota、256 MiB shm、512 PID、no-new-privileges；页面 hardwareConcurrency=8 单独记录 |
| 真实 Web 串流与交互 | Chromium 151 客户端通过 HTTPS Session、画面、Unicode 虚拟键盘、中文剪贴板往返、窗口缩放和刷新重连；缩放后 Worker 环境复验一致 |
| Session 公网跳转修正 | Caddy 显式保留 Host，修复授权跳转到 127.0.0.1:8443；TLS 校验保持启用 |
| 可靠停止与状态对账 | SealSkin 固定 Home 名称/标签与确认删除；Adapter 持久化停止意图、本机运维 socket、重启续停；59 项 Python 测试、Go/race 与独立容器故障通过，原 Work/Personal 会话和进程保留 |
| Relay／网络生命周期 | 每个受管理 generation 独立分配 internal／egress 网络、Relay 和 Guard，启动前落盘占用并探测，确认 Worker 消失后回收；122 项 Python 测试、Go/race/vet、18 项真实 Docker 场景通过 |
| 管理网络与浏览器出站 | Guard 阻断 Worker 主动访问同网段管理 API；11 项真实 Firefox 检查、私有权威 DNS、14 条直接路径阻断、故障下载与后台请求、真实 Personal 上游验证通过 |
| 控制容器与独立 daemon 恢复 | 控制容器重建接回原显示地址，Firefox 原进程保留；独立 Docker 29.8.0 的 live-restore 和 Guard 先行恢复通过，正式主机仍未重启 |

证据分别见 [Camoufox 验收记录](../infra/camoufox/acceptance-2026-09-12.md)、[SealSkin 验收记录](../infra/sealskin/acceptance-2026-09-12.md)、[网络隔离与恢复验收](../infra/sealskin/network-isolation-acceptance-2026-09-13.md)、[网络生命周期基线](../infra/sealskin/network-lifecycle-acceptance-2026-09-13.md) 和 [源码审计](sealskin-0.3.2-audit.md)。实现与重现命令见 [Camoufox](../infra/camoufox/README.md)、[Adapter](../adapter/README.md)、[Relay](../relay/README.md)。

现有 Personal/Work Session 及 Home 仍使用原 Firefox Worker。Personal 的 `personal-socks5-r2` 动态网络策略和代理环境会在下次新建会话生效；Camoufox 使用单独应用及保留的静态 Relay，未切换既有固定入口。QA Home 的恢复记录不代表已经迁移或修改真实用户 Home。

## 1. 实际 Trilium 客户端

2026-09-13 已修复固定入口自动 POST 的 `Origin: null` 与 Session 重定向 CSP 问题；Personal/Work 均通过 Chromium 公网入口 → Session 页面回归，见 [入口验收](../infra/sealskin/entry-acceptance-2026-09-13.md)。用户在 **Trilium 0.105.0、macOS Sequoia 15.1** 上确认两个入口可查看、中文输入正常、缩放滚动正常、会话可恢复，并已确认手动 Clipboard 面板双向文本传递通过。该版本的 WebView 拒绝程序读写系统剪贴板，自动同步尚未启用；按 Session origin 授权需要定制客户端，当前只完成方案核对，见 [客户端记录与权限方案](trilium-client.md)。

Files 栏已按用户要求为两个入口开启，PNG 按钮上传通过独立 Wayland 会话验证，Mac / Trilium 文件选择仍待用户复测。两个现存 Worker 实际仍是旧 Wayland；本次 Work 的初始串流重载曾连带重启 Firefox，最终采用无需重启的页面更新，并持久化后续启动配置，详见 [Files 开启记录](../infra/sealskin/files-sidebar-acceptance-2026-09-13.md)。

用户进一步要求截图无需本机保存即可上传，现已为 Personal / Work 加入 **⌃⇧⌘4 截图到剪贴板 → 远程网页 ⌘V** 的原生粘贴入口。旧 Wayland 与代理 X11 隔离会话通过图片完整性、中文文本及取消/断线/只读拒绝验证；新会话与一次性 QA Worker 重启通过静态资源核对。此次部署未重启现有 Worker 的任何浏览器、桌面或串流进程，未更改 Trilium 剪贴板权限。用户随后在 Mac / Trilium 上确认截图测试正常，目标客户端验收通过，见 [截图粘贴记录](../infra/sealskin/screenshot-paste-acceptance-2026-09-13.md)。

用户也确认本机文字可用原生 ⌘V 粘到远程。为补齐反向，现已部署 **远程选中文字 ⌘C → 等待成功提示 → 本机 ⌘V**；等待超时或内容未变化时提示再次按 ⌘C。实现只更新 Selkies 前端，Trilium 权限策略保持原样。X11 / Wayland、原生 Copy 事件、1.2 MB 文本、取消与权限限制均通过隔离验证，原有截图粘贴通过回归；两个旧 Worker 的所有原进程与绑定保留。新应用只更换两个客户端只读挂载的版本路径，新会话与一次性 QA Worker 重启核对通过。**用户已在 Mac / Trilium 上确认反向文字复制主流程可用**；大文本和异常等分项仍以隔离测试为证据。远程右键“复制”、网页复制按钮和 Control+C 只更新远程剪贴板，不会自动写入 Mac。见 [反向复制记录](../infra/sealskin/native-copy-acceptance-2026-09-13.md)。

补充显示缩放比例和具体输入法，并记录 screen/DPR 固定与输入坐标一致的观测。继续验证后退、前进、标签页、非文本剪贴板和明确的断线重连场景；现有反馈不代替这些分项记录。

本机 GUI、Playwright 和 Selkies Web 客户端测试不能替代 Trilium 的 cookie/SameSite、系统 IME 与嵌入行为。永久笔记只保存固定 `/browser/personal/` 地址，不保存一次性 token。Camoufox 正式 Profile 需要新命名 Home；在验证前继续保留既有 Personal/Work 绑定。

## 2. 网络验收剩余边界与主机维护窗口

v2 已修复同网段 SealSkin `8000/8443` 可达问题，完成 Guard ACL、私有权威 DNS、浏览器 HTTPS/WebSocket/AAAA、直接 DNS/DoT/STUN/UDP443、页面 DoH 经代理和断网下载／后台请求检查。控制容器重建保持真实 Firefox 原进程并接回显示网络；上游 hosts 映射变化与内网 IP 复用也有独立证据。

按 [设计第 48.5 节](design.md#485-首版网络故障验收)，正式 Docker/VPS 重启、真实 Firefox 整机恢复及开机窗口仍需在维护窗口验证。独立 Docker 29.8.0 检查使用合成 Worker、VFS 和无外部网络的容器；Relay／Guard 为 `restart=no`，没有新增生产自动开机恢复。公开委派 DNS／商业上游解析日志、真实 DNS TTL 轮换、成功 HTTP/3 协商和启用 WebRTC 后的 ICE 行为也不在此次证据范围内。详见 [验收边界](../infra/sealskin/network-isolation-acceptance-2026-09-13.md)。

继续验证 HTTP/HTTPS/SOCKS5 与认证组合。当前实现已验证固定 SOCKS5 上游；规格中的其他代理协议仍是后续工作。

## 3. 可靠停止、健康与运维

2026-09-13 当前发布为 `0.3.2-network-v2-e13c19eedc38245d`，包含可靠停止、Guard 网络隔离和控制容器接回。新 Worker 使用固定 Home 容器名及 Profile/operation 标签；停止先落盘，确认所有 Worker 消失后删除记录并清理 Guard／Relay／网络，全部资源消失后 Adapter 才提交 `stopped`。Adapter 经本机 `0600` socket 执行 inspect/stop/reconcile，失败保留占用，重启会继续已持久化的停止；SealSkin 界面直接停止留下的网络清理也可续接。旧无标签 Work/Personal 已精确对账并保持原绑定和全部浏览器、桌面、串流进程。

独立实测覆盖 20 路并发、假 stop 204、stop 500、Docker 查询失败、Adapter SIGKILL 续停、重复停止、Home 保留、旧 generation 拒绝、SealSkin 重启后的有标签孤儿，以及无标签孤儿拒绝自动清理。新增网络删除失败、异属端点阻断清理、create 响应丢失恢复和策略漂移拒绝，见 [网络生命周期验收](../infra/sealskin/network-lifecycle-acceptance-2026-09-13.md)、[此前停止验收](../infra/sealskin/lifecycle-acceptance-2026-09-13.md) 和 [运维说明](../infra/sealskin/lifecycle/README.md)。受管理网络已有 create 前占用日志；普通非策略会话的完整启动日志、自动空闲回收、Docker/VPS 重启窗口和活跃 Home 删除保护仍需补齐。

实现绑定实例和配置修订的健康报告、过期状态、出口观测与地域一致性策略、启动并发和资源调度。当前冻结产物没有因实时 IP 而自动重选语言、时区或 seeds；设计中的健康 API/Dashboard 尚未由本次 Camoufox 工作实现。

2026-09-13 已确认浏览器退出与 Worker 存活是不同状态：用户关闭 Work Firefox 后，入口继续复用 Session，呈现空桌面。已在原用户、原 Home 和原桌面中重开 Firefox，确认窗口可见且其余进程与绑定保留。当前 Work / Personal 均保留桌面右键菜单中的 **FireFox** 启动项，用户可自行重开。后续需补充浏览器存活检测及入口中的恢复提示；当前没有自动重开机制。见 [客户端恢复记录](trilium-client.md#关闭远程-firefox-后出现黑框)。

主机上 Adapter 用户服务当前可用，但 `loginctl enable-linger sshUser` 返回 `Access denied`，`Linger=no`。退出登录与主机重启持久运行仍需管理员启用 linger 或改成系统级服务后验证。当前主机为 Debian 12；正式目标 Debian 13 需记录独立验收结果。

## 4. 迁移、恢复和发布门槛

对真实 Home 做关闭浏览器后的备份演练，连同精确镜像、环境产物、成功报告和所需密钥保存。跨引擎迁移创建新 Home，不把原 Firefox/Chromium Home 直接交给 Camoufox。当前只验证同一固定浏览器的离线恢复；跨浏览器发布升级、回退和第三方登录保持尚未验证。

完成入口鉴权和 Trilium 客户端证据；代理凭据从当前主机 `0600` bind mount 转入受控 Secret Store/运行时注入。管理私钥、上游密码和 Session URL 均不得进入 Git 或验收文档。

只有 [design.md 第 44 节](design.md#44-当前版本完成标准) 及各 P/N/E/C/H/S 组要求的运行记录明确列为 PASS，才提升整体版本状态。本次 Camoufox 冻结环境和独立应用通过，不等于 v0.1/v0.5 的全部功能均已完成。
