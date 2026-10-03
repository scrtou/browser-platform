# SealSkin Profile Adapter

当前部署已封存为 [server-2026.10.02.3](../docs/releases/server-2026.10.02.3.md)：R6AS Adapter `63d88d1e…`，精确121文件及原始二进制、恢复说明均在发布树。混合开发工作树不作为部署身份；慢启动增量与历史矩阵按实际版本分别记录。

R6AS当前已部署：LaunchURL使用现有180秒长操作预算，避免正常原生启动超过45秒后提前转为unknown；幂等键、取消与真正不确定响应的保护保持。三引擎固定网络/升级矩阵、两次额外50秒真实启动及完整Go回归见[R6AS验收](../infra/sealskin/r6as-fixed-version-matrix-acceptance-2026-10-02.md)。当前源码在R6AR精确快照上增加两路径；统一版本封存随后记录。


历史 R6AM Adapter 已随 [server-2026.10.02.2](../docs/releases/server-2026.10.02.2.md)封存，二进制与运行身份匹配。

R6AM：首页网络列及详情显示实际绑定代理名称。`EnvironmentSummary.NetworkProfileLabel` 按当前目录 ID/revision 只读解析，`HomeCard.NetworkName` 传递给授权首页；缺失名称明确占位，直连保持原显示，不读取凭据或发起探测。见 [验收](../infra/sealskin/r6am-workspace-proxy-name-acceptance-2026-10-02.md)。

R6AL：首页列表增加“网络”列，直接渲染既有授权 `HomeCard.Network` / `NetworkIssue`，已知模式显示中文、缺失/不可用明确占位；仅改首页模板，无额外探测或凭据读取。见 [验收](../infra/sealskin/r6al-workspace-network-acceptance-2026-10-02.md)。

[服务器版本 server-2026.10.02.1](../docs/releases/server-2026.10.02.1.md)已封存：当前发布源码、原始Adapter二进制与恢复边界；本地标签/归档核对通过。

R6AI容量发布：已收尾并部署：容量改为按机器CPU/内存/磁盘自动推导，保留逐项覆盖和实时内存/并发预算保护；当前机器算得4个活动、1个并发，迁移重新计算。两套Go test/vet、容量race、只读诊断与保护发布通过，原浏览器和会话保持。 见[验收](../infra/sealskin/r6ai-capacity-release-acceptance-2026-10-02.md)。

R6AG：所有现有需近期密码确认的管理操作统一使用密码弹框，成功后继续原提交。覆盖代理创建/探针/停用/撤销/删除、浏览器删除/网络绑定与迁移/模板应用回退、管理员创建/账号密码重置/启停/角色/删除，保留指纹数据删除。普通不需确认的操作不新增门槛；取消不执行，密码错误可重试；只有明确reauth响应才重试一次，普通拒绝与超时不自动重试。 见[验收](../infra/sealskin/r6ag-all-reauth-acceptance-2026-10-02.md)。

R6AF：指纹数据删除遇到近期密码验证时，在弹框输入当前密码并继续原已确认删除；取消/错误不删除，引用拒绝原框反馈，成功才刷新。管理页确认密码入口也使用弹框，无脚本仍有验证链接。原权限、5分钟窗口、引用保护和持久删除标记保持。 见[验收](../infra/sealskin/r6af-job-delete-acceptance-2026-10-02.md)。

R6AE更新：修改密码在首页/管理页打开共享弹窗，原地址保留无脚本回退；密码创建、重置和自助修改最低4、最高256个UTF-8字节，原哈希强度、当前密码验证、CSRF和其他登录撤销语义保留。浏览器详情按概览、常用设置、网络、环境模板、危险操作分页签，代理/账号按实际功能分组；短表单保持单页。指纹四类删除为直接按钮打开对象确认框，原引用保护和确认勾选保留。 见[本项验收](../infra/sealskin/r6ae-dialog-layout-password-acceptance-2026-10-02.md)。

R6AD只扩展管理模板CSS/JS，指纹数据list-create/delete-control复用record dialog；表单移动但不复制，删除标题绑定对象，增加取消。处理器与表单契约不变，见[验收](../infra/sealskin/r6ad-fingerprint-dialogs-acceptance-2026-10-02.md)。

R6AC仅调整httpapi/manage.go模板及既有UI契约测试。四个管理子项统一表格，记录详情弹窗移动原表单节点，保留无脚本details和原鉴权/字段/删除保护。对照133个表单契约、105布局及24次回环提交通过，见[验收](../infra/sealskin/r6ac-management-lists-acceptance-2026-10-02.md)。

R6AB界面：gateway首页采用授权浏览器列表和详情dialog，每请求随机nonce支持脚本；管理面板成为首页/管理页统一侧栏的可展开一级菜单，四个二级功能保留原路由。侧栏支持收起、手机抽屉与键盘。无脚本可通过checkbox/details查看导航和详情。业务处理与生产浏览器保持，见[验收](../infra/sealskin/r6ab-workspace-ui-acceptance-2026-10-02.md)。

R6Y 删除：`internal/profile/data_deletion.go` 实现代理凭据撤销/删除审计与指纹数据引用检查/私有删除标记；`internal/access/accounts.go` 在现有文件锁内删除账号并保护最后管理员；HTTP 删除端点要求确认框和近期密码。新建/模板重选与删除串行，源码/任务证据保持，引用包括当前、未完成及回退绑定，来源扫描全部保留任务。控制器与 runner 接口不变。

R6X：浏览器卡片的网络区改用单个下拉表单，当前绑定精确回显、不可用绑定占位，DIRECT/已授权 accepted 代理可选。`network_selection.go` 将 `network_select` 分发到原受保护处理器，不改变业务状态或凭据授权规则；`network_selection_test.go` 与真实网关测试覆盖解析/授权/近期确认/错误提示。无 JS 也可提交，保留操作标识重试语义。

2026-09-30 当前 Adapter `7f4e2a1a…` 的 76 文件源码、已复建二进制与配置现纳入 [352 文件服务器发布包](../infra/sealskin/r7f-server-release-seal-acceptance-2026-09-30.md)。包内外清单校验通过；恢复仍保留现行 journal/账号/Session，迁移前二进制不能直接覆盖当前目录。本轮只固定材料，没有部署。

2026-09-30 客户端续跑：当前二进制的 Linux Chromium 实际页面 9 组复验通过。显示模板选项使用目录 label 与 screen；生产 operator-owned 目录的 label 已修正为“固定指纹”，避免底层 X11/Selkies 名称出现在效果选择中。目录每次读取，无需服务重启，技术字段与绑定不变；Mac Chrome 与 Trilium 0.106.0 后续已完成注明范围分项，未测菜单和精确尺寸不据此通过。见 [页面验收](../infra/sealskin/r7f-client-ui-acceptance-2026-09-30.md)。

## R7F 旧 Work 网络迁移与回退（2026-09-30）

当前最终源码已独立复建并匹配已运行的 `7f4e2a1a…`；109 文件审核材料固定当前二进制、配置/目录、历史二进制与加密备份，见 [材料验收](../infra/sealskin/r7f-release-materials-acceptance-2026-09-30.md)。原私有源码副本落后于最终清单的差异按 DEV-080 修正；完整发布包封版与运行/客户端剩余项仍归 R7F。材料校验不会自动应用配置或回退。

