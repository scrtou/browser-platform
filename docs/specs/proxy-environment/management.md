# 远程浏览器管理面设计：新增/修改/删除、代理、指纹与访问

状态：**设计（2026-09-17 第 2 版，按用户需求修订）；第 1–5 步（只读列表；目录、角色、管理员面板、关闭；新增/删除与 launch plan；代理草稿、探针与修订；自定义指纹作业）已完成候选代码与隔离测试，第 6 步未实施，均未部署生产**。本文把远程浏览器的新增、修改、删除，每个浏览器的代理、指纹、起始页和访问账号，纳入现有 Adapter/SealSkin 生命周期；不表示任何生产入口已经启用这些操作。

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
├── engine：camoufox（新建默认）| firefox-legacy（仅保留现有 Work，不能新建）
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

### 指纹配置

- **固化指纹**：从环境目录中状态为 `accepted`、镜像摘要与当前 Camoufox 镜像一致的产物中选择；面板只显示名称、引擎、locale/languages、timezone、screen/DPR、验收日期。
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
6. **R6F 组合 QA 与生产候选**：独立 QA、真实客户端（Trilium/Mac）、备份/恢复、日志脱敏、回退演练后，才准备生产候选与部署。

第 1 版中“关闭入口”作为第 2 步、“指纹选择”作为第 3 步的顺序已被上述顺序取代；R6A–R6E 均只在候选或隔离环境验证，本文件不授权部署或改变现有 Profile。R2 的退出登录与 Debian 13 仍待外部条件。
