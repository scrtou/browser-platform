# 远程浏览器管理面设计：新增/修改/删除、代理、指纹与访问

R6AV补充：删除唯一测试管理员是本次离线维护的明确授权，不新增线上绕过最后管理员保护的接口。无预置账号使用显式v3初始化状态和CLI首位管理员命令；缺失/损坏账号文件不自动转换为该状态。旧浏览器未记录任何环境/浏览器/显示模板ID时，归档v1的environment_artifact_id使用保留值`legacy-unrecorded`，表示未记录，不是已验收产物；实际Home/应用/Profile修订与幂等归档检查保持，原目录不补造绑定。

R6AI容量发布：已收尾并部署：容量改为按机器CPU/内存/磁盘自动推导，保留逐项覆盖和实时内存/并发预算保护；当前机器算得4个活动、1个并发，迁移重新计算。两套Go test/vet、容量race、只读诊断与保护发布通过，原浏览器和会话保持。 见[验收](../../../infra/sealskin/r6ai-capacity-release-acceptance-2026-10-02.md)。

R6AG：所有现有需近期密码确认的管理操作统一使用密码弹框，成功后继续原提交。覆盖代理创建/探针/停用/撤销/删除、浏览器删除/网络绑定与迁移/模板应用回退、管理员创建/账号密码重置/启停/角色/删除，保留指纹数据删除。普通不需确认的操作不新增门槛；取消不执行，密码错误可重试；只有明确reauth响应才重试一次，普通拒绝与超时不自动重试。 见[验收](../../../infra/sealskin/r6ag-all-reauth-acceptance-2026-10-02.md)。

R6AF：指纹数据删除遇到近期密码验证时，在弹框输入当前密码并继续原已确认删除；取消/错误不删除，引用拒绝原框反馈，成功才刷新。管理页确认密码入口也使用弹框，无脚本仍有验证链接。原权限、5分钟窗口、引用保护和持久删除标记保持。 见[验收](../../../infra/sealskin/r6af-job-delete-acceptance-2026-10-02.md)。

R6AE更新：修改密码在首页/管理页打开共享弹窗，原地址保留无脚本回退；密码创建、重置和自助修改最低4、最高256个UTF-8字节，原哈希强度、当前密码验证、CSRF和其他登录撤销语义保留。浏览器详情按概览、常用设置、网络、环境模板、危险操作分页签，代理/账号按实际功能分组；短表单保持单页。指纹四类删除为直接按钮打开对象确认框，原引用保护和确认勾选保留。 见[本项验收](../../../infra/sealskin/r6ae-dialog-layout-password-acceptance-2026-10-02.md)。

R6AD展示修订：指纹数据三个创建/验收入口及四类删除入口全部弹窗化，原字段/路由/校验、内置/进行中拒绝、浏览器引用删除保护保持。取消/关闭不触发操作，见[工作项](../../work-items/R6AD-2026-10-02-fingerprint-dialogs.md)。

R6AC展示修订：四个管理功能的资源默认显示为表格，浏览器/代理/账号详细配置从行“详情 / 管理”进入；原表单DOM只移动、不复制，无脚本保留details操作。指纹/显示创建和组合生成表单折叠，记录与内置显示均为列表。原POST字段、权限、CSRF/确认与浏览器引用删除保护保持，见[工作项](../../work-items/R6AC-2026-10-02-management-lists.md)。

R6AB导航修订：管理面板作为统一工作区侧栏一级菜单展开浏览器、网络代理、指纹数据、访问账号；二级原GET导航和权限/能力门控保持。首页授权浏览器为名称、状态、打开浏览器、详情列表，详情只读缓存摘要。没有新增管理API或业务副作用。见[工作项](../../work-items/R6AB-2026-10-02-workspace-navigation.md)。

2026-10-01 R6Y 删除契约：网络代理、指纹数据和访问账号均提供折叠的删除确认表单，勾选确认并通过近期密码确认后提交。被浏览器引用的代理修订和指纹数据均拒绝删除；指纹数据检查当前绑定、未完成绑定和回退历史，来源模板通过全部保留任务追溯生成产物，不受页面 100 条上限或任务隐藏影响。无法核对来源时拒绝删除。

代理删除先撤销凭据，再以 `revision_deleted` 审计隐藏该修订；编号/审计保留，同一逻辑代理后续版本继续递增。来源模板和精确已验收组合以私有 `spool/templates/deleted` 标记移出列表和新选择，原来源/队列/产物/验收文件保留，不触发浏览器停止或磁盘清除。系统内置显示不能删除；验收任务仅可删除已结束且输出未被引用的记录，已发布组合另行删除。账号从注册表移除并撤销目标登录/显示权限，当前登录账号和最后启用管理员受保护。

新增 `POST /manage/fingerprint-templates/{id}/delete`、`display-templates/{id}/delete`、`template-combinations/{artifact}/delete`、`environment-jobs/{id}/delete`。组合以请求体 browser_template_id/display_template_id 明确三元组，统一 confirm=delete；网络沿用 /manage/network-profiles 的 action=delete，保留精确 revision/幂等键。账号使用 /manage/accounts/{id} 的 action=delete。全部受管理员/Origin/CSRF/近期确认保护，POST 不接受重复确认或选择字段。

2026-10-01 R6X 网络修改交互：已有浏览器卡片使用单个网络下拉框和应用按钮，回显持久化的网络类型/代理 ID/修订；当前绑定不可选时使用空值占位。可选代理继续要求 accepted、未过期，并对认证代理检查已有 Profile 授权；本项不新增凭据授权。`action=network_select` 在服务端解析后复用原 DIRECT/BindNetworkProfile 操作，仍要求管理员/manage、Origin/CSRF、近期密码确认、浏览器 revision、操作标识和 stopped/零资源。运行中按钮禁用，服务端仍检查实际状态。无 JS 可提交，非法或重复选择字段拒绝；详见 [R6X](../../work-items/R6X-2026-10-01-browser-network-select.md)。

## R7F 存量无策略 Work 的受控迁移

2026-09-30：没有旧受管理 policy 的 Work 不能通过 DEV-071 的兼容分支直接绑定。专用迁移使用服务端批准的私有目录，固定原 Definition/revision、完整 resolved App、已验收目标镜像与备份/恢复摘要；普通表单不能提交镜像、应用内容或 Docker 参数。目标限定保持同一 Firefox/Wayland/Home 的 managed DIRECT 网络层，原记录须停用、无环境 artifact/模板和无网络/凭据绑定，不能把它伪造为 Camoufox 模板。

迁移及回退均要求管理员/manage 授权、Origin/CSRF、近期密码确认、生命周期锁内 stopped/0 resources。外部修改前持久保存 `migrating/pending_migration`，原 revision、actor、key、目录及 DIRECT 模板摘要共同绑定重试；完整 PUT 后必须读回一致才提交 ready。pending 阻止启动、删除和普通状态清除。回退恢复原应用/Definition，保留 Home、当前 journal、账号及已追加的不可变策略；前后记录均保留停用状态。实际启用、生产公网/无直连、数据恢复及 Mac/Trilium 是独立后续验收，详见 [R7F](../../work-items/R7F-2026-09-23-production-release.md)。