可选 `legacy_network_migrations` 指向服务端私有 JSON 目录（普通文件、0600、version 1）。每条迁移固定 `id/status=accepted/source_revision/source_definition/source_application/target_image/acceptance_sha256/backup_sha256/restore_sha256`。`source_application` 必须来自加密管理员 API 的完整 resolved application，去掉 `image_sha/last_checked_at/pull_status` 三个观测字段；磁盘 `installed_apps.yml` 的局部 overrides 不能替代它。运维准备负责复核真实验收、精确父镜像层和备份/恢复回执，摘要字段本身不是验收证明。配置依赖 DIRECT、环境目录与入口认证。

管理页只为匹配的已停用 Firefox/Wayland 存量记录显示“迁入受管理网络”；请求只提交目录 ID、revision 与操作标识，经现有管理员/manage 授权、Origin/CSRF 和 5 分钟近期密码确认。迁移在 Profile 生命周期锁内只读确认 stopped/0 resources 和控制器能力；先写 `migrating/pending_migration`，再追加精确 DIRECT policy、完整 PUT 与读回比对，最后提交目录。只更换受验收镜像及 policy 引用，保留 Home、引擎/显示、账号、禁用状态和其余应用字段。失败后保留门禁；相同管理员、操作标识、原 revision 与目录摘要可恢复，其他请求拒绝。迁移中禁止删除与普通状态清除。

成功后仍停用；管理页提供“回退网络迁移”，在停止且资源为零时经同样认证和持久门禁恢复原应用/目录，不恢复旧 journal、不删除策略、不改 Home。中断后同一请求可继续。目录或其他配置漂移时拒绝猜测回退；回退后若要重新迁移，按新的 Profile revision 重新审阅目录条目。生产生效范围及未完成条件见[本轮验收](../infra/sealskin/r7f-legacy-migration-acceptance-2026-09-30.md)。

`Ensure` 现先取得生命周期锁再读取目录、状态与禁用标志；等待中的启动不会使用变更前定义，见 [DEV-077](../docs/deviations/DEV-2026-09-30-077-launch-definition-lock.md)。

当前线上组合的独立实际迁移/回退已通过真实登录、近期认证与完整应用比对；正常停止后 Cookie/localStorage/IndexedDB 及再次迁移读回一致，Home、journal、账号和策略历史保持。工具从干净环境复跑及清理通过，范围见 [独立恢复验收](../infra/sealskin/r7f-work-recovery-acceptance-2026-09-30.md)；生产真实 Home 重建和目标客户端仍单独验收。

2026-09-30 Personal 经现有 R7C 管理页绑定到授权的 `tw` r1，新代次 PROXY_OK、浏览器/显示与 Worker HTTPS/绕过拒绝通过，原 Home/应用/镜像保留。旧目录受管理策略兼容问题 DEV-071 已完成生产验证；没有新增接口或部署，浏览器 GUI/数据及目标客户端范围见 [恢复验收](../infra/sealskin/r7f-personal-recovery-acceptance-2026-09-30.md)。

[文档导航](../docs/README.md) · [当前架构](../docs/design.md) · [开发进度](../docs/progress.md) · [运维说明](../docs/operations.md)

它把稳定 Profile 入口映射到 SealSkin 的命名 Home 和运行会话，并实现 SealSkin 的 RSA-PSS 握手、RSA-OAEP 密钥交换、AES-256-GCM API 信封和 RS256 用户 JWT。

当前通过 [systemd 用户服务](../infra/sealskin/profile-adapter.service) 运行，安装见 [部署说明](../infra/sealskin/README.md)。发布版本、现有会话与新会话的生效范围、linger 和验收缺口统一见 [开发进度](../docs/progress.md)。

2026-09-29 阶段历史：当时生产为 `346d6377…`，环境、统一代理及模板目录已配置；r10“测试”健康，Personal/Work 当前停止。`inspect` 保留控制器实测的 `network_direct_version`，缺字段为 0，不根据镜像猜测版本。Work 旧记录迁移及目标客户端仍待验证，见 [本轮验收](../infra/sealskin/r7f-production-review-acceptance-2026-09-29.md)。

## 已实现的行为

