# 浏览器工作区、统一代理与首页改版方案

状态：**方案 v4 已确认并进入实施（2026-09-21；R7A、R7B 已收尾，尚未部署）**

关联：[R7-DESIGN 工作项](work-items/R7-DESIGN-2026-09-20-browser-workspace.md)、[管理面规格](specs/proxy-environment/management.md)、[UI 重构说明](management-ui-redesign.md)、[Work 出网偏差](deviations/DEV-2026-09-20-061-work-egress-unobserved.md)、[网络应用副作用偏差](deviations/DEV-2026-09-20-062-network-apply-implicit-stop.md)。

## 1. 先处理 Work 公网问题

### 当前证据

Work 的进程和显示运行正常，但只连接内部隔离网络，没有 IPv4 默认路由，也没有受管理 network policy / Relay / Guard 资源；健康缓存把它显示为 `healthy`，同时将 proxy 标为 `PROXY_NOT_CONFIGURED`。因此当前结论是“浏览器运行健康，公网网络未配置且不可达”，不是“Work 已具备公网能力”。完整因果链仍需分层验证。

### R7A 只读诊断

1. 核对 Profile 目录、应用 provider、Home/Session/operation 绑定和历史 journal；确认 Work 使用的是 legacy Firefox/Wayland，还是配置漂移。
2. 只读检查 Worker 网络命名空间：网络列表、internal/gateway、IPv4/IPv6 路由、DNS、默认路由、Guard/Relay 记录；不读取 Cookie，不改容器网络。
3. 在受控网络探针中分别测试 DNS、TCP/TLS、HTTPS 目标和返回出口；把 `DNS_FAIL`、`NO_DEFAULT_ROUTE`、`DIRECT_GATEWAY_UNAVAILABLE`、`RELAY_UNAVAILABLE`、`UPSTREAM_AUTH_FAILED`、`BROWSER_ONLY_FAIL` 分开。
4. 若控制器报告正常，再从 Work 浏览器打开固定无登录 HTTPS 回显页，记录页面结果与健康报告的对应关系；第三方验证码/登录失败不能当作网络证据。

实施状态（2026-09-21）：R7A 已完成旧运行证据与当前停止态复核，并交付未部署健康候选：无策略运行代次为 `unmanaged / EGRESS_NOT_CONFIGURED`、整体 degraded。因 Work 已由此前管理动作停用并停止，R7A 没有为浏览器重新导航或启动无策略代次；DNS/HTTPS 与出口实测随 R7B 的受管理 QA 路径完成。证据见 [R7A 验收](../infra/sealskin/r7a-work-egress-diagnosis-acceptance-2026-09-21.md)。

### R7B 修复决策

优先沿用受管理网络所有权：

- 代理模式：为 Work 绑定一条独立 immutable `proxy_required` policy，由统一代理目录引用，经 Relay/Guard 出网；不能把 Personal 的 policy、secret、Home 或 generation 直接复用。
- DIRECT 模式：绑定独立受管理 DIRECT policy，由专属网关、Guard 和批准解析器提供出网；不是把 Worker 接入默认 bridge，也不是清除 internal 隔离。
- 运行中的 Work 不热切换。若必须更换引擎/网络关键绑定，先显示影响，安全关闭并确认 0 resources，再生成下一 revision；失败保留旧绑定和 Home。
- 修复不修改用户 Home 内容，不重新生成既有 Firefox 数据，不更换账号密码；只有明确授权的维护窗口才停止/重建 Work。

实施状态（2026-09-21）：独立 QA 证明旧 Work 兼容镜像还缺少 Firefox Relay 锁定配置；已在精确的既有 Firefox/Wayland/正常退出/显示认证父层上增加最小受管理网络层。真实公开 HTTPS、DIRECT 健康、四类原始绕过拒绝、网关停止 fail-closed、正常 Stop/新 generation 及 Cookie/localStorage/IndexedDB 恢复全部通过，QA 已清理且生产保持。候选未绑定生产，见 [R7B 验收](../infra/sealskin/r7b-managed-work-egress-acceptance-2026-09-21.md)。

### R7C 验收门槛

