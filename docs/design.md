# 当前架构与设计决策

[文档导航](README.md) · [开发背景](background.md) · [开发进度](progress.md) · [开发计划](roadmap.md)

本页描述当前采用的架构及其边界。具体版本、生效范围与验收结果统一见 [开发进度](progress.md)；完整接口和能力要求见 [代理与环境规格](specs/proxy-environment/specification.md)。原 1–50 节长篇设计已完整保存在 [历史快照](archive/design-v1.3-2026-09-13.md)。

## 总体架构

Trilium 通过固定 URL 进入 Profile Adapter，Adapter 调用 SealSkin 创建或复用会话。浏览器画面、键鼠与剪贴板经过 SealSkin/Caddy/Selkies 数据通道，浏览器运行在独立 Docker Worker 中。

```mermaid
flowchart LR
    T[Trilium WebView] -->|固定 Profile URL| C[前置 Caddy]
    C --> A[Go Profile Adapter]
    A -->|加密 API，创建或复用| S[SealSkin]
    T -->|HTTPS Session / WebSocket| C
    A -->|授权后的显示请求，私有 HTTPS| D[SealSkin Caddy]
    D -->|显示与输入| W[Browser Worker / Selkies]
    S -->|生命周期| W
    W --> H[持久化 Home]
    W -->|受管理代理会话| R[专属 Relay]
    R --> P[指定上游代理]
    P --> I[网站]
```