- `GET /browser/{profile}/` 只返回自动提交页面，不在 GET 中创建会话。
- `POST /browser/{profile}/start` 创建或复用会话；启用 `access` 时以 `303` 跳到短期交接地址，兑换后进入不含后端 token 的 Session URL。
- 每个启动操作先持久化 `operation_id`、幂等键和唯一 bootstrap URL。
- SealSkin 启动成功但响应丢失时，使用 `launch_context` 中的 bootstrap URL 精确认领会话。
- 控制器明确提供 `profile_initial_url_version: 1` 时，受管理启动另传配置的 `start_url` 作为 `initial_url`，保留 bootstrap 对账标记；DIRECT 无需访问宿主机中转页。
- 无法证明启动结果时记录 `unknown`，后续请求不会再次启动。
- Profile 可声明 `required_runtime_capabilities: {"browser_shutdown_version": 1, "session_auth_version": 1}`。Adapter 从当前控制器读取能力，在创建 Home、启动/复用及恢复前核对，启动后再次核对；缺失/版本不匹配时入口返回 503，保持 journal 和资源。停止与对账仍可用。未声明要求的旧 Profile 保持兼容；本机 inspect 的 `capabilities` 是实时观测，缺失值为 0。R4B 的迁移准备器依据目标镜像标签生成要求，见 [DEV-040](../docs/deviations/DEV-2026-09-15-040-migration-controller-capabilities.md)。
- Profile 已绑定的会话从 SealSkin 列表消失时转为 `unknown`，避免在 SealSkin 重启后遗漏孤儿容器。
- 状态文件使用跨进程 `flock`、`fsync`、原子 rename 和 `0600` 权限。
- 启用 lifecycle 补丁后，启动前检查 Home 的会话记录与全部 Docker 挂载；新 Worker 使用固定容器名及 Home/Profile/operation 标签。
- 新代次固定网络策略 ID 和 SHA-256，受管理启动要求服务端 `network_runtime_version: 1`，并在启动后核对资源归属；旧无策略活跃绑定保持兼容。
- SealSkin 在 Docker create 前落盘网络占用，为 generation 分配独立内网、出站网络、Relay 和 Guard；Guard 安装规则并降权、探测通过后才启动 Worker。
- 停止前先持久化 `stopping` 与稳定停止幂等键；停止后重新查询，只有记录、Worker、Guard、Relay、网络和占用都消失才提交 `stopped`。失败保留占用，重启后继续停止；SealSkin 界面直接停止留下的网络清理也可通过对账继续。
- 本机 `0600` Unix socket 提供 inspect、stop、reconcile；服务全程持有独占状态文件锁，CLI 复用运行中的 Profile 锁。
- Session URL 只能解析到配置的 SealSkin HTTPS origin；带 token 的重定向使用 `no-store` 和 `no-referrer`。
- R5D 候选的 `access` 为入口、健康、Session HTTP/WebSocket 增加本地账号与 Profile 授权，使用短期 Cookie、CSRF 和一次性交接；账号/绑定失效会关闭显示连接，保留浏览器与 Home。两公开 origin 都必须路由到 Adapter，控制 API 使用同一受验证的私有 HTTPS 上游。管理、日志和恢复见 [入口登录说明](../infra/sealskin/entry-auth/README.md)；候选 3 的真实客户端、显示撤销与恢复已通过 [隔离验收](../infra/sealskin/entry-authentication-acceptance-2026-09-15.md)，生产未切换。
- R6A 管理面第 1 步：启用 `access` 后，`GET /manage/`（服务端页面，新建联动使用 nonce 脚本）和 `GET /manage/environments`（JSON）列出当前登录管理员可管理的 Profile 及只读环境摘要：`label`、固定入口路径、能力、应用/Home、语言/时区/显示模式、网络模式与策略 ID、journal 状态，以及缓存健康报告的整体结果、采样时间、有效期、恢复提示代码和环境产物身份。列表只读缓存，不观测、不启动、不恢复、不停止；无缓存标为未观测，过期标为 stale 且整体 unknown。响应不含 operation、Session、bootstrap、幂等键、策略摘要、错误文本或 resolved config；未登录 303/401，普通账号 403，POST 405，未启用 `access` 时 404。Profile 定义可选 `label`（≤ 64 个可打印字符）仅用于显示。该列表已随 2026-09-19 的 R6F 安全子集部署生产，原隔离范围见 [R6A 验收](../infra/sealskin/environment-list-acceptance-2026-09-17.md)。
- R6B 管理面第 2 步：`profile_directory` 把 Profile 定义持久化为私有 `profiles.json`（首次从配置 `profiles` 导入，之后以文件为准；Adapter 服务锁保证单写者，进程内互斥、逐条 `revision`、乐观锁、0600/fsync/原子替换），管理员可在运行中修改 `label`、`start_url` 与 `disabled`；停用的浏览器在入口返回 503，已运行代次、显示、健康、停止不受影响。账号表 version 2 增加 `role`（`admin`/`user`，空即 `user`；无角色时仍写 version 1）。`/manage/*` 只对管理员放行，POST 经精确 Origin + CSRF；管理员看到全部浏览器（`view`/`manage`/`stop`，被分配的另有 `start`）、分配账号与固定入口 URL，可保存名称/起始页、停用/启用、安全关闭（复用 `profile.Stop`），并创建账号、重置密码、禁用/启用、分配浏览器、改角色。`POST /auth/reauth`（5 分钟）保护创建管理员、禁用/启用、改角色、重置他人密码；`/auth/password` 供任意账号改自己的密码并撤销其他登录。账号表变化只撤销记录变化的账号；最后一个启用的管理员不能被禁用或降级。DEV-045–047 已解决；Profile 目录、角色和上述操作已随 R6F 安全子集部署生产，真实 Mac/Trilium 仍待确认，原隔离范围见 [R6B 验收](../infra/sealskin/environment-directory-acceptance-2026-09-17.md)。
- R6C 管理面第 3 步：配置 `environment_catalog` 后，Adapter 使用独立的 `sealskin_admin` 身份安装/删除应用；目录只接受 `status=accepted`、`source=frozen`、完整 SHA-256 与固定 `sha256:` 镜像摘要，并把应用模板、网络策略 ID/SHA、Profile、Home 和应用 ID 一起固定。创建失败留下 `creating` 记录可重试；删除先复用 verified Stop，确认 records/workers/resources 全为零，再请求 SealSkin 控制器归档 Home、删除应用并把记录标为 `deleted`。归档由 [R6C 控制器补丁](../infra/sealskin/lifecycle/environment-management.patch) 在 Home 锁内执行，Adapter 不直接操作 Home 文件。固定入口启动使用按账号、Profile 修订和一次性 token 绑定的 90 秒 launch plan。未配置该目录、独立身份或控制器补丁时，新增/归档删除表单不显示，相应写入口和目录入口返回 404；隔离范围见 R6C 验收，当前生产已由 R6F/R7F 启用。
- R6D 管理面第 4 步：配置 `proxy_template` 后，管理员可为受管理（DIRECT/proxy_required）且已存在的浏览器创建代理草稿（socks5 用户名/密码、http/https basic 或无认证，HTTPS 可附上游 CA）。Adapter 先在目录中递增该浏览器的 `proxy_secret_version`（失败或放弃的草稿也消耗版本），再经 `sealskin_admin` 身份把凭据一次性提交到控制器 Secret Store 的 `POST /api/admin/environment-management/proxy-secrets`，只保留 `secret://proxy-<id>/<field>/<version>` 引用；表单字段处理后清空，日志不含凭据。草稿为内存对象，30 分钟过期，每个浏览器同时只有一个，被替换时撤销旧版本。`proxy_probe` 调用控制器有界探针（冻结公网 IPv4、协议握手、隧道内 TLS，见 [DEV-050](../docs/deviations/DEV-2026-09-18-050-proxy-draft-probe-scope.md)）；`proxy_apply` 要求探针通过、修订未漂移、经 `/auth/reauth` 确认并且 verified Stop 后 records/workers/resources 为零，然后按顺序：控制器追加 `<id>-proxy-r<version>` 的不可变 `proxy_required` 修订（同内容幂等）→ 补丁应用定义的策略引用 → 撤销该浏览器其他凭据版本 → 写入目录修订；下一代次启动使用新策略，运行中代次不热切换。`network_direct` 以同样顺序把浏览器绑定回已登记的 DIRECT 修订并撤销全部代理凭据；删除浏览器时也撤销其全部版本。未部署生产，见 [R6D 验收](../infra/sealskin/proxy-drafts-acceptance-2026-09-18.md) 与 [DEV-049](../docs/deviations/DEV-2026-09-18-049-proxy-secret-import-channel.md)。
- R7C 统一代理目录：配置 `network_profile_catalog` 后，Adapter 以私有 `network_profiles.json` 保存逻辑代理的不可变修订、状态、授权集合、脱敏探针结果和审计事件；写入为 0600/fsync/原子替换，明文凭据不落盘。创建先保留只增版本并经现有管理员加密接口导入 `network-<id>` Secret Store；探针通过才成为 `accepted`，失败/过期先撤销；`disabled` 阻止新绑定，`revoked` 要求派生引用数为零。绑定时为目标浏览器派生精确 Profile/Home/App policy，并在同一生命周期锁内确认 stopped/0 resources、追加 policy、补丁应用、写 Profile 目录；运行中零 Stop/append/patch。脱敏 API 为 `GET/POST /manage/network-profiles` 和 `POST /manage/browsers/{id}/network-profile`；R7E 页面在能力开启时显示脱敏 Tab，探针码和实际探针时间 `probe_at`（旧记录缺失时不补造）。原始 grants 冻结为修订创建时的 ready 浏览器，R6W 新建流程可追加独立精确授权；已随 R7F 启用目录，组合验收尚未完成；候选阶段证据见 [R7C 验收](../infra/sealskin/r7c-network-profile-catalog-acceptance-2026-09-22.md)和 [R7E 验收](../infra/sealskin/r7e-management-network-home-acceptance-2026-09-23.md)。
- R7D 模板兼容目录：配置 `template_catalog` 后，Adapter 只把显式 `accepted` 的“浏览器模板 + 环境/指纹 artifact + 显示模板”三元组作为可选组合。浏览器模板固定 engine/version/OS/platform/UA 产品与新建资格，artifact 固定浏览器版本/UA、locale/languages/timezone、screen/DPR 和不可变 SHA，显示模板固定 X11/Wayland、Selkies、screen/DPR 与 scaling；加载时不一致即 fail closed。`firefox_legacy` 永远不能作为普通新增浏览器模板。`GET /manage/templates` 只返回脱敏后的兼容组合；`POST /manage/browsers/{id}/template` 在近期 reauth + manage grant 下应用或显式回退。运行中直接冲突且不会隐式 Stop；stopped/0-resources 后先持久化 `updating` 启动门禁，再以完整 PUT 替换应用定义，最后提交 Profile 新 revision 与历史模板绑定。中断时 `updating` 阻止启动，同一目标/幂等键可继续；网络 revision 不包含模板字段，因此代理变化不会静默改写指纹。已随 R7F 启用目录，r9/r10 及匹配自定义组合可选；候选阶段证据见 [R7D 验收](../infra/sealskin/r7d-browser-template-catalog-acceptance-2026-09-23.md)。
- R6E 管理面第 5 步：配置 `environment_job_spool` 后，管理员可在面板提交自定义指纹作业，只填写 locale、languages（首项须等于 locale）、IANA 时区、屏幕尺寸（DPR 固定 1）与可选窗口；Adapter 按规格 46.2 校验后派生固定规格（Linux、WebRTC/定位关闭、8 项能力），以 0600、O_EXCL、fsync 写入 spool 的 `queue/job-<hex>.json`，最多 4 个排队/运行中作业。生成、完整验收与目录追加由主机端 [environment-job.py](../infra/camoufox/environment-job.py) 执行（[DEV-051](../docs/deviations/DEV-2026-09-18-051-environment-job-runner.md)）；Adapter 只读取 `status/job-<hex>.json`（版本、job_id 与状态枚举校验，未知字段拒绝），页面与 `GET /manage/environment-jobs` 只显示高层字段、阶段、稳定代码与产物/报告摘要。通过的作业以 `source=custom` 出现在环境目录，新增浏览器表单改为从目录条目中选择；目录条目的 locale/timezone/screen/accepted_at 等描述字段只用于显示。未部署生产，见 [R6E 验收](../infra/sealskin/custom-fingerprint-acceptance-2026-09-18.md)。
- R6G 管理页视觉重构：`/manage/` 保持服务端渲染和无外部资源；R6U 新建联动使用每请求 nonce 脚本，把原九列浏览器表格改为响应式卡片；入口、健康、网络、环境和 Home 形成概览，常用设置、生命周期、高级网络与归档删除分层，账号/作业表格只在自身容器横向滚动。后续按用户反馈拆为浏览器、指纹作业、访问账号三个独立服务端 Tab，默认浏览器；账号/作业提交返回对应页，公共确认密码入口返回当前页。原有路由、字段名、权限、CSRF、重新认证和能力门控保持。该 UI 已由 [R6H](../docs/work-items/R6H-2026-09-20-management-ui-deployment.md) 以 Adapter 摘要 `fe4e13c4…` 部署，服务器健康和运行绑定复核通过；1280×800 Mac/Trilium 视觉仍待用户确认，见 [UI 说明](../docs/management-ui-redesign.md)。
- 入口 HTML 使用 `Referrer-Policy: same-origin`，让 Chromium/WebView 的自动表单 POST 保留正常 `Origin`；CSP 的 `form-action` 允许入口自身与配置的 Session origin，以支持后续 `303` 跳转。`Origin: null` 和异源启动请求仍被拒绝。
- 运行健康报告：按 Profile 汇总入口、控制面、Session 记录、Worker、浏览器主进程、显示服务、代理与公网出站状态，绑定 operation/Session/策略修订/环境产物与采样时间，60 秒有效；查询只读，不启动或重建实例。浏览器退出、显示不可用或代理故障时，入口页改为恢复提示并保留手动「继续进入会话」。已登记浏览器模板的 Profile 退出后必须经管理页「安全关闭」释放原代次，再从固定入口重建；不能从远程桌面启动基础镜像的其他浏览器代替受管模板。运行代次没有策略时标为 `network_mode=unmanaged`，代理项为 `PROXY_NOT_CONFIGURED`，另以 `EGRESS_NOT_CONFIGURED` 将整体降为 degraded；不能用进程/显示正常推断网站可访问。
- DIRECT 候选报告 `network_mode=direct`，`proxy` 为 `not_applicable / DIRECT_NO_UPSTREAM`，另有必需的 `egress` 分项；网关不可用为失败，公网探测未执行或证据不足为 unknown。没有外部代理不等于没有受管理网络。
- 空闲回收（可选）：Profile 定义 `idle_policy: {"mode": "disconnected", "timeout_seconds": 900}` 时，后台采样按 SealSkin 观测到的**已认证显示连接数**计时：连接数为 0 时记录 `idle_since`，重新连接即清除；到期前先强制重新观测，仍无连接才调用已验证的 `Stop`（可重复、失败保持 `stopping` 下次重试）。观测缺失、报告过期或状态未知时不推进也不清除；轮询、健康检查与视频帧不算活动。`input_idle` 模式未实现并被拒绝。默认关闭。
- 容量门槛（可选）：`limits` 中的 `max_active_profiles`、`max_concurrent_launches`、`min_free_disk_mib`（需 `storage_path`）在启动新代次前检查，超出返回 503 且不写 journal；已运行的 Profile 不受影响。2026-10-01 候选用全局短准入锁保护跨 Profile 的检查、占用和计数；远程启动不持该锁，见 [R6I 验收](../infra/sealskin/r6i-capacity-acceptance-2026-10-01.md)；R6AI已完成原子准入与自动容量部署。
- 休眠代次恢复：Docker 或主机重启后，本代次的会话记录仍在而全部容器已退出时，启动对账与入口会请求 SealSkin 按 **Relay → Guard（规则就绪）→ 控制器接回 → 一次性探测 → Worker → 显示端点** 的顺序恢复同一批容器；任一步失败 Worker 不启动，占用保留，绑定标为 `unknown` 并附错误码，入口返回 409。恢复从不创建新容器；`-resume-profile` 供运维显式重试。