Work 必须同时通过：Adapter/Session/Worker/显示、DNS、HTTPS、出口路径、Guard/Relay、失败时无直连、停止—重建—恢复、Home 数据抽样和 Mac/Trilium 真实打开。公网成功一次不等于长期策略通过；健康页显示采样时间和网络状态，过期为 unknown。

## 2. 统一“网络代理”Tab

### 信息架构

管理页新增“网络代理”顶级 Tab，与现有“浏览器 / 指纹作业 / 访问账号”并列：首页只显示摘要。网络代理 Tab 管理代理配置目录，不直接管理某个 Worker 的临时草稿。

每条配置显示：名称、协议（SOCKS5/HTTP/HTTPS）、认证方式、脱敏主机与端口、探针状态/时间、出口验证状态、引用浏览器数、修订号、启用/停用状态。凭据永不回显，主机和错误信息按现有脱敏规则处理。

### 生命周期

`草稿 → Secret Store 导入 → 隔离探针 → accepted 修订 → 可绑定`。配置采用追加修订，旧修订不可覆盖；被引用修订不可删除，只能停用并在无引用时归档。探针失败、过期、撤销均保持明确失败状态，不降级为 DIRECT。

### 安全与副作用

- Adapter 只保存代理 ID、修订、脱敏摘要和 Secret Store 引用；密码只经 tmpfs/管理员加密接口进入 Store。
- 每个浏览器绑定自己的 policy/application/Home 关系；“统一配置”表示目录统一、引用统一，不表示共享运行时 secret 或网络命名空间。
- 代理配置 Tab 的保存是无副作用的目录操作。绑定/应用是单独动作，须显示“下一代生效”。运行中默认返回冲突，不隐式调用 Stop；若提供“关闭后应用”，必须是独立确认动作。
- 普通管理员需要近期确认密码才能创建、探测、停用、撤销和绑定；所有动作带 CSRF、幂等键和审计结果。

## 3. 浏览器配置表单

浏览器创建/编辑表单改为只选择服务端已准备好的对象，不让客户端提交策略摘要或底层资源标识：

1. **指纹模板**：下拉选择 `accepted` 环境目录条目，显示来源（固化/自定义）、引擎、locale/languages、时区、屏幕/DPR、验收时间和产物修订；不可选择 generating/failed/retired。
2. **网络代理**：下拉选择“无代理（受管理 DIRECT）”或已 `accepted` 的代理配置修订；保存时由服务端解析为新的 immutable policy，不接受用户粘贴 policy ID/SHA。
3. **浏览器模板**：下拉显示能力目录中的 `Camoufox`、`Firefox legacy（兼容 Work）` 等已验收浏览器模板。它决定浏览器二进制、指纹/环境产物和浏览器启动方式。
4. **显示模板**：面向用户显示效果，不直接要求选择 X11/Wayland。候选名称为“清晰适配”“固定指纹 1920×1080”“固定指纹 1280×800”；每项显示适用客户端、画面比例、缩放方式、screen/DPR、清晰度取舍和验收状态。只有 `accepted` 模板可选择。
5. **高级详情**：展开后显示该模板使用 `X11 + Selkies` 或 `Wayland + Selkies`、编码/分辨率约束和固定版本。Selkies 是共同的画面/输入传输层，不是与 Camoufox/Firefox 并列的浏览器引擎。
6. **兼容性提示**：浏览器模板与显示模板不是任意组合；服务端只列出共同通过验收的组合。当前 Personal 的 `Camoufox + X11 + Selkies + 固定 1920×1080` 可作为既有固定指纹模板，Work 的 `Firefox legacy + Wayland + Selkies` 仅作为清晰度参考；在补齐明确 screen/DPR、缩放规则和客户端验收前，不能直接把 Work 标为已实现的“自适应”模板。“固定指纹 1280×800”同样是未来候选，生成与完整验收通过后才能进入下拉框。
7. **其他可编辑项**：名称、起始页、入口账号分配、启用状态。浏览器 ID、Home、已发布的应用/策略历史不可直接改写。

顶部优先显示用户可理解的组合，例如 `Work · Firefox · 清晰适配`、`Personal · Camoufox · 固定指纹 1920×1080`；高级详情再显示 `Wayland/X11` 和“传输：Selkies”。不再让一个 Selkies 标题看起来像浏览器名称。