图中的显示访问边界为 R5D 候选，已通过独立 HTTPS/真实客户端验收，生产尚未切换。专属代理路径用于受管理的新 Personal 会话。现存 Work/Personal 与独立 Camoufox 的配置、生效时机不同，见 [部署范围](progress.md#deployment)。

## 组件职责与状态归属

| 对象 | 当前所有者与职责 |
| --- | --- |
| 固定 Profile 入口与配置 | Adapter：Profile ID、应用/Home/策略引用、启动前校验 |
| 启动占用、绑定与停止意图 | Adapter：持久化 journal、operation、幂等键、保守对账、容量门槛、空闲回收（可选）、本机运维 socket |
| Session 与 Docker 生命周期 | SealSkin 及本地生命周期补丁：create 前启动日志、创建、停止、资源清查、确认删除、Home 删除保护 |
| 会话授权与显示转发 | R5D 候选：Adapter 校验最终用户、Profile 与当前 Session；私有 SealSkin/Caddy 继续核对 Session 能力和一致性门槛；Selkies 处理画面与输入 |
| 浏览器数据与运行目录锁 | Worker 中的浏览器，数据放在命名 Home |
| 环境产物 | 构建/生成工具冻结版本与完整结果；Worker 在启动前验证并读取 |
| 受管理网络 | SealSkin 分配 generation 资源；Guard 安装规则，Relay 转发上游流量 |
| 上游代理凭据 | 私有版本文件只读交给 Relay，不进入 Worker、镜像、环境产物或 Home |
| Worker 显示材料 | 控制器从密封 Session 在专属 tmpfs 重建；Worker 只读自己的密码校验文件与可选协作 token，显示 TLS 私钥也留在 Worker tmpfs |
| 统一运行健康报告 | Adapter 汇总：读取 journal 绑定与 SealSkin 只读观测（进程、显示端口、Relay/Guard、上游探测），按规格计算整体状态并给出恢复提示；查询不启动或重建实例 |

当前只有 SealSkin 操作这批 Worker 的 Docker 生命周期。Adapter 不再建立第二套 Docker 编排路径，也不复制完整的 SealSkin Session 状态机。

Adapter 已使用持久化状态文件、跨进程锁、fsync 和原子替换；SealSkin 保留自身会话记录及按 Home 保存的网络占用文件。[SQLite 规格](specs/proxy-environment/schema.sql) 是未来自有元数据的参考契约，不是当前数据库，也不是 SealSkin 数据迁移脚本。

## Profile、Home 与 generation

- **Profile** 是用户长期使用的逻辑身份，例如 Personal、Work。
- **Home** 是浏览器持久化目录，保存 Cookie、网站存储、设置和恢复所需数据。
- **Session** 是 SealSkin 提供授权与显示连接的一次运行会话。
- **Worker** 是运行浏览器、桌面与 Selkies 的容器。
- **generation / operation** 标识一次受管理的启动代次，用于绑定实际资源和拒绝过期操作。

一个 Home 同时只允许一个浏览器实例使用。并发和不确定结果通过持久化占用与实际资源对账处理；`unknown` 不按 TTL 自动解锁。旧无标签会话使用 Session、Home、应用与唯一 bootstrap 上下文精确匹配，新代次还使用确定名称、标签及配置摘要。

刷新 Trilium 只重新连接或授权已有 Session。更新应用定义影响后续新会话，不会替换仍运行的旧 Worker；升级浏览器或更换网络架构需要单独处理。

## 启动、复用与停止

1. `GET /browser/{profile}/` 返回入口页，不创建会话；启用 `access` 后先验证短期登录与 Profile 授权，再由带精确 Origin/CSRF 的 `POST /browser/{profile}/start` 请求启动或复用。
2. Adapter 保存启动占用和唯一 bootstrap 上下文，先核对实际绑定。结果未知时保留占用并拒绝重复创建。
3. 受管理的 SealSkin 启动在 Docker create 前保存网络占用，按代次分配网络、Relay 与 Guard。
4. Guard 规则安装并降权、代理与直连阻断探测通过、探测容器清理后，才启动 Worker；Worker 验证环境产物并使用命名 Home。
5. Adapter 核对当前 Session 与一致性门槛，将后端能力保存在内存，向客户端发放一次性短期交接地址。兑换再次核对当前登录与业务绑定，设置专属显示 Cookie，再以 303 跳转到不含后端 token 的 Session URL；后续 HTTP/WebSocket 经 Adapter 和私有控制器授权。Note 只保存固定 Profile 入口。
6. 停止先持久化意图；支持正常退出的 Worker 先关闭浏览器并确认退出，关闭拒绝/超时保留资源。确认全部 Worker 消失，再回收 Guard、Relay、网络及占用。失败时可重试或对账；全部资源消失后才提交 `stopped`，Home 保留。

控制容器重建会先核对所有权、网络端点、配置与旧控制器状态，再按原地址接回显示网络。传统运行健康观测在 Home 锁外只读进行；R5C3 的实际浏览器采样和门槛更新沿用 Home 生命周期互斥。

R5C1 的 `profile_initial_url_version: 1` 将受管理浏览器的 HTTP(S) 初始 URL 与唯一 bootstrap 对账标记分开：`launch_context` 保留原标记，Worker 直接打开配置的起始页。DIRECT 继续拒绝宿主机地址。两个实际 Adapter 入口、重复进入和持久数据已验证；旧控制器不接收新字段，无绑定会话仍为 unknown，见 [启动中转页修复](deviations/DEV-2026-09-14-011-direct-bootstrap-url.md)。

Docker 或主机重启后，Profile 的 Worker、Guard、Relay（均 `restart=no`，不使用自动删除）保持为已退出容器，会话记录与网络占用保留，称为**休眠代次**。Adapter 启动对账或入口识别休眠代次后，由 SealSkin 按 **Relay → Guard 规则就绪 → 控制器接回内网 → 一次性探测（代理 TLS 通过且直连阻断）→ Worker → 显示端点** 的顺序恢复同一批容器；任一步失败 Worker 不启动，占用保留并标为 `unknown`。恢复从不创建或删除容器。

所有命名 Home 的启动在 Docker create 前写入启动日志，控制进程崩溃或创建响应丢失后由清单中的 `launch` 资源暴露并阻止重复启动；清单为空即证明没有创建发生。Home 删除只在会话、容器、网络占用与启动日志全部不存在时执行。空闲回收以 SealSkin 代理持有的已认证显示连接数为唯一依据：断开后计时、重连取消、到期前重新观测，再经已验证的停止路径释放；轮询、健康检查与视频帧不算活动。自动重开浏览器与整机自动开机验收仍属于 [后续计划](roadmap.md)。实现细节见 [生命周期说明](../infra/sealskin/lifecycle/README.md)。

## 受管理 Personal 的网络边界

每个 generation 有独立 internal/egress 网络、Guard 和 Relay。Guard 只接内网，在自己的网络命名空间安装 nftables 后丢弃全部 capabilities；Worker 共享这个已经受限的命名空间。

| 方向 | 规则 |
| --- | --- |
| Worker → 自己的 Relay | 仅固定内网 IPv4 的 TCP 1080 |
| 固定控制器 → Worker 显示端口 | 允许授权显示通道；允许已建立连接的回复 |
| Worker → 公网、其他 Profile、管理 API、宿主机、metadata | 默认拒绝，覆盖 IPv4/IPv6 |
| Worker → Docker DNS / 直接 DNS | 拒绝；网站域名经内部 SOCKS5 交 Relay，再以所选 SOCKS5/CONNECT 请求交上游解析 |
| Relay → 上游代理 | 仅控制器在分配时解析并冻结的 IPv4/端口 |
| 其他入站、出站或转发 | 默认拒绝 |

Worker 不获得 Docker socket、NET_ADMIN 或 NET_RAW。上游故障只使代理失败，不提供 VPS 直连回退。Guard 丢失时应停止并清理整个原代次后新建，不能单独重启 Guard 来接管仍存活的 Worker。

上表为 `proxy_required` 的本地网络约束；上游代理所在网络的目标访问范围由上游 ACL 管理。R5C1 的显式 DIRECT 候选保留相同的 Worker/Guard 约束，专属网关只允许批准解析器的 UDP/TCP 53 与通过地址校验的公开 IPv4 TCP；不创建外部 ProxyConfig 或凭据。完整域名回答、CNAME、私网/保留地址、宿主机公网地址和 53/853 目标均检查；不用系统 DNS 或 hosts，没有应用级 DNS 缓存。

DIRECT 控制器与网关只读挂载固定宿主机 procfs 地址证据，冻结本机原生公网 IPv4；NAT-only 主机不支持。网关每次连接前和每 100 ms 复核证据，丢失/变化关闭监听与已有隧道；恢复/重接再次核对配置、地址和挂载。私网拒绝前仅放行已建立 SOCKS5 连接的回复方向（[DEV-010](deviations/DEV-2026-09-14-010-direct-reply-filter.md)）。DNS 故障阻止新的域名连接，数值地址与既有隧道仍由 ACL 管理。配置和独立验收见 [DIRECT](../infra/sealskin/lifecycle/direct-network.md)。生产旧 Work 未迁移；公开 DNS/TTL 已在 R5C2 的限定 QA 环境验收；完整主机重启和一致性报告仍按 [网络规格](specs/proxy-environment/specification.md#48-dns--webrtc--egress-leak-protection) 验收。

R5C2 候选把代理端点引导 DNS 独立配置为 `bootstrap_resolver_id` / `bootstrap_resolver_ip`。批准路径只查询固定数值端点，以有界 UDP/TCP、CNAME 和完整 IPv4 校验取得回答；数值上游不执行 DNS。回答、TTL 和接收时间绑定 Home/operation/策略，恢复和控制器重接核对冻结配置与挂载。TTL 到期不更换运行端点或释放 Home，新代次才重新解析。空字段保留旧策略 SHA 及 `legacy_system` 路径，该路径不能算批准解析器通过。依赖、记录和兼容边界见 [引导 DNS 契约](../infra/sealskin/lifecycle/bootstrap-dns.md)。公开委派、三条实际解析路径和真实 TTL 已在独立标准 Unbound 与受控公网端点完成验收；该结果不推论公共递归前端只有一个缓存期限，也不代替运行时新鲜一致性报告。

[R5A](work-items/R5A-2026-09-14-proxy-protocols.md) 保留内部 SOCKS5，扩展上游 HTTP/HTTPS CONNECT 与明确认证矩阵；HTTPS 在冻结 IP 上验证原始代理主机名。旧策略的规范化摘要保持不变，新协议配置通过新修订采用。六组协议/认证及正常退出修复已完成隔离验收；该候选没有独立发布，R4B 后续组合已把当前固定 SOCKS5 策略和匹配正常退出能力部署生产，其他协议仍只引用 R5A 范围证据。内部协议映射和握手超时偏差分别见 [DEV-006](deviations/DEV-2026-09-14-006-internal-proxy-protocol.md)、[DEV-005](deviations/DEV-2026-09-14-005-relay-handshake-timeout.md)。

## 运行时一致性候选

R5C3 在原运行健康上增加控制器拥有的实际页面、socket 出口、指定 GeoIP 推断及网络拒绝证据。报告与 Profile/Home/operation/Session、三类容器 ID/启动时间、策略和环境产物绑定；Adapter 每个 Session 发放路径都核对新鲜必需项和代次门槛，公开 GET 只读当前绑定缓存。缺失或过期为 UNKNOWN，城市可选 UNKNOWN 为 DEGRADED；语言与国家不同不自动失败，strict/advisory 只执行明确约束。

Relay 的初始/失败/到期门槛关闭普通网站新旧连接，只保留受限观测路径。控制器每 30 秒开始续查，60 秒到期不延长；确认拓扑/规则漂移或绕过时暂停精确 Worker。出口变化 block 按代次保留锁定；比较历史与相应报告原子保存，跨 UNKNOWN/同代次恢复保留，但新鲜报告仍因启动时间变化而失效。浏览器观测仅操作自己创建的隐藏标签，loopback 控制通道不公开。字段与停止/恢复要求见 [运行时一致性契约](../infra/sealskin/lifecycle/runtime-coherence.md)。候选的代码与隔离验收不改变生产部署范围。

## 凭据存储与恢复

[R5B](work-items/R5B-2026-09-14-secret-store.md) 的候选实现 FileSecretStore：配置只保存一对不可变版本引用，AES-256-GCM 认证密文和 owner/Profile/Home/App 授权；主密钥在独立私有目录。控制器在启动/恢复提交期间持有凭据锁，只向对应 generation 的主机 tmpfs 写入临时材料，Relay 只读挂载整个目录，Worker 不获得凭据或主密钥。

普通停止和紧急撤销先保存意图/禁用并阻断出站，再正常关闭浏览器。Relay 的租约监测关闭已有隧道；控制器启动及后台授权检查处理撤销中断和密钥丢失。失败保留 Home/占用，重试才确认清理。age 备份包含 Home、入口 journal、固定产物及必要身份/解密材料；新目录恢复默认锁定，合并当前撤销并持久化启用记录后才能离线重绑。上述范围已完成 [隔离验收](../infra/sealskin/secret-store-acceptance-2026-09-14.md)，未部署；真实 Home/整机恢复仍归 R2。操作和兼容限制见 [组件说明](../infra/sealskin/lifecycle/secret-store.md)。

R2A 为无 Store、入口登录或密封 Session 的旧生产提供独立加密格式：运行时只读快照区分实际旧镜像和配置中的下次镜像，同一 operation 停止确认后才能归档。缺少冻结产物时保留 `observed-legacy-runtime` 的事实范围，不伪造环境通过。旧格式恢复只作离线重绑准备，提示文件不是旧控制器执行的门槛；原 Store 撤销/账号保护保持。工具及只读准备结果见 [R2A 验收](../infra/sealskin/legacy-backup-acceptance-2026-09-15.md)，真实 Home 的可恢复性仍须 R2 证明。

## 浏览器环境与版本

原生 Firefox 基线用镜像和启动校验固定 locale、languages、timezone、screen/DPR、DoH/WebRTC 等设置；它不包含 Camoufox 的低层生成配置。固定版本 Wayland 的屏幕观测未达标，因此新 Personal 基线使用 X11。

Camoufox 作为独立应用固定 Python 包、BrowserForge、浏览器发布、完整生成结果与 seeds。运行时只读取通过摘要、版本和成功报告校验的产物。Home 持久化与环境持久化分别验证；复用 Home 不足以证明环境稳定。

R5A 发现 TERM 不等于正常浏览器退出，最近 localStorage 写入可能丢失，见 [DEV-008](deviations/DEV-2026-09-14-008-resume-storage-observation.md)。新的 [退出层](../infra/browser-runtime/README.md) 在 X11/桌面存活时请求窗口关闭；显式 API 在未确认退出时保留 Worker 和占用，容器停止钩子也先尝试同一正常关闭。该能力由新镜像标签与控制清单版本声明，旧生产 Worker 不据此获得保证；强制结束、OOM 和断电仍属于未完成正常退出的场景。

R4B 为保留 Work 的 Firefox/Wayland 增加原生窗口关闭候选：限定单一已核对的 Firefox 主进程、可信 labwc socket 及 version 3 顶层管理协议，只关闭无 parent 的 `firefox` 窗口。协议没有逐窗口 PID，不能用于任意 Wayland 桌面。真实控制器 stop 的关闭拒绝/重试、s6 停止与 resume、入口显示认证、五类错误材料和三类存储恢复已通过隔离验收；候选未部署，见 [DEV-042](deviations/DEV-2026-09-15-042-work-wayland-shutdown.md)。

Camoufox 准备器支持由 SealSkin 分配 Guard/Relay 的受管理网络；该模式禁止同时指定静态 Docker network。冻结产物与成功报告继续只读挂载，生命周期所有权不变。此路径已通过 R4A 隔离验收；生产独立应用仍使用此前的静态网络，实际切换留待 R4B。

不同引擎使用各自 Home。升级与回退要配套处理镜像、Home 和产物快照，不能只改镜像标签。版本及结果见 [Camoufox 说明](../infra/camoufox/README.md) 和 [开发进度](progress.md)。

迁移准备只生成候选 App、策略及 Adapter 正向/回退配置，记录当前实际绑定和摘要。实际切换必须先用旧配置完成 stop 并确认资源释放，随后让 Adapter 在下一次启动写入新绑定；回退也走已验证 stop，保留 journal 和两个 Home。

R4B 的迁移契约还要求目标镜像与实际控制器能力匹配：精确镜像的正常退出/显示认证标签转换为 Profile 的 `required_runtime_capabilities`，准备器从当前 Adapter inspect 核对，Adapter 在创建 Home、发起启动/复用和恢复前再次核对。能力未知或版本不匹配时不创建新代次；实际启动后的能力漂移保留 unknown 占用，停止路径继续可用。共享控制器的升级须核对所有 Profile 的后续新建镜像，旧 Work 的兼容恢复不能证明它可以在新显示契约下再次创建，见 [DEV-040](deviations/DEV-2026-09-15-040-migration-controller-capabilities.md)。

目标客户端要求浏览器铺满远程桌面。R4B 将默认窗口从 1600×900 修订为 1920×1080、位置 (0, 0)，screen 1920×1080 / DPR 1 保持固定；这是新的环境产物修订，须重新验收后启用。原始 BrowserForge 结果作为生成来源保留，原生窗口配置按显式规格覆盖；其余设备、seeds、preferences 保持。r9 在精确 r7 镜像上增加去除 Openbox 边框的桌面层，重新绑定镜像并验收；不能在旧产物下临时最大化来绕过 inner/outer 一致性，见 [DEV-041](deviations/DEV-2026-09-15-041-camoufox-window-size.md)。

加密归档必须包含当前网络策略引用的 `coherence-assets/`，连同 Home、完整环境/成功报告、Store、密封状态密钥和授权身份保存；创建和解密阶段核对路径、摘要与成员。恢复先离线合并当前撤销和账号授权，再重绑新根并取得实际新鲜报告。[R5E](../infra/sealskin/release-combination-acceptance-2026-09-15.md) 已验证单 QA Home 的这一组合，生产真实 Home 和切换仍归 R2/R4B。

## 入口与客户端边界

固定入口和 Session 使用不同 origin。R5D 候选将两个公开域名全部路由到 Adapter，由短期登录、Profile 授权和一次性交接保护画面及 WebSocket；SealSkin API 与原 Session 监听保持私有并校验 TLS。登录/账号状态与业务 journal 分开，访问撤销只关闭显示，不新增生命周期所有者。私有能力头仍经过控制器的 `session_gate`；它在转发 Worker 前被删除。重复交接保留同一显示 Cookie；完整 Selkies 客户端遵循单 primary 接管规则，另一个画面接管时保持 Worker/Home/Session。

Session 持久化使用独立密钥密封，Worker 使用 [专属显示材料](../infra/browser-access/README.md)，各层日志和 HTTP 异常只保留受控输出。真实客户端、五类错误材料拒绝及恢复后扫描已通过 [R5D 隔离验收](../infra/sealskin/entry-authentication-acceptance-2026-09-15.md)，QA 已清理，生产未切换。配置、迁移/回退与已知边界见 [访问契约](../infra/sealskin/entry-auth/README.md)，当前地址见 [客户端接入](trilium-client.md#接入地址)。

Trilium Core 保持原样。主动原生 copy/paste 事件与 Selkies 面板支持已验收的文字/截图传递；WebView 的程序剪贴板访问限制继续存在。浏览器关闭而 Worker 存活时，固定入口先显示恢复提示并保留手动进入；直接进入仍会复用空桌面，恢复操作见 [客户端说明](trilium-client.md#关闭远程-firefox-后出现黑框)。自动重开尚未实现。

远程→本机仅支持纯文本，未交付反向图片、HTML/RTF 或文件下载。Unicode 输入按 code point 处理；系统 `LC_ALL` 使用 POSIX UTF-8 locale，不能直接套用浏览器 BCP 47 标签。显示、组合输入、文件与重连的证据按平台分列于 [客户端矩阵](client-matrix.md)，CDP 事件不能替代 Mac 原生输入法/Finder 验收。

## R6 远程浏览器管理面

2026-09-17 用户需求：一个面板可以新增/删除/修改远程浏览器，为每个浏览器配置代理（不配置即直连）、指纹（固化或自定义）、浏览器页面的登录 URL 与账号密码。具体契约见[管理面规格第 2 版](specs/proxy-environment/management.md)；除第 1 步只读列表外尚未实现，均未部署。相对第 1 版提案的架构变化：

- **Profile 定义从静态配置变为 Adapter 私有的可修订目录**（`profiles.json`）：运行中可增删改，写入沿用 journal 的 flock/fsync/原子替换与乐观锁；现有配置文件中的 Profile 首次启用时原样导入。Adapter 仍是业务授权与 Profile 状态所有者，SealSkin 仍是唯一的 Session/Docker 生命周期所有者。
- **Adapter 增加只用于管理面的管理员 SealSkin 客户端**（独立密钥），负责按 Profile 修订安装/更新/删除应用定义与创建 Home；策略修订与 Secret Store 导入沿用控制器已有格式与授权模型，只追加不改历史。生命周期调用继续使用原用户身份。
- **网络二选一**：受管理代理（http/https/socks5，草稿 → 隔离探针 → 不可变修订 → 下一代次）或受管理 DIRECT（R5C1）。“不配置代理”就是 DIRECT，不是无 Guard 的裸容器网络；DIRECT 的生产前置（主机 IPv4 证据、网关镜像、控制器能力）成为部署条件。
- **指纹两种来源**：固化产物目录（`accepted` 且镜像摘要匹配）或自定义：用户只提交规格 46.2 的高层字段，服务端在隔离容器中生成、完整验收后发布到目录才可绑定；不接受低层字段，不允许运行中切换。
- **访问**：账号表增加 `admin`/`user` 角色，面板可创建/重置/禁用账号并分配浏览器，展示每个浏览器的固定入口 URL；密码仍只存 PBKDF2 派生值。此处的“登录 URL 与账号密码”指平台入口，不含目标网站自动登录。
- **删除 = 停止并确认资源为零 → Home 归档 → 撤销应用/策略/授权**；物理清除是要求加密备份的单独管理员命令。关闭复用 `profile.Stop`/`Reconcile`；启动前仍由服务端生成一次性 `launch_plan`。

实施顺序改为：R6A 只读列表（已完成候选）→ R6B 目录与角色/关闭 → R6C 新增与删除（固化指纹 + DIRECT/现有代理）→ R6D 代理草稿与探针 → R6E 自定义指纹作业 → R6F 组合 QA 与生产候选。R4B 收尾后用户决定不等待 R2 剩余条件；R6A 候选未部署。

<a id="decisions"></a>
## 设计决策

沿用原 ADR 编号，以下说明其在当前实现中的含义。

| 决策 | 当前含义 |
| --- | --- |
| ADR-001 · Linux 生产运行 | 网络、容器和桌面联调在 Linux；实际主机与目标版本分别记录 |
| ADR-002 · Go 入口适配层 | 用 Go 实现固定入口与控制契约；独立 Go Broker 保留为备选 |
| ADR-003 · 不修改 Trilium Core | 优先通过服务端和网页客户端完成接入 |
| ADR-004 · Worker 临时、Profile 持久 | 数据、环境产物与容器生命周期分离 |
| ADR-005 · Home 独占 | 单实例、持久化占用与实际资源核对共同保证 |
| ADR-006 · 代理与环境长期绑定 | 绑定具体修订；运行观测不自动改写环境 |
| ADR-007 · 引擎可替换 | 通过受控新 Home 和能力验收替换，当前不提供任意引擎互换 |
| ADR-008 · SealSkin 优先 | 当前复用 SealSkin，补丁范围可审计；独立 Docker Broker 未启动实施 |
| ADR-009 · 后端由验收与维护成本决定 | 同一批 Worker 始终只有一个生命周期管理者 |
| ADR-010 · Persona Studio 可选 | 不是当前生产或 MVP 的前置依赖 |
| ADR-011 · 选择已验收环境槽位 | R6 提案：用户选择不可变 Artifact/Profile/Home 组合，不允许运行中修改任意指纹字段 |
| ADR-012 · 管理操作经过 Adapter | R6 提案：客户端只提交授权选择和一次性计划，Adapter 负责权限、修订和生命周期调用 |
| ADR-013 · 代理秘密只进 Secret Store | R6 提案：手动代理先测试再固化，Worker 只经 Guard/Relay，失败不能直连 |

上游已知缺口及本地处理见 [SealSkin 审计](sealskin-0.3.2-audit.md)。原始理由和备选方案保存在 [历史 ADR](archive/design-v1.3-2026-09-13.md#38-architecture-decision-records)。

## 原章节定位

原设计的其他章节、API 草案、M0–M19 和推荐目录结构保存在 [完整快照](archive/design-v1.3-2026-09-13.md)。下列锚点兼容已有引用，新文档应直接链接到对应现行页面。

<a id="44-当前版本完成标准"></a>

- 原第 44 节：[版本定义与发布门槛](roadmap.md#release-criteria)。

<a id="45-proxy-architecture--specification"></a>

- 原第 45–50 节：[代理、环境、网络、健康与凭据规格](specs/proxy-environment/specification.md)。

<a id="485-首版网络故障验收"></a>

- 原第 48.5 节：[N01–N08 网络故障验收](specs/proxy-environment/specification.md#485-首版网络故障验收)。