[2026-09-13 入口回归](../infra/sealskin/entry-acceptance-2026-09-13.md)已验证 Personal/Work 的公网自动 POST 和 Session 页面跳转。

bootstrap URL 解决了一个实际的上游缺口：SealSkin 0.3.2 的用户会话列表包含 `app_id` 和 `launch_context`，不包含 `home_name`。仅靠 Home 名无法在控制进程崩溃后精确区分两个同应用会话。旧控制器或无受管理策略的启动先访问：

```text
https://browser.example.com/bootstrap/personal/<operation-id>
```

适配层校验当前操作后以 `303` 跳到 Profile 的 `start_url`。浏览器最终看到的是目标网站，SealSkin 仍保留可供恢复的唯一启动上下文。

R5C1 候选在明确协商 `profile_initial_url_version: 1` 后，将受管理浏览器的起始页和上述标记分开：SealSkin 的 `launch_context` 仍保存 bootstrap，Worker 直接打开经校验的 HTTP(S) `initial_url`。拒绝 userinfo、控制字符等无效 URL，启动后能力丢失时保留 unknown 占用；旧控制器不接收新字段，无绑定会话不自动接管。原因与兼容验证见 [DEV-011](../docs/deviations/DEV-2026-09-14-011-direct-bootstrap-url.md)。

[lifecycle 补丁](../infra/sealskin/lifecycle/README.md) 补充 Home、实例、generation 和网络资源元数据。新受管理启动要求 `network_enforcement_version: 1`，停止确认包含 Guard；bootstrap 继续用于旧无标签会话的兼容对账。

## 运行时一致性候选

R5C3 增加 [当前代次一致性门槛](../infra/sealskin/lifecycle/runtime-coherence.md)。启动、复用、恢复及响应丢失后的认领都会向控制器核对新鲜报告和完整运行绑定，失败/未知时返回 503，不发放 Session 重定向；“继续进入”也经过相同检查。省略策略的旧应用保持兼容，候选尚未部署生产。

恢复中的首次 503 可以表示容器已运行而一致性尚未就绪；私有命令不会据此断言 Worker 停止，保留原绑定并正常重试，直到当前门槛通过。