### 指纹模板策略

“效果更好”定义为兼容、稳定、内部一致并可回退，不以字段更多、每次随机或绕过第三方风控为目标。页面不开放 User-Agent、WebGL、Canvas、字体等低层字段逐项拼装；管理员只选择已验收模板，或提交受限的高层自定义规格，由服务端生成完整产物。

每个指纹模板必须满足：

- 浏览器引擎、版本、User-Agent、平台和操作系统家族一致；Camoufox 模板不能直接绑定 Firefox legacy，反之亦然。
- `locale`、`languages`、timezone 与预期工作地区形成可解释组合；网络代理只负责出口，不能在启动时根据代理自动改写既有指纹。代理地区变化时显示不一致提示，由管理员生成并验收新 revision。
- `screen`、可用区域、窗口尺寸和 DPR 与显示模板的缩放规则一致。Selkies 的客户端缩放只改变观看效果，不得暗中改变浏览器报告的 screen/DPR。
- 字体、WebGL、Canvas、音频及媒体能力由固定生成器和镜像摘要共同解析；页面不允许分别随机。模板首次生成后固定到不可变 revision，同一浏览器跨重启继续使用同一 revision。
- 不追求“独一无二”或每次启动随机化。新增随机种子只在创建新模板时发生；修改任何关键字段都生成新 revision，并明确提示可能影响既有网站登录状态和设备识别。
- 验收使用本地测试页核对报告字段、窗口/点击映射和多次重建稳定性，再做目标 Mac/Trilium 视觉与交互复测；第三方验证码是否出现不作为指纹成功或失败的判据。

推荐目录先提供少量经过完整验收的组合，而不是大量自由组合：

| 场景 | 浏览器模板 | 指纹模板 | 显示模板 | 网络边界 |
| --- | --- | --- | --- | --- |
| Personal 长期使用 | Camoufox | 稳定桌面模板，同一实例固定 revision | 已验收的固定 1920×1080；清晰适配验收后可选 | 固定代理修订；失败不回退 DIRECT |
| Mac/Trilium 日常操作 | Camoufox | 与目标语言、时区和引擎一致的稳定模板 | 优先选择验收后的清晰适配 | 代理或受管理 DIRECT 均独立验收 |
| 现有 Work | Firefox legacy | 保留现有环境与 Home，不直接改造成 Camoufox 指纹 | 当前 Wayland 组合先标为“兼容显示”；清晰适配验收后再改名 | 先完成 R7A/R7B 出网修复 |
| 隔离测试 | Camoufox | 独立 QA 模板和 Home | 与目标客户端匹配的已验收模板 | 独立 QA 代理/策略，不复用生产身份 |

下拉项摘要显示名称、引擎、主要语言/时区、screen/DPR、来源、修订和验收时间；低层解析值放在只读详情中。若所选代理、浏览器模板或显示模板与指纹不兼容，服务端不提供该组合，而不是只在提交后给出警告。

### 重新选择规则

- 运行中仅允许无副作用字段保存；浏览器模板、指纹、代理、显示模板任一修改都显示“停止后应用”，不自动停止。
- 停止且资源为零后，服务端创建新的应用/策略修订，保留旧 revision 供回退；同一 Home 更换指纹或引擎必须提示 Cookie/设备身份可能不再匹配。
- 旧 Work 只能选择已验收且与 Firefox legacy 兼容的显示模板；迁移到 Camoufox，或让显示模板改变底层 Wayland/X11，均视为迁移工作，不是普通下拉保存，必须独立备份、QA Home、客户端和回退门槛。
- 新浏览器默认只能选择已验收 Camoufox 模板和与之匹配的显示模板；Firefox legacy 仅为存量兼容模板，不能创建新实例，除非另有验收。

## 4. 首页 UI 重设计

入口首页 `/` 目前是无层级的 Profile 文本列表。改为单屏工作区：