状态：**设计（2026-09-17 第 2 版，按用户需求修订）及 R6A–R6F 已于 2026-09-20 收尾。生产受控启用列表、账号、名称/起始页、停用/启用和安全关闭；新增/删除、代理与自定义指纹已在现有环境按维护窗口完成组合验证。管理员页面、普通账号边界和真实自定义 artifact 已完成目标 Mac/Trilium 验收，临时 Profile 已归档删除。后续 [R6G UI 重构](../../management-ui-redesign.md) 首版由 R6H 部署；用户查看后要求按大功能分 Tab，R6H 第二版已部署并通过服务器复核，等待 Mac/Trilium 再验收，不改变本文功能与安全契约。**

2026-09-20–22 用户新增的统一代理目录、浏览器配置下拉重选、浏览器模板/指纹模板/显示模板分离和入口首页改版进入 [R7 方案 v4](../../browser-workspace-plan.md) 的顺序实施。R7A 健康语义、R7B Work 受管理 DIRECT 候选及 R7C 统一代理目录/绑定 API 均已按未部署候选收尾；下一项为 R7D 模板与兼容组合。指纹模板要求跨重启稳定并保持引擎/平台、语言/时区、screen/DPR 与显示规则一致，不随启动随机或随代理静默改写；显示模板采用用户效果名称，X11/Wayland 与 Selkies 仅作为高级详情和验收绑定。Work 公网故障见 [DEV-061](../../deviations/DEV-2026-09-20-061-work-egress-unobserved.md)，网络应用入口隐式 Stop 已由 R7C 解决，见 [DEV-062](../../deviations/DEV-2026-09-20-062-network-apply-implicit-stop.md)。本规格下方的 R6 已实现范围不能据此扩展为尚未完成的 R7D–R7F。

管理页的信息架构采用浏览器、指纹作业、访问账号三个独立服务端 Tab（`/manage/?tab=browsers|jobs|accounts`），默认浏览器页，每次只渲染选中内容；jobs 能力不可用时不显示入口且请求回退。查询参数只选择视图，不改变授权、能力或业务状态。账号/作业 POST 回到各自 Tab，浏览器操作保持旧 notice 路径；公共确认密码入口返回白名单当前页。具体视觉与验收要求见 [UI 设计](../../management-ui-redesign.md)。