健康缓存的每个返回分支复核当前 journal，包括 Session、策略、bootstrap、resume/stop 操作；不匹配时返回 UNKNOWN，普通 GET 不启动新探测。公开健康移除顶层及一致性 binding 的 operation/Session；本机 `-coherence-profile` 命令通过私有 socket 显式采样现有代次，空 Home 不会创建 Worker。`-health-profile` 读取缓存，`-probe-profile` 刷新传统运行健康；强制探测须遵守 10 秒限流。控制器报告的城市 UNKNOWN 仍为 DEGRADED，不能称全部健康。

## 构建与测试

需要 Go 1.24 或更新版本，且当前代码只依赖标准库。

```bash
cd adapter
go test ./...
go vet ./...
go build -buildvcs=false -trimpath -o profile-adapter ./cmd/profile-adapter
```

`-buildvcs=false` 使构建不依赖 VCS 元数据；需要在二进制中记录 VCS 信息时，可在完整 Git checkout 中移除。

测试覆盖加密协议、服务端签名被篡改、crypto session 过期重握手、变更请求网络失败分类、并发单实例、丢失启动响应恢复、未知结果禁止重试、可靠停止/重启续停、残留容器与旧 generation 拒绝、网络策略引用/能力/归属检查、资源残留续停、持久化并发、HTTP 重定向，以及健康报告的绑定/新鲜度/缓存/节流/单飞、故障分项、恢复提示与脱敏。真实 Docker 故障与 race 结果见 [网络生命周期验收](../infra/sealskin/network-lifecycle-acceptance-2026-09-13.md) 和 [此前停止验收](../infra/sealskin/lifecycle-acceptance-2026-09-13.md)。

## 配置与运行

从 [config.example.json](config.example.json) 复制配置。相对文件路径以配置文件所在目录为基准。

示例已启用 `sealskin.lifecycle_enabled`，要求先安装配套 SealSkin 补丁。连接原版上游时设为 false；省略开关也默认为 false。`control_socket` 可省略，默认追加在 `state_file` 后；应使用较短路径，避免超过 Unix socket 的系统限制。

```bash
cp config.example.json config.json
chmod 600 secrets/sealskin-client-private.pem
./profile-adapter -config config.json
```

`server_public_key_file` 必须固定为所连接 SealSkin 服务的公钥。`client_private_key_file` 是 SealSkin 中该用户公钥对应的私钥；程序拒绝读取 group/other 可访问的私钥文件。

Profile 的 `application_id` 应指向经过固定版本管理的 SealSkin 应用定义。若不同 Profile 使用不同代理或环境策略，应使用各自的应用定义，例如 `firefox-personal-proxy` 和 `firefox-work-proxy`，由该定义锁定代理 relay、网络和浏览器环境。`home_name` 提供长期浏览器数据，不能拿来承载代理密码。