- 顶栏：产品名、当前登录身份、网络/系统总状态、管理入口、修改密码、退出。
- 欢迎/状态区：明确“可访问的浏览器数量”“需要处理的网络问题”“最近一次采样时间”；不把 HTTP 200 或容器 running 当作公网健康。
- 浏览器卡片：名称、入口按钮、运行状态、健康状态、网络状态（代理/DIRECT/未配置）、指纹模板、浏览器模板、显示模板、最近采样时间、进入配置/查看详情；X11/Wayland 与 Selkies 放入高级详情。
- 操作分层：打开浏览器为主按钮；查看详情/配置为次按钮；停止/停用为警示按钮；删除不放在首页卡片主操作内。
- 空状态：无授权浏览器、网络未配置、Work 出网故障分别给出可操作提示；普通用户不显示管理动作或其他 Profile。
- 响应式：1280×800 首屏看到全部卡片主要状态，窄屏单列；不用外部资源、JavaScript 或大表格；键盘焦点、状态文字和错误提示可见。

首页不显示代理密码、Session URL、Cookie、Home 路径、完整 policy SHA 或容器内部地址。所有链接由服务端按授权生成，不能从 query 参数拼接任意跳转。

## 5. 服务端对象与实施顺序

建议新增/扩展以下 Adapter 私有对象：

| 对象 | 作用 | 生效边界 |
| --- | --- | --- |
| `network_profiles.json` | 代理配置摘要、修订、状态、引用计数 | 追加写、原子替换、被引用不可删除 |
| `environment_catalog` | 指纹/浏览器模板、稳定性规则、引擎及地区语义与验收摘要 | 只绑定 accepted 的不可变修订；低层字段由固定生成器解析 |
| `display_catalog` | 用户效果名、X11/Wayland、Selkies、screen/DPR、缩放规则、客户端范围与验收摘要 | 只列 accepted 且与所选浏览器模板兼容的修订 |
| `browser record` | `browser_template_ref`、`display_template_ref`、`artifact_ref`、`network_ref`、Home/application 绑定 | 运行中仅轻量字段；关键变更下一代 |
| `health report` | 运行、显示、网络、公网探针分开 | 采样过期为 unknown |
| `audit event` | 操作者、旧/新 revision、结果和失败码 | 不含密码、Cookie、Session URL |

实施顺序：

1. R7A：只读 Work 网络诊断和健康模型补齐；先得到具体失败码。
2. R7B：按失败码在隔离 QA 修复 Work 受管理出网，完成无直连和恢复验收；未经用户维护授权不动生产 Work。
3. R7C：代理目录、Secret Store、探针、修订/撤销和绑定 API；补充合法运行实例零 Stop 副作用测试（承接 DEV-062）。
4. R7D：指纹模板、浏览器模板、显示模板及其兼容组合目录；落实指纹稳定性与字段一致性检查、受限高层自定义、浏览器配置下拉和停止后应用/回退；用户按“清晰适配/固定指纹”选择效果，X11/Wayland 与 Selkies 作为底层详情分别验收。
5. R7E：首页 UI 重设计和管理页“网络代理”Tab，先隔离 fixture，再 Mac/Trilium 视觉验收。
6. R7F：只在明确授权后发布 Adapter/控制器变更；发布前保留回退二进制、Profile/Home/Session/账号摘要，发布只执行授权服务重启。

## 6. 完成与不做的事

完成必须证明：Work 的真实公网路径可用且受 Guard/Relay/DIRECT 约束；代理凭据不泄露；浏览器可分别从 accepted 浏览器模板、指纹模板和显示模板兼容组合下拉选择，并在停止后安全切换；指纹跨重启稳定且引擎/平台、语言/时区、screen/DPR 与显示规则一致；代理变化不会静默改写指纹；“清晰适配”有明确而非推测的 screen/DPR 与缩放规则；旧 revision 可回退；页面明确区分浏览器模板、指纹、显示效果与 Selkies 传输；首页和管理页在 Mac/Trilium 1280×800 及窄屏清晰可用。

方案阶段本身不曾授权修复 Work、新增代理、停止浏览器、修改 Home/账号、切换 Camoufox/Firefox 或部署 UI。用户已于 2026-09-21 明确确认开始并持续推进；实施仍须按 R7A–R7F 逐项建立、验收和收尾，生产副作用只在对应工作项与发布门槛内执行。