相关基础：[当前架构](../../design.md)、[代理与环境规格](specification.md)、[入口登录与 Session 访问](../../../infra/sealskin/entry-auth/README.md)、[Secret Store](../../../infra/sealskin/lifecycle/secret-store.md)、[按 generation 分配代理与网络](../../../infra/sealskin/lifecycle/README.md#按-generation-分配代理与网络)、[受管理 DIRECT](../../../infra/sealskin/lifecycle/direct-network.md)、[Camoufox 产物与验收](../../../infra/camoufox/README.md)、[R6 工作项](../../work-items/R6-2026-09-16-environment-management.md)。

## 需求与修订说明

2026-09-17 用户明确需求：一个面板，可以新增、删除、修改远程浏览器；为每个远程浏览器配置代理（不配置就直连）；配置指纹（固化的或自定义的）；配置浏览器页面的登录 URL 与账号密码。本文据此修订 2026-09-16 的第 1 版提案，主要变化：

| 第 1 版（2026-09-16） | 第 2 版（本文） | 原因 |
| --- | --- | --- |
| 只在已有 Profile 之间选择，不新增/删除 | 面板可新增、修改、删除远程浏览器；Profile 定义改为服务端持久化的可修订记录 | 用户需求 |
| 指纹只能从已验收产物中选择，客户端不能提交任何指纹字段 | 保留“固化指纹”目录选择；新增“自定义指纹”：用户只提交第 46.2 节的高层字段，服务端生成、验收、发布后才可绑定 | 用户需求；仍不接受任意 resolved config |
| 代理是可选草稿，未说明“无代理”的网络形态 | 每个浏览器的网络二选一：受管理代理（http/https/socks5）或受管理 DIRECT；没有配置代理即 DIRECT，不是无 Guard 的裸容器网络 | 用户需求“不配置就直连”与无直连回退原则 |
| 访问只沿用现有账号表，未在面板管理 | 面板显示每个浏览器的固定入口 URL，可创建/重置/禁用访问账号并分配浏览器 | 用户需求“登录 URL 和账号密码” |
| 删除环境不实现 | 删除 = 停止并确认资源为零 → Home 归档（不立即物理删除）→ 撤销应用/策略/授权；物理清除是单独管理员动作 | 用户需求 + Home 删除保护 |
| 任何登录账号都可进入管理列表（R6A 按此实现） | 两级访问：管理面板只对管理员账号开放；每个远程浏览器入口用各自分配的账号密码登录 | 用户 2026-09-17 补充确认；R6B 已完成收紧，见 [DEV-045](../../deviations/DEV-2026-09-17-045-manage-list-role.md) |

“浏览器页面登录 URL 和账号密码”指平台入口：面板中每个远程浏览器展示其固定入口地址（供 Trilium 笔记保存），并管理登录该入口所用的账号与密码。用户已于 2026-09-17 确认这一理解，并补充两级访问要求：登录管理面板需要管理员账号密码，登录单个远程浏览器入口也需要账号密码（见“访问账号与登录 URL”）。目标网站的账号密码自动填充不在本设计内。

## 目标与边界

用户可以在一个受保护的管理面板中：

1. 登录后查看自己获授权的远程浏览器列表、记录状态、最近健康采样与环境产物身份（已由 R6A 实现候选）。
2. 新增远程浏览器：填写名称、起始页 URL、选择固化指纹或提交自定义指纹规格、选择代理或留空（DIRECT）、指定可访问的账号。
3. 修改远程浏览器：名称、起始页、代理、指纹、访问账号；涉及指纹/代理/引擎的修改只在浏览器停止时允许，并在下一代次生效。
4. 删除远程浏览器：先安全关闭并确认资源为零，Home 归档保留，撤销访问与配置引用。
5. 管理访问账号：创建账号、重置密码、禁用、分配浏览器；查看每个浏览器的固定入口 URL。
6. 安全关闭运行中的浏览器（复用现有 Stop）。

客户端不能提交 Docker 参数、挂载路径、SealSkin Session URL、镜像引用、resolved config、seeds 或代理密码明文之外的任何后端资源标识；所有后端对象由服务端按目录与修订解析。Trilium 继续保存稳定的固定入口地址；面板只负责配置和发起受保护的操作。

本设计不提供在线修改运行中浏览器的指纹或代理，不把删除实现为立即物理清除 Home，不新增第二个 Docker 生命周期所有者，不修改 Trilium Core。

## 现有基础与职责变化

| 能力 | 现有基础（截至 2026-09-17） | 本设计的变化 |
| --- | --- | --- |
| Profile 定义 | Adapter 启动时从配置文件 `profiles` 数组静态加载，改动需改文件并重启 | 改为 Adapter 私有的 **Profile 目录**（`profiles.json`，version/revision；Adapter 全局服务锁保证单写者，进程内互斥串行更新，0600 + fsync + 原子替换），运行中可增删改并按修订核对；配置文件中的 `profiles` 只作首次导入或只读兼容 |
| 账号 | `entry-users.json` version 1：账号、PBKDF2 派生值、Profile 列表、禁用；只有 CLI 管理 | 升级为 version 2：增加 `role`（`admin`/`user`）；面板由 admin 创建/重置/禁用账号并分配浏览器；CLI 继续可用；账号表变化仍撤销现有登录 |
| 应用定义 | SealSkin `installed_apps.yml` 由离线工具（`sealskin-install-app`、`prepare-sealskin.py`）经管理员 API 安装，拒绝覆盖 | Adapter 新增仅用于管理面的 **管理员 SealSkin 客户端**（独立密钥，只调用应用安装/更新/删除），按 Profile 修订生成应用定义；生命周期 API 仍用原用户身份 |
| 网络策略 | `profile-network-policies.json` 由管理员离线写入，策略 SHA 固定到应用与 Profile | 由 Adapter 管理面写入新修订（只追加，不改历史修订），SHA 计算沿用控制器规则；控制器已监视配置路径变化 |
| 代理凭据 | Secret Store：CLI 导入版本化凭据并授权到 owner/Profile/Home/App，撤销走控制 API | 面板创建代理草稿时由 Adapter 调用同一导入路径（tmpfs 0600 输入、只返回引用）；草稿过期/失败即撤销 |
| DIRECT | R5C1 候选已隔离验收，生产未部署，需要主机 IPv4 证据挂载 | “无代理”默认使用 DIRECT 策略；部署前置条件列入实施顺序，不用裸网络代替 |
| 指纹产物 | `environment.py generate` + `acceptance.py --phase all --recreations 10` 离线生成/验收，产物绑定精确镜像摘要 | 新增 **环境目录**（固化产物 + 验收报告索引）与 **生成作业**：自定义指纹由服务端在隔离容器中生成并验收，通过后进入目录 |
| Home | `POST /api/homedirs` 创建，删除受 R3 保护（有会话/容器/占用/启动日志即拒绝） | 新增：先 Stop 并确认为零，再把 Home 目录移到归档目录；物理清除需管理员单独执行且要求已有加密备份 |
| 生命周期 | Adapter Ensure/Stop/Reconcile/Resume，SealSkin Session/Worker/Guard/Relay | 不变；面板的关闭按钮调用 Stop；启动仍走固定入口的 launch plan 核对 |

## 核心对象

```text
Browser（远程浏览器，= Profile 记录，可修订）
├── id（固定，用于 /browser/{id}/；创建后不可改）
├── label、start_url
├── engine：camoufox（新建默认）| chromix（固定已验收模板）| firefox-legacy（仅保留现有 Work，不能新建）
├── environment_ref：EnvironmentArtifact ID + 摘要（来自环境目录）
├── network_ref：NetworkPolicy ID + SHA（DIRECT 或 proxy_required 修订）
├── home_name（创建时生成，固定）
├── application_id（由服务端派生，固定到 environment_ref/network_ref 修订）
├── required_runtime_capabilities（由目标镜像标签派生）
├── enabled（停用后禁止新的启动/复用，Home 保留）
└── revision、updated_by、updated_at
```

| 对象 | 关键字段 | 生命周期与约束 |
| --- | --- | --- |
| `profiles.json`（Profile 目录） | `version`, `revision`, `browsers[]`（上表） | Adapter 独占写入；每次修改递增全局与条目修订，写前核对当前修订（乐观锁）；运行中的浏览器只允许改 `label`、`start_url`、账号分配、`enabled` |
| `environment_catalog/` | `artifacts/<id>.json`、`acceptance/<id>.json`、`index.json`（ID、引擎、镜像摘要、locale/timezone/screen/DPR、状态 `accepted`/`generating`/`failed`/`retired`、来源 `frozen`/`custom`） | 只追加；`accepted` 必须有完整成功报告且报告绑定同一镜像摘要；退役只改状态，不删文件 |
| `environment_job` | `id`, `subject`, `spec`（46.2 高层字段）, `image_digest`, `status`, `started_at`, `finished_at`, `artifact_id`, `failure_code` | 一次只运行一个作业；在隔离容器（默认拒绝网络、只读根、内存/CPU 上限）执行 generate → verify → acceptance；失败保留报告，不发布 |
| `proxy_draft` | `id`, `subject`, `type`, `host`, `port`, `auth`, `secret_ref`, `probe_status`, `expires_at` | 短期（默认 30 分钟）；凭据只进 Secret Store，Adapter/日志只保留引用；探针通过后固化为 ProxyConfig + NetworkPolicy 修订并绑定到浏览器的下一代次 |
| `network_policy` 修订 | 现有 registry 格式；`mode=direct` 或 `proxy_required` | 只追加；DIRECT 修订使用固定解析器模板；被引用的修订不删除 |
| `account` | 现有字段 + `role` | `admin` 可管理浏览器/账号；`user` 只能查看/启动/关闭被分配的浏览器 |
| `launch_plan` | `subject`, `browser_id`, `revision`, 环境/策略/能力摘要, `expires_at`, `used_at` | 固定入口启动前由服务端生成并核对；修订漂移、过期、跨账号、重复使用拒绝 |
| `audit_event` | `subject`, `browser_id`, `revision`, `event`, `result`, 安全摘要 | 只记修订和结果，不记密码、Cookie、Session URL、完整指纹或代理主机名以外的敏感值 |
| `archive/<home>-<timestamp>/` | 归档的 Home 目录 + `archive.json`（原浏览器记录、修订、时间、操作者） | 删除浏览器后保留；物理清除是单独管理员命令，要求已有加密备份或显式确认 |

## 面板功能与服务端流程

### 列表与状态

沿用 R6A：只读，来自 Profile 目录、journal 与缓存健康报告；增加 `enabled`、`revision`、指纹来源（固化/自定义）、代理摘要（类型、主机、端口、DIRECT）和固定入口 URL。

### 新增远程浏览器

```text
admin 提交 {label, start_url, environment: {artifact_id} | {custom_spec}, proxy: {draft_id} | none, accounts[]}
  → 校验字段；自定义指纹先创建 environment_job，作业 accepted 前浏览器保持 `draft`
  → 分配 id/home_name；派生 application_id 与能力要求
  → 网络：none → 复用/创建 DIRECT 修订；draft → 探针必须已通过，固化为 proxy_required 修订
  → 写入 Profile 目录（draft → ready）
  → 经管理员客户端安装 SealSkin 应用（拒绝覆盖已有 ID）；创建 Home
  → 账号分配写入账号表；返回固定入口 URL
```

创建过程中任一步失败，记录已完成的步骤并把浏览器留在 `draft`/`failed` 状态，允许重试或删除；不会留下无记录的应用、Home 或策略。

### 修改远程浏览器

- 运行中：只允许 `label`、`start_url`（下次启动生效）、账号分配、`enabled=false`（停用后新启动拒绝，已运行代次不受影响）。
- 停止且资源为零：允许更换指纹产物或代理/DIRECT；生成新的应用定义修订与策略修订，写入新的 Profile 修订；旧修订保留供回退与审计。同一 Home 更换引擎或关键指纹字段时提示风险（Cookie 与设备指纹不再匹配），并在审计中记录。
- 引擎 `firefox-legacy` 的现有 Work 只能改标签、起始页、账号与启用状态；迁移到 Camoufox 按 R4B 的迁移准备流程另做。

### 删除远程浏览器

```text
admin 请求删除 → 必须已停止且 records/workers/resources 为 0（否则 409 ENVIRONMENT_BUSY）
  → 撤销该浏览器的显示授权与账号分配
  → Profile 记录标为 `deleting`
  → 归档 Home 目录到 archive/（同文件系统 rename；失败保持 `deleting`，可重试）
  → 删除 SealSkin 应用定义；撤销该浏览器专属的 Secret Store 授权
  → Profile 记录标为 `deleted`（保留在目录中供审计），固定入口返回 404
```

物理清除归档需要单独的管理员命令，并要求存在该 Home 的加密备份或显式的“无需备份”确认；本设计的面板不提供该按钮。

### 代理配置

沿用第 1 版的“草稿 → 探针 → 固化 → 下一代次生效”，并明确：

1. 类型 `http`、`https`、`socks5`，认证 `none` 或用户名/密码；HTTPS 可选上游 CA。字段范围、地址类别与长度先校验；私网、metadata、宿主机地址拒绝。
2. 凭据经 tmpfs 0600 输入进入 Secret Store，Adapter 只保存引用；草稿过期或探针失败即撤销引用。
3. 探针在隔离网络中验证认证、TLS、DNS 与出口，不访问宿主机/私网/未批准地址；结果带出口国家/地区供一致性策略参考。
4. 通过后创建不可变 ProxyConfig 与 `proxy_required` NetworkPolicy 修订；运行中的代次不热切换。
5. 没有代理 = `mode=direct` 的受管理 DIRECT：Guard/网关仍强制、无 VPS 裸直连；主机缺少 IPv4 证据时创建拒绝并提示，不退回无 Guard 网络。

R6D 实现（2026-09-18，候选）：Adapter 不持有 Secret Store、主密钥或策略注册表，凭据导入、草稿探针与修订追加都经控制器第二层补丁的管理员加密接口 `/api/admin/environment-management/{proxy-secrets,proxy-probe,network-policies}` 完成（[DEV-049](../../deviations/DEV-2026-09-18-049-proxy-secret-import-channel.md)）。草稿阶段没有 generation，探针在控制器进程内以冻结的公网 IPv4 完成协议握手与隧道内 TLS，只返回稳定代码；它不给出出口国家，也不替代启动时 Guard 命名空间探针与一致性门槛（[DEV-050](../../deviations/DEV-2026-09-18-050-proxy-draft-probe-scope.md)）。凭据版本为 `proxy-<browser id>` 下递增整数，每次草稿先在目录中保留版本号；应用修订按“追加策略 → 应用引用 → 撤销旧版本 → 目录修订”顺序执行，每步幂等，可用同一草稿与幂等键重试；切回 DIRECT 与删除浏览器撤销全部代理凭据版本。运行中的浏览器拒绝应用与切换。

R7C 实现（2026-09-22，候选）：可选 `network_profile_catalog` 将代理提升为独立逻辑对象。私有 `network_profiles.json` 以 0600、fsync、原子替换和严格 version 1 JSON 保存不可变修订、状态、授权集合、脱敏探针结果与审计；明文凭据不落盘。修订状态为 `pending / accepted / disabled / failed / revoked`，只有 accepted 可新绑定；引用数从 Profile 目录的 `network_profile_id / revision` 派生，被引用修订不可撤销。探针失败/过期先撤销 Secret Store 版本，停用不影响已有绑定，撤销先要求引用为零。浏览器绑定在持有 Profile 生命周期锁并确认资源为零后，按该浏览器精确 Profile/Home/App 物化 `proxy_required` policy，再补丁应用并写目录；运行中返回冲突且 Stop/append/patch 为零。认证型修订的四维 grants 冻结为创建时 ready 浏览器集合，后续新浏览器必须使用新修订；无认证修订不受此限制。详见 [R7C 验收](../../../infra/sealskin/r7c-network-profile-catalog-acceptance-2026-09-22.md)。

### 指纹配置

- **固化指纹**：从环境目录中状态为 `accepted`、镜像摘要与所选引擎已验收镜像一致的产物中选择；面板只显示名称、引擎、locale/languages、timezone、screen/DPR、验收日期。
- **自定义指纹**：用户提交第 46.2 节的高层字段（osFamily、locale、languages、timezone、screen、deviceScaleFactor、可选 geolocation 策略），服务端：
  1. 按 46.2 的范围校验；
  2. 创建 `environment_job`，在隔离容器中运行 `environment.py generate`（一次 BrowserForge + 固定转换器）；
  3. 运行 `acceptance.py --phase all`（默认 `--recreations 10`，可配置下限）；
  4. 通过后把产物与报告写入目录并标为 `accepted`，失败保留报告标为 `failed`；
  5. 只有 `accepted` 才可绑定到浏览器；作业运行时浏览器保持 `draft`。
- 不接受 UA、Canvas/Audio seed、字体、WebGL、`resolvedConfig`、`firefoxUserPrefs` 等低层字段；不允许运行时切换。
- 每个自定义作业消耗约 1.5 GiB 内存与 1.5 CPU（沿用验收容器限制），一次只运行一个；主机可用内存不足时排队并提示。

R6E 实现（2026-09-18，候选）：面板表单只接受 locale、languages、timezone、screen（DPR 固定 1）与可选窗口；Adapter 校验后派生固定规格写入私有 spool，主机执行器 [environment-job.py](../../../infra/camoufox/environment-job.py) 一次处理一个作业：固定镜像内只读根/无网络/限额生成（规格不符最多重试 3 次）→ 一次性 QA 网络与夹具上的完整 `acceptance.py --phase all --recreations 10` → 镜像 `verify` → 原子追加 `source=custom` 目录条目；失败保留产物、报告与日志并写入稳定失败码；内存不足保持排队并提示 `HOST_MEMORY_LOW`。执行位置差异见 [DEV-051](../../deviations/DEV-2026-09-18-051-environment-job-runner.md)；`osFamily` 非 Linux、DPR≠1 与 `from_proxy_on_create` 定位按 `UNSUPPORTED_CAPABILITY` 拒绝。

### 访问账号与登录 URL（两级访问）

用户 2026-09-17 确认：登录管理面板需要管理员账号密码；登录单个远程浏览器入口也需要账号密码。

- **管理员账号**（`role=admin`）：唯一可以进入 `/manage/*`（列表、新增/修改/删除、代理、指纹、账号）的角色。首个管理员由主机 CLI `profile-accounts put --role admin` 创建，面板不能自举管理员；管理员可再创建其他管理员，禁止禁用或删除最后一个启用的管理员。
- **浏览器入口账号**（`role=user`）：只能登录被分配的浏览器固定入口 `/browser/{id}/`，根页只列出被分配的浏览器；访问 `/manage/*` 返回 403，不泄漏任何浏览器信息。新增浏览器时面板默认建议创建一个专属入口账号（账号 ID 默认等于浏览器 ID，密码由管理员设置或一次性显示），也可以把已有账号分配给多个浏览器。
- 管理员账号也可以被分配浏览器，但面板提示在 Trilium 中应使用专属入口账号打开浏览器，避免把管理员登录 Cookie 留在 WebView。
- 两级登录共用 `/auth/login` 表单、短期 `__Host-` Cookie、CSRF、精确 Origin 和限速；角色只决定网关放行范围。删除浏览器、重置他人密码、禁用管理员等敏感操作要求管理员在最近 5 分钟内通过 `/auth/reauth` 重新输入密码，否则 403。
- 面板对每个浏览器显示固定入口 URL：`{public_base_url}/browser/{id}/`，并提示登录页 `{public_base_url}/auth/login`；入口 URL 不含账号或密码。
- `admin` 可创建账号、重置密码、禁用/启用、分配/取消浏览器；`user` 只能通过 `/auth/password` 修改自己的密码。
- 密码继续使用 PBKDF2-SHA256（600,000 次）派生值，表中不存明文；账号表变化撤销现有登录与显示（沿用 R5D 行为，因此修改账号会让当前用户重新登录）。
- 现有 version 1 账号表升级到 version 2 时，原有账号一律视为 `user`；管理员必须显式创建。R6A 候选曾对任何登录账号放行 `/manage/`，R6B 已按本节收紧并解决 [DEV-045](../../deviations/DEV-2026-09-17-045-manage-list-role.md)。
- 不提供长期 HTTP Basic、API token 或把凭据写入 Trilium 笔记的方式。

### 安全关闭

复用 `profile.Stop`/`Reconcile`：撤销显示、持久化停止意图、正常关闭浏览器、确认 Worker/Guard/Relay/网络/占用消失、保留 Home。停止失败或不明确时状态保持 `STOPPING`/`UNKNOWN`，允许重试或对账；按钮不能执行 `docker rm`、删除 Home 或跳过生命周期所有权检查。

## 接口

| 接口 | 用途 | 必要约束 |
| --- | --- | --- |
| `GET /manage/`、`GET /manage/environments` | 列表与只读摘要（R6A） | `admin`（R6B 已收紧）；不泄漏未授权浏览器 |
| `POST /manage/browsers` | 新增浏览器 | `admin`、CSRF、幂等键；返回记录与固定入口 URL |
| `GET /manage/browsers/{id}` | 单个浏览器详情（脱敏） | `view` |
| `PATCH /manage/browsers/{id}` | 修改（按修订号乐观锁） | `admin`；指纹/代理变更要求已停止。页面无脚本，R6B 以表单 `POST /manage/browsers/{id}`（`action=update/enable/disable/stop`）实现，PATCH 留给脚本客户端 |
| `DELETE /manage/browsers/{id}` | 删除（归档 Home） | `admin`；要求已停止、资源为零 |
| `POST /browser/{id}/start` | 启动或复用（现有） | `start`、CSRF、有效 launch plan |
| `POST /browser/{id}/stop` | 安全关闭 | `stop`、CSRF、幂等键。R6B 以面板表单 `action=stop` 实现，结果只以固定通知显示 |
| `GET /manage/environments/catalog` | 固化指纹目录 | `admin` |
| `POST /manage/environment-jobs` / `GET …/{id}` | 自定义指纹生成作业 | `admin`；一次一个；结果只含摘要与状态。R6E 以表单 `POST /manage/environment-jobs` 与 `GET /manage/environment-jobs`（JSON 列表）实现，作业摘要随 `/manage/` 页面显示；最多 4 个排队/运行中 |
| `POST /manage/proxy-drafts`、`POST …/{id}/probe`、`GET …/{id}` | 代理草稿与探针 | `admin`；只写 Secret Store 引用。R6D 以面板表单 `POST /manage/browsers/{id}`（`action=proxy_draft/proxy_probe/proxy_apply/network_direct`）实现，草稿摘要随 `/manage/` 页面显示；`proxy_apply` 与 `network_direct` 需近期重新认证、修订号与幂等键 |
| `GET/POST /manage/network-profiles` | R7C 统一代理目录、创建/探针/停用/撤销 | `admin`、能力门控、CSRF；响应脱敏，创建/停用/撤销需幂等键，停用/撤销需近期重新认证 |
| `POST /manage/browsers/{id}/network-profile` | 绑定 accepted 代理修订 | `admin`、该浏览器 `manage`、近期重新认证、浏览器/代理修订与幂等键；运行中零副作用拒绝 |
| `GET/POST /manage/accounts`、`PATCH /manage/accounts/{id}` | 账号管理 | `admin`；密码只经表单 POST，响应不回显；创建管理员、禁用/启用、改角色、重置他人密码需近期重新认证。R6B 以 `POST /manage/accounts`（创建）与 `POST /manage/accounts/{id}`（`action=reset_password/enable/disable/grants/role`）实现 |
| `POST /auth/reauth` | 管理员敏感操作前重新输入密码 | 登录中的 `admin`；5 分钟有效，不延长登录期限 |
| `POST /auth/password` | 修改自己的密码 | 任意登录账号；需当前密码、CSRF；成功后撤销其他登录 |

所有写操作要求登录、精确 Origin、CSRF、幂等键，产生审计事件；响应与日志不含密码、Cookie、Session URL、完整指纹或后端能力。

## 安全与验收门槛

- 未授权账号不能列出、创建、修改、删除、启动、查看健康或关闭其他浏览器；错误返回不泄漏存在性；`user` 角色不能进入管理面板、没有任何写配置能力；管理员的敏感操作需要近期重新认证。
- 指纹只能落到目录中 `accepted` 的产物；自定义作业失败不发布；运行中变更拒绝；新的组合产生新的应用/策略/Profile 修订与新代次。
- 任意代理不可绕过 Guard/Relay；无代理即受管理 DIRECT；私网/metadata/宿主机访问、协议不支持时拒绝；代理凭据不出现在客户端、Worker、镜像、Home、URL、普通日志或公开报告。
- 删除前确认 Worker、显示、Guard、Relay、网络与占用清理；Home 归档而非清除；journal、修订与审计保留。
- launch plan 过期、重复使用、跨账号、跨浏览器或修订漂移拒绝；所有修改具备幂等键和审计事件。
- 固定入口 URL、现有 Trilium 使用方式和生产 Work 会话保持兼容；现有静态配置的 Profile 在首次启用目录时原样导入。

## 实施顺序

该设计归入 R6，实施时分为独立可验收的子项；每个子项都保留固定入口 URL、Home 独占、Guard/Relay 无直连和现有生命周期所有权：

1. **R6A 只读列表**（已完成候选代码与 Go 测试，2026-09-17）。
2. **R6B 目录与角色**（candidate-2 已完成代码与 Go 测试，2026-09-18 收尾，未部署）：Profile 目录（导入现有配置、修订、乐观锁、热更新）、账号表 version 2 的 `role`、管理面板改为仅管理员（修复 [DEV-045](../../deviations/DEV-2026-09-17-045-manage-list-role.md)）、`/auth/reauth` 与 `/auth/password`、`stop` 能力与面板关闭按钮；修改 `label`/`start_url`/账号分配/`enabled`；账号表变化按账号撤销；账号 CLI 的目录权威边界与锁契约见 [DEV-046](../../deviations/DEV-2026-09-18-046-profile-directory-cli-grants.md)、[DEV-047](../../deviations/DEV-2026-09-18-047-profile-directory-lock-contract.md)。见 [R6B 验收](../../../infra/sealskin/environment-directory-acceptance-2026-09-17.md)。
3. **R6C 新增与删除（固化指纹 + DIRECT/现有代理修订）**（候选代码已完成隔离验证，未部署）：管理员 SealSkin 客户端、应用安装/删除、Home 创建与控制器归档、launch plan；环境目录只接受已验收固化产物和完整应用模板，创建失败可重试，删除先 Stop 并确认资源为空。DIRECT 生产前置（主机 IPv4 证据、网关镜像、控制器能力）作为本步的部署条件；归档 API 的上游缺口与补丁见 [DEV-048](../../deviations/DEV-2026-09-18-048-home-archive-controller-api.md)。
4. **R6D 代理草稿、探针与修订**（候选代码已完成隔离验证，未部署）：控制器管理员接口的 Secret Store 导入、有界探针、`proxy_required` 修订追加与下一代次绑定，切回 DIRECT 与删除时撤销凭据；见 [DEV-049](../../deviations/DEV-2026-09-18-049-proxy-secret-import-channel.md)、[DEV-050](../../deviations/DEV-2026-09-18-050-proxy-draft-probe-scope.md) 与 [R6D 验收](../../../infra/sealskin/proxy-drafts-acceptance-2026-09-18.md)。真实上游代理与生产验证归 R6F。
5. **R6E 自定义指纹作业**（候选代码已完成隔离验证，未部署）：高层字段校验、私有 spool、主机执行器的隔离生成/完整验收/镜像核对/目录追加、失败保留与不发布、内存排队提示；见 [DEV-051](../../deviations/DEV-2026-09-18-051-environment-job-runner.md) 与 [R6E 验收](../../../infra/sealskin/custom-fingerprint-acceptance-2026-09-18.md)。执行器安装与真实客户端归 R6F。
6. **R6F 组合 QA 与生产候选**（已于 2026-09-20 收尾）：Adapter 管理面安全子集和控制器 overlay 已部署；Trilium/Mac 管理页面、可逆修改、账号及普通账号边界通过。现有环境完成创建/归档删除、真实代理、固化/自定义指纹、控制根与两个生产 Home 恢复、完整停启矩阵、实际回退和真实 Mac 自定义 artifact 验收；临时 Profile 已安全关闭、资源归零并归档删除。新增/删除、代理和自定义作业是否长期开放仍由生产能力配置控制。

第 1 版中“关闭入口”作为第 2 步、“指纹选择”作为第 3 步的顺序已被上述顺序取代。生产只启用由运行配置明确报告可用的能力；未配置 `environment_catalog`、独立 `sealskin_admin`、代理模板或作业 spool 时，页面不得展示相应操作，写入口也必须拒绝。R2 的退出登录与 Debian 13 未执行，并已由用户于 2026-09-20 移出当前交付范围。

### R7D 模板修订扩展

R7D 在 R6 accepted artifact 之上增加独立 `template_catalog`：浏览器模板、环境/指纹 artifact 与显示模板只能通过显式 `accepted` compatibility 三元组组合，不允许管理页面自由拼接低层字段。浏览器模板固定 engine/version/OS/platform/UA 产品族及是否允许新建；环境 artifact 固定 browser version/UA、locale/languages/timezone、screen/DPR 与不可变摘要；显示模板固定 X11/Wayland、Selkies、screen/DPR 与 scaling。任一字段不一致、引用非 accepted artifact、旧 artifact 缺 R7D 元数据或 `firefox_legacy` 被标为可新建时均 fail closed。

关键模板切换不复用会隐式 Stop 的旧流程。Adapter 持同一 Profile 生命周期锁先证明 stopped 且 records/workers/resources 全为零，再把 Profile 原子写成 `updating` 和 pending target；该状态拒绝启动。随后用完整应用定义的 PUT 替换 SealSkin 应用，避免 PATCH deep-merge 遗留旧模板字段；成功后提交新 Profile revision，并把上一套完整模板绑定按 Profile revision 写入历史。应用替换或目录提交中断时 `updating` 保留为启动门禁，同一 base revision/目标/幂等键可继续。显式 rollback 只接受历史中的精确 accepted 绑定；网络 policy/profile/Secret Store 引用不属于模板绑定，因此模板回退不改变代理，网络 revision 也不会改写浏览器/指纹/显示模板。R7E 将已验证目录呈现为分别选择浏览器、指纹和显示模板的下拉及脱敏网络代理 Tab；最终三元组合仍由服务端验证，目录为空不退回手填策略。网络代理探针结果可选保存实际 `probe_at`，旧失败记录不补造时间。R7E 同时提供只读授权首页，过期健康显示未知；R7F 负责生产目录生成、发布与目标 Mac/Trilium 视觉验收。

R6L：Chromix 只提供固定 Linux/en-US/UTC/1280×720/DPR1 模板。已有 Home 在 Chromix 与 Firefox/Camoufox 间双向切换均拒绝，原 artifact 缺失时同样拒绝；新引擎须新建独立 Home。自定义产物作业继续仅限 Camoufox。默认 Chromium UA 简化版本按相同 major 核对，完整版本单列；其他环境组合和完整跨接口指纹未验收。见 [组件契约](../../../infra/chromix/README.md)。

R6L2：Chromix cjk-r2 是 en-US/UTC 的中文字体覆盖修订，并非切换中文语言。只有停止且资源清零后才能应用新镜像/产物；保持独立 Home 和种子，旧修订可回退。

R6L3 编辑回显契约：浏览器、指纹、显示下拉必须选中行级当前绑定，不得使用目录首项替代。当前 ID 为空或未出现在可选目录时显示空值禁选占位，并要求管理员明确选择；不得自动提交另一个有效配置。

R6M 用户确认：显示偏好跟随远程浏览器保存，跨客户端共用，与固定 screen/DPR 和底层显示模板独立；保持比例/铺满窗口只影响客户端画面。指纹选择须明确引擎/版本，选择仅限已验收组合，不允许伪造任意引擎版本。

R6M 实现：已验收指纹和引擎选项显示 engine + browser_version；自定义生成目标目前为 Camoufox/152.0 绑定版本，其他引擎/版本提交拒绝，不代表 Chromix 自定义生成已支持。显示偏好保存入口复用 update 的管理授权、近期确认/Origin/CSRF 和乐观 revision 校验；空值、contain、fill 白名单，不接受远程分辨率命令。旧未登记模板 Work 不接受非空显示偏好，固定模板支持范围与回退见 [R6M 验收](../../../infra/sealskin/r6m-display-preferences-acceptance-2026-10-01.md)。


## R6O · UI scaling 修订（服务器已部署，2026-10-01）

Chromix 新增 v2 环境规格：screen.mode=auto、screen.dpr=system，目录 screen=auto@system；移除强制 scale=1，保留 R6N 自动尺寸、最大物理像素 3840×2160、显式种子、字体、网络与正常退出层。网页的 CSS screen/窗口尺寸随系统 DPI 改变，DPR 跟随 UI Scaling；客户端 DPR 2 的 Selkies 默认缩放也可为 200%。旧 v1 auto@1/固定产物保持原契约。

自动模式仍由 Profile 模板绑定保存。UI Scaling 的具体百分比沿用 Selkies 自身客户端设置，并非新增的跨客户端共享 Profile 字段；新客户端可按自身像素密度初始化。跨客户端统一百分比、并发客户端冲突处理不在本修复中冒称完成。新修订需正常停止后应用，不能热改旧环境。

本次增量只改 launcher 的版本化 DPR 契约及目录兼容/UI说明；网络、账号、存储与退出层引用 R6N 已通过基础镜像证据，不冒称完整重跑。新镜像必须通过真实 UI 控件、尺寸/点击/输入和正常关闭验收后才发布。工作项：[R6O](../../work-items/R6O-2026-10-01-ui-scaling.md)。

## R6P：独立指纹模板与显示模板

以下现行契约已由 R6Q 更新，历史 R6P 验收保留原范围。

管理员在“指纹模板”保存名称、locale/languages 和 IANA 时区等通用要求；在“显示模板”保存固定屏幕尺寸、DPR 1 与窗口尺寸。屏幕参数不在指纹表单填写。选择指纹模板、显示模板和浏览器引擎目标后创建组合任务，只有完整验收并登记兼容关系后，组合才出现在浏览器配置中。名称仅供显示，不决定身份或兼容性。

指纹模板和显示模板分别是私有、不可变的 revision 1 记录。修改配置通过新建模板完成，既有记录不覆盖。新指纹源使用 version 2 且不含 engine/browser_version；v3 作业绑定两份 ID/完整 SHA-256，以及生成目标的 browser_template_id/browser_template_revision/engine/browser_version。首次按目标生成并冻结设备参数，以后换显示只更新屏幕/窗口字段，保留其他 resolvedConfig、seeds、原 BrowserForge 来源和 preferences。缓存镜像或来源摘要变化时拒绝复用，不静默随机生成。

`GET /manage/template-sources` 返回 version 1、fingerprints、displays 和 generation_targets 摘要，不返回完整指纹或缓存。`POST /manage/fingerprint-templates`、`POST /manage/display-templates` 分别保存配置；`POST /manage/template-combinations` 接受 fingerprint_id/display_id/browser_template_id，目标不能为空且必须同时满足 accepted 目录与生成器能力。沿用管理员登录、Origin、CSRF、作业能力门控；新指纹表单拒绝 engine/browser_version，重复字段和跨表单字段拒绝，来源读取失败返回 503，不冒充空目录。

旧无 version 指纹源和 v1/v2 作业、完整 artifact、显示组合和模板历史继续读取，不自动迁移或重建真实 Home。Chromix 仍使用已有固定/自动/UI scaling 验收组合；本项不开放 Chromix 自定义生成，也不把 Camoufox 固定 DPR1 扩大为自动分辨率。画面保持比例/铺满仍是按远程浏览器保存的显示偏好；UI scaling 百分比跨客户端统一保存未实现，属 R6O 后续。

验证及部署状态见 [R6P 验收](../../../infra/sealskin/r6p-template-separation-acceptance-2026-10-01.md)。

## R6Q 通用指纹配置与生成目标

用户确认的新契约：新指纹源 version 2 不绑定引擎/版本，只保存名称、语言和时区等通用要求；生成组合时显式选择服务端支持的 accepted 浏览器模板，v3 作业冻结 ID/revision/engine/version 目标快照。产物、镜像和验收继续严格绑定。通用来源缓存按目标隔离，同目标换显示复用原设备，镜像漂移拒绝；旧来源与 v1/v2 作业保留原约束和缓存。R6Q 当时生成能力限 Camoufox 152/Linux、固定 DPR1，不能从通用配置推定其他引擎已支持。实施/部署状态见 [R6Q 工作项](../../work-items/R6Q-2026-10-01-engine-neutral-fingerprint-templates.md)。

R6Q 当时交付已部署，完整结果及旧模板兼容范围见 [R6Q 验收](../../../infra/sealskin/r6q-engine-neutral-acceptance-2026-10-01.md)。

## R6R 三引擎自定义生成

承接 R6Q，生成目标扩展为 Camoufox152.0、Chromix154.0.8037.57、原生Firefox155.0.1（Linux x86_64）。目标 ID/revision/engine/version 与 accepted 目录严格匹配；最终 artifact、缓存及验收精确绑定不可变镜像。Chromix/Firefox 只接受固定 DPR1、窗口等于屏幕的显示模板，Adapter 入队前与 runner 均拒绝不支持尺寸；现有自动分辨率/UI scaling 模板保持。

Chromix 同来源/目标跨显示复用种子和受管理语言偏好，WebRTC 契约为 proxy-only。Firefox 固定语言/时区和原生设备特征，不伪造独立设备身份，WebRTC 禁用。两者 `.chromix`/`.firefox` Home 数据独立，已有 Home 跨引擎双向拒绝；旧 Work 不迁移。

新增引擎必须通过完整两 Home 十次重建、存储/离线恢复、代理/直连阻断、桌面显示与输入后才登记环境和兼容三元组。报告不可覆盖，已通过报告支持发布恢复，失败报告和来源/镜像漂移拒绝发布。空目录的 null 列表规范为 []，不覆盖既有条目。实现、操作、实测原生特征与版本边界见 [组件说明](../../../infra/environment-engines/README.md)；交付状态见 [R6R 工作项](../../work-items/R6R-2026-10-01-multi-engine-generation.md)。

## R6S 三引擎共用显示模板

承接用户确认，自定义显示模板保持固定尺寸与DPR1（100%），允许合法独立窗口；系统内置“自动分辨率 · DPR随缩放变化”使用auto/system。两类来源均不绑定引擎，可与Camoufox152、Chromix154、Firefox155组合。内置模板只读且始终可见，不接受用户改写成自定义记录。指纹源仍只保存语言/时区，生成组合时选择引擎。

内置来源固定ID `display-0000000000000001`、revision1、mode=auto、builtin=true、dpr_mode=system；初始尺寸1280×720只作规格校验，实际画面随客户端变化，物理上限3840×2160。组合spec.screen使用mode=auto/dprMode=system并省略deviceScaleFactor，目录screen=auto@system/scaling=auto。旧Chromix auto@1及已冻结fixed产物保持原行为。

Camoufox自动产物v2移除固定显示覆盖，系统DPI决定DPR；fixed保持v1。Chromix v4、Firefox v3同时支持fixed和auto/system。Camoufox首次设备源使用1920×1080参考尺寸提取设备配置，再组合用户显示；保留BrowserForge来源及非显示字段，缓存来源/目标/镜像变化时拒绝重抽。不同DPR可能改变实际画布栅格化，画布稳定性在相同DPR比较；语言、时区、种子及其他非显示字段仍固定。

空指纹页独立显示生成组合入口和全部可用引擎，没有指纹源时禁用提交并提示先保存。默认三引擎各需完整accepted固定/自动组合，只有目标记录不算可新建。现有浏览器停止且资源清零后应用兼容组合，跨引擎仍须新Home。UI Scaling不是网页缩放，具体百分比的跨客户端统一保存仍属R6O后续。完整重建、恢复、实际客户端和发布门槛见[组件](../../../infra/environment-engines/README.md)，状态见[R6S工作项](../../work-items/R6S-2026-10-01-shared-display-templates.md)。

2026-10-01实现/验收增量：上述六个默认兼容组合已限定发布，空页入口、默认新建选择、三引擎fixed/auto与完整重建/恢复达到原门槛；不改变现有浏览器绑定。[R6S验收](../../../infra/sealskin/r6s-shared-display-acceptance-2026-10-01.md)记录当前版本及未测客户端范围。

## R6U 新建引擎与指纹联动

用户确认新增浏览器只保留引擎和指纹两个下拉：指纹项代表选定引擎的已验收环境组合，包含显示配置。切换引擎刷新可选产物，不显示独立显示选择。提交引擎ID和产物ID，由服务端按当前accepted兼容目录确定唯一显示绑定；组合失效/跨引擎/歧义均在创建副作用前拒绝。旧新建表单的显示ID/组合字符串不再兼容；不清理历史持久数据。生成组合和编辑现有浏览器不属本次UI变更。局部联动使用每请求nonce脚本，其他网关边界保持。状态见[R6U](../../work-items/R6U-2026-10-01-linked-create-templates.md)。

## R6V 指纹数据入口

管理页统一使用 `tab=fingerprint-data`，内部白名单 `section=fingerprints|displays|combinations`；默认和未知section回指纹模板。旧fingerprints/displays/jobs入口分别映射三个功能。指纹与显示POST返回各自功能，组合/旧作业POST返回组合验收，失败notice同样返回；确认密码next保留有效section，不能引入任意URL。

来源保存后还需组合验收，完整accepted组合与来源列表分开展示，待验收任务不冒充可新建环境。空依赖禁用组合提交并给出对应功能入口，目录错误保持不可用响应；内置自动显示只读。仅UI和导航重组，不改变来源格式、accepted门槛、生成队列、权限/CSRF/Origin或R6U两下拉绑定。见[设计](../../fingerprint-data-ui-design.md)及[R6V工作项](../../work-items/R6V-2026-10-01-fingerprint-data-ui.md)。

## R6W 新建复用代理（已发布）

新增浏览器可选任一 accepted 代理修订。管理员选择已有认证代理等价于为这次新浏览器的 owner/profile/home/app 追加精确凭据授权；不重新提交密码、不改变原上游/凭据版本。服务端先持久记录创建请求摘要，外部步骤失败只允许同请求重试。原版本 grants 不变，追加授权独立认证并随原版本撤销。目录的 allowed_profiles 在确认授权后追加；pending 凭据导入仍使用最初冻结集合。此契约取代“未来新浏览器必须新建代理修订”的创建限制，既有浏览器换代理维持原授权检查。

R6Z1 修复已部署：Chromix v4 同屏尺寸固定窗口采用最大化几何，较小窗口保留独立尺寸；验收仍精确比较 outerWidth/outerHeight。同版本镜像维护可显式追加缓存运行时修订，要求除镜像外来源/目标/种子完全一致，保留原缓存和失败记录；新组合仍须完整验收。进度与范围见 [R6Z1](../../work-items/R6Z1-2026-10-01-chromix-window-geometry.md)。

R6AA（2026-10-02）视觉改版已部署：侧栏对应原服务端Tab，指纹数据仍分三个子功能；浏览器/代理/账号新增表单有原生dialog渐进增强与无脚本内联回退。搜索只过滤当前已返回列表。删除、认证、字段、状态所有权和后端副作用不变，详情见[参考设计](../../reference-ui-design.md)。

[机器容量策略](../../capacity-policy.md)：自动计算、逐项覆盖、实时内存保护和只读诊断。

### R6AL · 首页网络配置摘要

首页授权浏览器列表增加网络列，使用已有 `HomeCard.Network`/`NetworkIssue`，与详情来自同一次缓存摘要。已知模式使用中文名称，缺失/不可用明确占位，异常配置显示需要处理；只显示配置模式，不判定实时连通性，不追加探测或网络目录/凭据查询。原授权过滤、转义、详情、打开入口和业务接口保持。布局/显示规则见 [参考设计](../../reference-ui-design.md#r6al--工作区网络列)，交付状态见 [R6AL](../../work-items/R6AL-2026-10-02-workspace-network.md)。

### R6AM · 首页绑定代理名称

R6AL 网络模式显示由用户反馈修订：首页代理网络以当前绑定目录的名称显示。`EnvironmentSummary.network_profile_label` 仅从 `NetworkProfileID/Revision` 对应内存记录取得，`HomeCard.NetworkName` 只向已有授权首页传递名称，不传递地址/凭据，也不新增探测。直连不关联代理名称；缺失/错误修订/目录不可用返回空名称，由列表显示“代理名称不可用”。现有禁用修订仍可被浏览器使用，名称显示不以是否允许新绑定判断。详情保留模式并附上名称。见 [R6AM](../../work-items/R6AM-2026-10-02-workspace-proxy-name.md)。

## R6AR：共享界面缩放百分比（已部署）

Profile `ui_scaling_percent` 保存 0（客户端默认）或 100–300、步长 25 的百分比。仅已登记 accepted `auto@system` 显示组合和旧 Wayland Work 支持；固定画面/DPR1 与旧 `auto@1` 拒绝非零值。切换模板清零，恢复目标显示契约。保持比例/铺满继续只用于固定画面。

管理页面可修改百分比；已授权且绑定有效的 Session 通过独立同源、CSRF 保护的显示设置入口保存 Selkies UI Scaling。该入口仅允许修改当前 Session 对应的 Profile，不提供 Profile 参数，不触发 Home/Worker 生命周期。Profile revision 冲突返回 409，界面提示刷新，不能自动覆盖其他客户端的保存。保存成功后当前客户端发送原生 DPI 消息；刷新、重连或新客户端读取服务器设置。已打开的其他控制页面需要刷新，不宣称实时同步。精确已审核资产摘要才允许变换，未知 JS 保持原样。

新能力的验收与部署状态以 [R6AR](../../work-items/R6AR-2026-10-02-display-persistence.md) 为准，以上历史 R6O/R6S 的“未持久化”描述保留当时范围。

## R6AW：1.0 内置数据契约

本项已完成并部署，完整24组合和四份固定Camoufox桌面补验结果以[R6AW工作项](../../work-items/R6AW-2026-10-02-protected-builtins.md)为准。发行版规定4个通用指纹：US（en-US、America/New_York）、TW（zh-TW、Asia/Taipei）、JP（ja-JP、Asia/Tokyo）、CN（zh-CN、Asia/Shanghai）；完整语言列表以源码种子为准。固定保留ID为`fp-0000000000000001`至`fp-0000000000000004`，version2/revision1/builtin=true。来源仍无引擎、设备、screen或DPR字段。

显示种子只有既有`display-0000000000000001`自动分辨率/system DPR，以及新增`display-0000000000000002`固定1920×1080、窗口1920×1080、DPR1。两者均revision1/builtin=true。自动显示的历史创建时间与字节不变。来源初始化仅补齐缺失文件，不覆盖已有文件；保留ID的内容、builtin标志或删除标记异常时拒绝加载，不能静默修复或隐藏。API不能创建、修改或删除保留来源，UI不提供删除表单。显示尺寸按mode判断，不能把所有内置显示都呈现为自动模式。

三引擎×四指纹×两显示的24个组合分别运行既有完整验收后，发布器才给精确的compatibility三元组写入builtin=true。内置组合不能经API或UI删除。普通用户后来生成的组合不因使用内置来源而自动变成内置；重复发布同一已安装组合保留其builtin标志。验收队列/合成Home不随内置数据安装；管理员账号不预置。来源种子存在不代表组合accepted，也不代表浏览器不可识别。