当前 [Go Profile Relay](../relay/README.md) 已实现并完成独立协议、sidecar 和 SealSkin Worker 实测。动态创建和停止由 SealSkin 统一执行：管理员在私有策略 registry 中固定用户、Profile、Home、应用、镜像与凭据修订，并将相同的 `network_policy_id`、`network_policy_sha256` 写入应用 `provider_config` 和 Adapter Profile 定义。启动先创建专属网络、Relay 与 Guard，安装规则并探测通过后才创建 Worker；漏传引用或缺失服务端能力均拒绝。受管理的活跃代次不接受策略漂移；轮换前必须停止并确认资源清空。配置方法见 [策略说明](../infra/sealskin/lifecycle/README.md#按-generation-分配代理与网络)。

`sealskin-configure-proxy-app` 使用一次性管理员配置热更新应用镜像和静态 `docker_overrides.network`，不会把管理员密钥写入适配层状态。以下保留静态 sidecar 的配置示例；当前受管理的 Personal 应用需按上述策略说明配置：

```bash
go run ./cmd/sealskin-configure-proxy-app \
  -admin-config ../infra/sealskin/config/admin.json \
  -api-base-url http://127.0.0.1:8000 \
  -app-id firefox-personal \
  -image browser-platform/firefox-proxy:env-tw-firefox-baseline-r1 \
  -network browser-platform-personal \
  -locale zh-TW \
  -languages zh-TW,zh,en-US,en \
  -environment-id env-tw-firefox-baseline-r1 \
  -artifact-sha256 3213e8aab48de79560ec1d34ff9524d6a517a16e080e1b95066d3c1b6d192d24 \
  -screen-width 1920 \
  -screen-height 1080
```

`sealskin-install-app` 从完整 JSON 定义创建独立应用，使用加密管理员 API 和稳定幂等键，并拒绝覆盖已有 ID。Camoufox 的应用定义由 `infra/camoufox/prepare-sealskin.py` 在镜像验证成功报告后生成；该管理操作不进入长期运行的 Profile 服务。

`sealskin-smoke-session` 可启动最长十分钟的 cleanroom 验收 Session，支持应用模式下的 `--language`、`--timezone`、`--wayland=false`。超时或收到中断信号后发起 stop 请求；必须另外确认 Docker 容器已经消失。命令只输出 Session ID，不输出 token URL。自动化客户端可以设置 `--session-file`，创建新的 `0600` 临时文件并在退出时删除，已有文件不会被覆盖。

适配层默认只监听 `127.0.0.1`。启用 `access` 后由它提供 `/auth/login`、账号授权和注销；Caddy 将两个公开 origin 的全部请求转发给 Adapter，不能为 Session 留下绕过网关的直达路由。兼容启动路径中的 GET `/bootstrap/*` 保持免登录：处理器核对随机 operation ID 和当前 Profile 状态，只能重定向到服务端预配置的 `start_url`。通用 `/healthz`、`/readyz` 也由网关豁免，不包含 Profile 绑定；运维 socket 始终只在本机。完整路由模板见 [入口 Caddyfile](../infra/sealskin/entry-auth/Caddyfile.example)。

`public_base_url` 必须是客户端可访问的 Caddy HTTPS 地址；旧控制器或无受管理策略的启动还要求 Worker 能访问它的 bootstrap 路径。支持上述初始 URL 能力的受管理启动不依赖 Worker 访问入口域名，DIRECT 继续拒绝宿主机地址。启用 `access` 时，`public_session_base_url` 是经 Adapter 授权转发的独立 Session HTTPS origin，SealSkin 自带 Caddy 仅作为私有上游。示例启用登录；旧省略 `access` 的本机配置不具有最终用户授权保证。

健康检查：

```text
GET /healthz                    只检查适配层进程
GET /readyz                     执行一次 SealSkin 加密会话列表请求
GET /browser/{profile}/health   该 Profile 的脱敏运行健康报告（读缓存或触发一次只读采集）
GET /manage/environments        全部 Profile 的只读环境摘要与分配账号 JSON（仅读缓存；需要 access 与管理员）
GET /manage/                    管理面板：浏览器与账号（仅管理员）
POST /manage/browsers/{id}      action=update|enable|disable|stop（表单 + CSRF）
POST /manage/accounts, /manage/accounts/{id}   创建 / 重置密码 / 禁用启用 / 分配 / 改角色
GET|POST /auth/reauth, /auth/password          确认密码（管理员敏感操作）/ 修改自己的密码
```

`/browser/{profile}/health` 与入口页一样由 Adapter 检查当前登录和 Profile 授权；它不包含 operation、Session ID 或授权 URL。`?cached=1` 只读取上次报告，过期时 `stale=true` 且整体为 `unknown`。

`health` 配置段（可省略，均有默认值）：

```json
"health": {
  "sample_interval_seconds": 60,
  "entry_hint": true,
  "entry_wait_seconds": 3
}
```

`sample_interval_seconds` 为后台采样间隔（0 关闭，10–3600），整体状态变化时记录日志；`entry_hint` 控制入口页是否在阻断级故障时显示恢复提示；`entry_wait_seconds` 是入口页等待报告的上限（1–30），超时或采集失败时保持原自动提交。

`profile_directory`（可选，需 `sealskin.lifecycle_enabled`）：Profile 目录文件路径，相对配置文件所在目录；设置后配置中的 `profiles` 只用于首次导入，可为空。目录文件只由持有全局服务锁的运行中 Adapter 写入；`profile-accounts` 只读该目录校验授权，读取失败时拒绝账号操作，不回退到配置种子。

`environment_catalog`（可选，启用 R6C 创建/删除时必需）是权限为 0600 的固定 JSON 文件，格式为 `{"version":1,"artifacts":[...]}`；每个可用条目必须同时提供已验收摘要、`status=accepted`、`source=frozen`、`sha256:<digest>` 镜像和完整应用模板。配置该文件时还必须配置 `sealskin_admin`，其私钥与生命周期/启动身份分开，不能写入 Profile 目录或运行状态。R6C 的 `POST /manage/browsers` 只引用目录中的产物和不可变网络策略，不接受运行时镜像、凭据或任意挂载路径。

`proxy_template`（可选，启用 R6D 代理草稿时必需，且需要 `environment_catalog` 与 `sealskin_admin`）固定每个生成的 `proxy_required` 修订共享的运维值：`owner` 必须等于 `sealskin.username`（启动身份，也是 Secret Store 授权的 owner 维度）、`relay_image` 与 `probe_image` 为主机上已存在的完整 `sha256:` 镜像摘要、`probe_url` 为批准的 HTTPS 探测目标、`probe_timeout_seconds`（1–20，默认 10）。草稿只提交协议、认证方式、公网主机/端口、凭据与可选 CA；策略 ID、摘要、Relay/Guard 配置与凭据引用全部由服务端派生。

`network_profile_catalog`（可选，启用 R7C 统一代理目录；要求 `proxy_template` 的全部依赖）是 `network_profiles.json` 的私有路径，相对配置文件解析。文件不存在时以 version 1 空目录创建；已有文件必须为普通 0600 文件且严格解码。配置项只启用服务/API，不会迁移旧 R6D 草稿、改动现有 Profile 或部署控制器。

`template_catalog`（可选，启用 R7D；要求 `environment_catalog`）是私有、严格 JSON 的兼容目录路径。version 1 分为 `browser_templates`、`display_templates` 和 `compatibility`：只有三者均为显式 accepted、ID/修订有效且引用的 environment artifact 通过 R7D 一致性校验时才会出现在管理 API。旧 R6 environment artifact 没有 `template_revision/browser_template_id/browser_engine/browser_version/os_family/platform/user_agent` 元数据时仍可由旧路径读取，但不会被猜测成 R7D 模板；正式启用前必须为目标 accepted artifact 生成并验收这些元数据。

`direct_template`（可选，启用 R7E 服务端“受管理 DIRECT”选择；要求 `environment_catalog` 与 `sealskin_admin`）固定 DIRECT policy 的运维字段。`owner` 必须等于 `sealskin.username`；`approved_resolver_id` / `approved_resolver_ip` 固定批准解析器；Relay/Probe 镜像必须为完整 `sha256:` 摘要；`probe_url` 必须为无凭据 HTTPS 地址。启用后，管理页和 `CreateBrowser` 不接受客户端提交 DIRECT policy ID/SHA，而是由 Adapter 以浏览器的 Profile/Application/Home 绑定生成新的 immutable policy。运行中的浏览器切换 DIRECT 先返回冲突，不隐式 Stop；只有确认 `records/workers/resources=0` 后才 append policy 并更新应用/目录。

R7E 管理 UI 同时启用模板、统一代理目录和受管理 DIRECT 的典型增量配置如下（摘要仅为占位符，必须替换为本机已验收值）：

```json
{
  "environment_catalog": "./var/environment-catalog.json",
  "template_catalog": "./var/template-catalog.json",
  "network_profile_catalog": "./var/network-profiles.json",
  "sealskin_admin": {
    "username": "profile-admin",
    "client_private_key_file": "./secrets/sealskin-admin-private.pem"
  },
  "proxy_template": {
    "owner": "profile-adapter",
    "relay_image": "sha256:<approved-relay-digest>",
    "probe_image": "sha256:<approved-probe-digest>",
    "probe_url": "https://probe.example/",
    "probe_timeout_seconds": 10
  },
  "direct_template": {
    "owner": "profile-adapter",
    "approved_resolver_id": "approved-dns",
    "approved_resolver_ip": "1.1.1.1",
    "relay_image": "sha256:<approved-relay-digest>",
    "probe_image": "sha256:<approved-probe-digest>",
    "probe_url": "https://probe.example/",
    "probe_timeout_seconds": 10
  }
}
```

新增浏览器必须具备可用的 `template_catalog`：页面只提交 `browser_template_id` 和 `environment_artifact_id`，服务端从当前 accepted 目录推导唯一 `display_template_id`；无目录时阻止创建，旧显示字段与三元字符串不再接收。当 `network_profile_catalog/direct_template` 可用时，网络只提交“受管理 DIRECT”或 accepted 代理目录修订。客户端 raw `network_policy_id/network_policy_sha256` 在该模式下被拒绝。新建下拉展示所有 accepted 代理，包括已保存账号密码的代理。管理员选择后，服务端持久化创建请求摘要和 creating 意图，再由控制器追加精确 owner/profile/home/app 授权，保存独立 policy 与完整上游/引用绑定。失败保留意图，同键改参被拒绝，重启后可按原请求重试；未完成记录不能启动。既有浏览器换代理仍只展示明确授权的认证修订。模板或网络切换均为“停止后应用”，历史模板 revision 由服务端列出并可显式回退。

`environment_job_spool`（可选，启用 R6E 自定义指纹作业时必需，且需要 `environment_catalog`）是归 Adapter 用户所有的 0700 目录，执行器以 `--spool` 指向同一目录并以 `--catalog` 指向同一 `environment_catalog` 文件；Adapter 只写 `queue/` 与读 `status/`，`artifacts/`、`evidence/` 由执行器写入，目录条目的挂载路径指向 spool 内的产物与报告，因此 spool 必须位于 SealSkin 控制器可 bind mount 的主机路径。

`startup.control_wait_seconds`（默认 120，0–900）：开机时 Adapter 先等待 SealSkin 会话列表可读，再逐 Profile 对账；控制面在期限内不可用时仍继续启动，Profile 保持对账前状态，入口在后续请求时再次核对。

```json
"limits": {
  "auto": true,
  "storage_path": "../infra/sealskin/storage"
}
```

`limits.auto=true` 时，省略或0表示按机器自动计算；正值可覆盖活动数量、并发启动、磁盘保留、`memory_per_profile_mib`和`memory_reserve_mib`。`auto=false`时原三项0仍表示不限，内存预算字段不得设置。自动模式需要 `storage_path`（相对配置文件所在目录）。规则和只读查看命令见[容量策略](../docs/capacity-policy.md)。Profile 定义可加 `"idle_policy": {"mode": "disconnected", "timeout_seconds": 900}`（60–86400 秒），需要 `sealskin.lifecycle_enabled` 与后台采样开启；健康报告增加非必需的 `idle` 项显示 `IDLE_CONNECTED / IDLE_DISCONNECTED / IDLE_COUNTING / IDLE_UNOBSERVED`。

## 停止与未知状态恢复

当前部署保持 Adapter 运行，通过本机控制 socket 操作：

```bash
./profile-adapter -config config.json -inspect-profile personal
./profile-adapter -config config.json -reconcile-profile personal
./profile-adapter -config config.json -stop-profile personal
```

```bash
./profile-adapter -config config.json -health-profile personal
./profile-adapter -config config.json -probe-profile personal
```

```bash
./profile-adapter -config config.json -resume-profile personal
```

`resume` 只对休眠代次（会话记录存在、本代次全部容器已退出、受管理代次的网络分配完整）执行按序恢复；实例已在运行时复核当前代次，非休眠且不能认领的状态返回 409。503 表示尚未达到已验证就绪：容器可能已运行并等待一致性观测，应保留绑定按正常接口重试，不能据此断言 Worker 已停止。`health` 返回缓存或新采集的完整报告（含 operation/Session 绑定）；`probe` 强制重新采集并经 Relay 探测上游，每 Profile 最短间隔 10 秒，过早返回 HTTP 429 与上次报告。`health`/`probe` 都只读。分项状态为 `pass/fail/warn/unknown/not_applicable`，整体按 `offline → unhealthy → unknown → degraded → healthy` 顺序计算；`recovery.blocking` 为真时入口页显示恢复提示。

运维命令失败时 CLI 输出 `profile command failed` 和固定 `error_code`，例如已完整停止、没有可恢复旧容器的 Profile 为 `PROFILE_NOT_DORMANT`；这不表示 systemd Adapter 服务停止。control reply 的错误码和旧版稳定文本映射均在最终脱敏边界内，不输出后端异常、URL、Cookie 或凭据。真正的服务启动/运行失败仍使用 `profile adapter stopped`。见 [DEV-056](../docs/deviations/DEV-2026-09-20-056-control-cli-error-classification.md)。

`inspect` 只读，显示记录、Worker、孤儿、资源、Guard、Relay 和网络数量、持久化的 `network_phase` 与启动日志阶段 `launch_phase`（`pending / creating / failed / aborted / orphaned`）；这些阶段字段不代表实时健康，实时结果见 `health`。SealSkin 报告 `launch_journal_version: 1` 时，清单为空即证明该 Home 没有进行中的创建，`reconcile` 可把“未收到 Session ID 且无容器”的模糊启动确认为 `stopped`；否则保持 `unknown`。`reconcile` 对账并续停 Adapter 或 SealSkin 已持久化的停止操作；`stop` 停止当前 generation，确认所有实例和网络资源消失后保留 Home、释放占用。超时或失败时重复执行 stop/reconcile，不能删除 journal 强行解锁。没有新增公网 stop API。

有标签的孤儿会报告 `unknown`，明确 stop 后按原 generation 清理。没有标签又丢失记录、异属挂载或配置漂移时拒绝自动操作。没有收到 Session ID 且没有可见容器的模糊启动仍保留未知状态，需要核实提交中的创建请求。

`-reset-profile` 仅兼容未启用 lifecycle 的旧部署，必须先停 Adapter 并人工确认没有占用 Home 的容器。启用 lifecycle 后此命令被禁用。

## 当前验收边界

管理网络 ACL、私有权威 DNS、Firefox 直接网络与控制容器重建已有 [v2 验收](../infra/sealskin/network-isolation-acceptance-2026-09-13.md)；Trilium 主要交互已有 [用户记录](../docs/trilium-client.md)。这些结果都有版本和环境限制。

R5C1 的两个真实 DIRECT 固定入口、初始页、重复进入、独立出站健康与持久数据恢复见 [DIRECT 验收](../infra/sealskin/direct-network-acceptance-2026-09-14.md)。候选未部署；DIRECT 需要相应控制/网关能力和主机地址证据，不能据此认为旧 Work 已迁移或最终入口鉴权已验收。

运行健康报告与恢复提示已有 [健康验收](../infra/sealskin/health-acceptance-2026-09-13.md)；基于显示连接的空闲回收、普通命名 Home 启动日志和 Home 删除保护已有 [生命周期保护验收](../infra/sealskin/lifecycle-protection-acceptance-2026-09-13.md)，历史验收时生产未启用空闲回收与容量门槛；当前自动容量见页首R6AI，空闲回收保持关闭。Camoufox 的迁移准备器只读当前绑定，生成独立候选配置并保留 journal，见 [R4A](../infra/sealskin/client-migration-acceptance-2026-09-14.md)。公开 DNS 和完整一致性候选分别已有 R5C2/R5C3 验收；Mac/Trilium 提示页、实际迁移、自动重开、正式主机/目标系统恢复及完整鉴权仍按 [开发计划](../docs/roadmap.md) 推进，不将独立 QA 结果推定为生产通过。

## Chromix 模板（R6L）

`template_catalog.go` 支持 `chromix` 引擎及匹配 major 的简化 Chromium UA；完整版本仍来自固定产物。已有 Home 不能在 Chromix 与 Firefox/Camoufox 间双向切换，原产物缺失时拒绝修改。管理新建复用现有 accepted 目录和近期认证，不接收任意镜像或启动参数；自定义生成作业仍只支持原 Camoufox 范围。最小生产更新只包含此兼容及保护，详见 [Chromix 组件](../infra/chromix/README.md)。

R6L3：编辑浏览器的三个模板下拉按当前记录分别选中；未登记/已不可选时显示不可提交的空值占位，要求显式选择。只修正回显，不改应用绑定或兼容检查。见 [验收](../infra/sealskin/r6l3-selection-acceptance-2026-10-01.md)。

R6M：已验收指纹选项/API 明确 engine/browser_version；自定义作业当前仅支持固定 Camoufox/152.0 目录版本，其他提交拒绝。Profile 的 display_preference（空值/contain/fill）与屏幕指纹独立保存，刷新远程显示页后跨客户端共用；旧 legacy Work 暂不支持非空值。Gateway 在 Session 认证/绑定之后对精确已知 JS 应用几何变换，未知摘要保持原行为。新字段保存后旧二进制不能直接解析目录，回退边界见 [R6M 验收](../infra/sealskin/r6m-display-preferences-acceptance-2026-10-01.md)。

R6N 自动分辨率已部署：兼容目录支持 Chromix/X11 的 auto@1/scaling=auto；resolution_mode 随模板绑定、历史和回退持久化。自动模式不注入 R6M 固定画面 CSS，拒绝保存 contain/fill。旧配置空值兼容；线上状态见 [验收](../infra/sealskin/r6n-auto-resolution-acceptance-2026-10-01.md)。


R6O：自动 Chromix 显示目录新增 auto@system，与 auto@1 分别显式匹配指纹产物；Profile 仍保存 resolution_mode=auto。管理 UI 不再统一宣称 DPR1，旧组合保留。已部署最小 R6N 增量；见 [验收](../infra/sealskin/r6o-ui-scaling-acceptance-2026-10-01.md)。

## R6P：独立指纹模板与显示模板

以下现行契约已由 R6Q 更新，历史 R6P 验收保留原范围。

管理员在“指纹模板”保存名称、locale/languages 和 IANA 时区等通用要求；在“显示模板”保存固定屏幕尺寸、DPR 1 与窗口尺寸。屏幕参数不在指纹表单填写。选择指纹模板、显示模板和浏览器引擎目标后创建组合任务，只有完整验收并登记兼容关系后，组合才出现在浏览器配置中。名称仅供显示，不决定身份或兼容性。

指纹模板和显示模板分别是私有、不可变的 revision 1 记录。修改配置通过新建模板完成，既有记录不覆盖。新指纹源使用 version 2 且不含 engine/browser_version；v3 作业绑定两份 ID/完整 SHA-256，以及生成目标的 browser_template_id/browser_template_revision/engine/browser_version。首次按目标生成并冻结设备参数，以后换显示只更新屏幕/窗口字段，保留其他 resolvedConfig、seeds、原 BrowserForge 来源和 preferences。缓存镜像或来源摘要变化时拒绝复用，不静默随机生成。

`GET /manage/template-sources` 返回 version 1、fingerprints、displays 和 generation_targets 摘要，不返回完整指纹或缓存。`POST /manage/fingerprint-templates`、`POST /manage/display-templates` 分别保存配置；`POST /manage/template-combinations` 接受 fingerprint_id/display_id/browser_template_id，目标不能为空且必须同时满足 accepted 目录与生成器能力。沿用管理员登录、Origin、CSRF、作业能力门控；新指纹表单拒绝 engine/browser_version，重复字段和跨表单字段拒绝，来源读取失败返回 503，不冒充空目录。

旧无 version 指纹源和 v1/v2 作业、完整 artifact、显示组合和模板历史继续读取，不自动迁移或重建真实 Home。Chromix 仍使用已有固定/自动/UI scaling 验收组合；本项不开放 Chromix 自定义生成，也不把 Camoufox 固定 DPR1 扩大为自动分辨率。画面保持比例/铺满仍是按远程浏览器保存的显示偏好；UI scaling 百分比跨客户端统一保存未实现，属 R6O 后续。

验证及部署状态见 [R6P 验收](../infra/sealskin/r6p-template-separation-acceptance-2026-10-01.md)。

R6Q 当时交付已部署，完整结果及旧模板兼容范围见 [R6Q 验收](../infra/sealskin/r6q-engine-neutral-acceptance-2026-10-01.md)。


## R6R：三引擎组合

新通用来源可选择 Camoufox152.0、Chromix154.0.8037.57、Firefox155.0.1；只有目录 accepted 且生成器版本匹配的目标返回 generation_targets。原生 Firefox 使用独立 `firefox` 引擎名，识别真实 Firefox/155.0 简化 UA，保留旧 Work `firefox_legacy`。Chromix/Firefox 非全屏窗口在入队前拒绝，跨引擎修改已有 Home 双向拒绝。其余字段/API/认证保持 R6Q 契约；旧来源仍限原 Camoufox。详见[多引擎组件](../infra/environment-engines/README.md)。

R6R已限定部署并收尾，见[三引擎验收](../infra/sealskin/r6r-multi-engine-acceptance-2026-10-01.md)。

R6S将显示来源分为自定义fixed/DPR1和系统内置auto/system，三类引擎共用。内置记录只读，空指纹页仍渲染独立生成组合区域；新增浏览器选项由实际accepted默认环境与兼容目录决定。动态作业摘要显示auto@system，来源/目标/产物保持独立绑定。状态与证据见[R6S工作项](../docs/work-items/R6S-2026-10-01-shared-display-templates.md)。

R6S服务器版本已于2026-10-01限定部署：六个accepted固定/自动默认组合和对应来源可用，运行Adapter摘要b4dc0eb6…；旧目录、账号、作业和运行浏览器保持。发布证据见[验收](../infra/sealskin/r6s-shared-display-acceptance-2026-10-01.md)。

2026-10-01 R6T复核：当前运行源为R6S冻结版本，仓库R6I原子容量准入代码仍未发布；配置未启用limits/生产idle_policy。不要用混合工作树替代实际发布源，见[审计](../infra/sealskin/r6t-server-plan-audit-2026-10-01.md)。

## R6U 新建引擎与指纹联动

“引擎”决定“指纹”可选项，指纹是完整已验收环境组合；显示配置只读展示并自动绑定。服务端在 CreateBrowser 前重新解析目录，拒绝过期、跨引擎、歧义、重复字段及伪造显示。模板失败返回可操作的刷新/重选提示，不泄露目录错误。`create_templates.go` 持有筛选与解析，`manage.go` 仅提供局部 nonce 联动；脚本禁用时指纹和提交按钮禁用。初始加载、切换、pageshow 和表单重置重新校准选项。原有编辑及组合生成入口仍遵循其契约，持久数据不迁移。验收与版本见 [R6U 验收](../infra/sealskin/r6u-linked-create-acceptance-2026-10-01.md)。

## R6V 指纹数据页面

`/manage/?tab=fingerprint-data` 统一模板入口，内部 `section=fingerprints|displays|combinations` 分别为指纹模板、显示模板与组合验收。默认/未知section回指纹模板，旧fingerprints/displays/jobs分别映射对应功能。三个POST动作及确认密码返回保留section，原业务路由和字段不变。页面原生导航不依赖脚本；R6U浏览器新建联动仍使用nonce脚本。字段归属、空状态、网关与三宽度交互验证见[R6V验收](../infra/sealskin/r6v-fingerprint-data-acceptance-2026-10-01.md)。

R6W 发布：控制器使用 `proxy-create-authorization.patch` 的加密管理员接口 `POST /api/admin/environment-management/proxy-secret-authorizations`；请求只有原版本引用、精确 grant 和创建请求 SHA-256，响应仅 `authorized`。凭据不重新进入 Adapter。目录 `allowed_profiles` 仅在控制器确认后追加，pending 导入的冻结集合不变。验收和发布见 [R6W](../infra/sealskin/r6w-existing-proxy-acceptance-2026-10-01.md)。

R6AA参考截图UI已限定部署：登录/认证、首页与管理页面统一侧栏/圆角面板，管理新增表单使用带键盘/渐进回退的原生dialog，搜索仅过滤当前列表。原认证和业务处理器不变，统计保留未知/过期语义；见[设计](../docs/reference-ui-design.md)和[验收](../infra/sealskin/r6aa-reference-ui-acceptance-2026-10-02.md)。

[R6AJ服务器完整自动回归](../infra/sealskin/r6aj-full-regression-acceptance-2026-10-02.md)：本机适用自动套件通过，外部实机/供应方/异机条件单列。

## 2026-10-02 · R6AR 共享缩放已部署

按远程浏览器保存界面缩放百分比：管理页或远程 UI Scaling 修改，刷新/新客户端共用。支持 auto@system 和旧 Wayland Work；0 跟随客户端默认，100–300、步长 25。固定 DPR1/auto@1 不接受非零。不同已打开页面需要刷新；并发修改遇到冲突提示时刷新重试。保持比例/铺满继续仅用于固定画面。

新 Adapter `8fb90eb2…` 已通过旧 Work 和三引擎 30 个真实显示场景；生产 Home、会话、Worker 与配置保持。回退旧 Adapter 前须通过新版本正常重置非零百分比并核对新增字段已消失，不能覆盖旧目录。新 Mac/Trilium 精确硬件组合未据此补造验证。详见 [验收](../infra/sealskin/r6ar-display-persistence-acceptance-2026-10-02.md)。

开机对账以当前持久化浏览器目录为准（排除已删除记录），不再只看配置文件的导入种子。每个浏览器独立保留恢复预算，单项失败不阻塞其他项。完整且归属已核对的休眠代次通过原有Relay→Guard→探测→Worker顺序恢复；DIRECT的预期Guard停止不会遮住该恢复入口。健康异常本身不改为healthy，存活Worker的Guard故障继续阻断，入口仍须经过生命周期归属/网络检查。

R6AX恢复候选：开机对账只对已确认休眠恢复的`ErrResumeFailed`在原逐浏览器195秒预算内最多续试三次，间隔两秒；每次重新检查归属和停止意图，复用持久化恢复键。其他错误不自动重试，取消立即终止，Guard原就绪门槛保持。实际发布范围见[DEV-163](../docs/deviations/DEV-2026-10-03-163-startup-resume-retry.md)。
