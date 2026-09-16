# 环境管理面设计：访问、代理、指纹与关闭

状态：**设计提案，未实施**。本文把账号访问、手动代理、已验收指纹选择和手动关闭纳入现有 Adapter/SealSkin 生命周期；不表示任何生产入口已经启用这些新操作。

相关基础：[当前架构](../../design.md)、[代理与环境规格](specification.md)、[入口登录与 Session 访问](../../../infra/sealskin/entry-auth/README.md)、[Secret Store](../../../infra/sealskin/lifecycle/secret-store.md)、[R6 设计工作项](../../work-items/R6-2026-09-16-environment-management.md)。

## 目标与边界

用户可以在一个受保护的管理页面中：

1. 登录并只查看自己获授权的环境。
2. 从已经生成、验证和发布的环境产物中选择一个指纹环境。
3. 录入代理配置，经过隔离测试后绑定到下一次启动。
4. 安全关闭当前环境，保留 Home 和配置。

客户端不能提交任意 Camoufox 配置、挂载路径、Docker 参数、SealSkin Session URL 或代理密码。Trilium 继续保存稳定的 Profile 入口；管理页面只负责选择和发起受保护的操作。

本提案不提供在线修改运行中浏览器的指纹或代理，不把关闭操作实现为删除 Home，也不新增第二个 Docker 生命周期所有者。生产 R5D 入口候选尚未部署，实施前仍需合并 R4B 的 r9 App/策略迁移材料。

## 现有基础与职责

| 能力 | 现有基础 | 本提案的扩展 |
| --- | --- | --- |
| 账号登录 | R5D 的 Adapter 账号表、PBKDF2-SHA256、短期 `__Host-` Cookie、CSRF、Origin 检查和限速 | 增加环境级能力授权和管理页面接口；不使用长期 HTTP Basic 作为显示凭据 |
| 显示访问 | Adapter 一次性交接、显示 Cookie、Session/主体/Profile/当前绑定核对 | 管理操作完成后重新交接；授权撤销立即取消显示请求 |
| 指纹产物 | `browser_environments`、不可变 `environment_artifacts`、Camoufox 摘要和成功报告 | 只能从已批准产物中选择；同一个 Home 不在运行中切换指纹 |
| 代理 | `proxies`、`network_policies`、R5A 协议矩阵、R5B Secret Store、Guard/Relay | 增加短期代理草稿、隔离探针和下一代绑定流程 |
| 生命周期 | Adapter `Ensure`/`Stop`/`Reconcile`、SealSkin Session/Worker/Guard/Relay | 关闭按钮调用现有 Stop；不直接操作 Docker 或删除数据 |

Adapter 负责业务授权、修订和操作日志；SealSkin 继续负责 Session 与 Docker 资源；Relay 只得到运行时所需的代理密钥；Worker 不得到主密钥或上游代理凭据。

## 核心对象

第一版可以把一个可选择的环境直接建模为一个独立 Profile。每个 Profile 绑定一套不可变组合：

```text
Profile / 环境槽位
├── 独立 persistentHome
├── EnvironmentArtifact（引擎、指纹、屏幕、DPR、语言、时区）
├── ProxyConfig 修订或 DIRECT NetworkPolicy 修订
├── 受验收的 Worker 镜像与能力版本
└── ProfileAccess（账号与能力）
```

如果将来需要一个 Profile 下维护多个槽位，再增加 `environment_slots` 目录；当前不为“启动时随意拼接指纹、代理和 Home”建立新的组合器。

建议补充的 Adapter 元数据如下：

| 对象 | 关键字段 | 生命周期 |
| --- | --- | --- |
| `profile_access` | `subject`, `profile_id`, `capabilities`, `revision`, `enabled` | 修订不可变；账号变更撤销登录 |
| `proxy_draft` | `id`, `owner`, `type`, `endpoint`, `secret_ref`, `probe_status`, `expires_at` | 短期、一次绑定或过期删除；不保存明文密码 |
| `launch_plan` | `id`, `subject`, `profile_id`, 精确环境/代理/策略摘要, `expires_at`, `used_at` | 由服务端创建，短期、一次性、不可转移 |
| `audit_event` | `subject`, `profile_id`, `operation_id`, `event`, 安全摘要, `result` | 只记修订和结果，不记秘密、Cookie 或完整指纹 |

已有 `profiles`、`environment_artifacts`、`proxies`、`network_policies`、`runtime_bindings` 和 `audit_events` 继续作为事实来源。修订写入必须在 Profile 停止、Home 占用明确和生命周期锁保护下完成。

## 访问与授权流程

访问页面使用现有登录入口：

```text
HTTPS 登录
  → 短期登录 Cookie
  → 列出授权 Profile 与状态
  → 选择 Profile / 已批准环境产物
  → 选择已有代理或提交代理草稿
  → 服务端创建 launch_plan
  → 启动/复用前再次核对授权、修订和当前绑定
  → 交接一次性 Session 显示访问
```

客户端只提交选择项和 CSRF，不提交后端 Session 地址。服务端先生成 `launch_plan`，把账号、Profile、Home、环境产物摘要、代理/网络策略摘要和能力版本冻结在一起；启动时如果任一修订发生变化，计划失效并要求重新选择。

推荐的最小接口：

| 接口 | 用途 | 必要约束 |
| --- | --- | --- |
| `GET /manage/environments` | 返回账号获授权的 Profile、标签、状态和有限环境摘要 | 不泄漏未授权 Profile 是否存在，不返回完整 resolved config |
| `POST /manage/launch-plans` | 创建一次性启动计划 | 校验能力、Home、代理、网络和 Profile 访问权；短 TTL |
| `POST /browser/{profile}/start` | 启动或复用 | 需要 `start`、CSRF、幂等键和有效 launch plan |
| `POST /browser/{profile}/stop` | 安全关闭 | 需要 `stop`、CSRF、幂等键；调用现有生命周期 Stop |
| `POST /manage/proxy-drafts` | 创建代理草稿 | 只写 Secret Store 引用；限制类型、地址、端口和大小 |
| `POST /manage/proxy-drafts/{id}/probe` | 隔离测试代理 | 受 SSRF、解析、认证、TLS、超时和网络策略约束 |

固定 `/browser/{profile}/` 入口继续可用；它只使用该 Profile 的已发布绑定，不允许通过查询参数切换指纹或代理。

## 指纹选择规则

- UI 只显示已通过环境验收、与账号授权匹配的名称和摘要，例如引擎、语言、时区、屏幕和 DPR。
- `environmentArtifactId`、摘要和镜像必须由服务端从目录读取；客户端不能提交任意 Artifact JSON、UA、Canvas seed、字体或窗口字段。
- 运行中的 Profile 不能修改环境产物。服务返回 `409 ENVIRONMENT_BUSY`，要求先安全关闭。
- 同一 Home 默认只绑定同一套环境产物。改变屏幕、语言、时区、引擎或关键指纹字段时，创建新的 Profile/Home。
- 选择成功不等于环境已启动；只有新的 generation 通过 Worker 产物、能力和运行时一致性门槛后才生效。
- 对外只展示摘要和修订标识；完整产物、seeds、resolved config 和成功报告留在受保护的运行目录。

## 手动代理规则

代理配置采用“草稿 → 测试 → 固化 → 下一代生效”：

1. 用户提交 `http`、`https` 或 `socks5` 类型、主机、端口和认证信息；先做格式、长度、地址类别和权限检查。
2. 用户名/密码进入 Secret Store，Adapter 和日志只保留 `SecretRef`。草稿过期或测试失败时撤销临时引用。
3. 探针在隔离网络中测试代理认证、TLS 主机名、DNS、出口和超时；禁止访问宿主机、metadata、私网和未批准管理地址。
4. 通过后创建不可变 ProxyConfig/NetworkPolicy 修订，绑定到 Profile 的下一次 generation。运行中的代次不热切换。
5. `proxy_required` 必须由 Guard/Relay 强制，代理失败时保持阻断；不能退回 VPS 直连。
6. 代理地区与语言、时区、地理位置和一致性策略存在冲突时，拒绝启动或要求选择兼容的环境槽位。

“测试通过”只代表代理链路符合本项目探针门槛，不代表所有目标网站可用；实际出口和一致性报告仍按原规格单独记录。

## 手动关闭与状态

界面把下列操作分开：

| 操作 | 效果 | 权限 |
| --- | --- | --- |
| 关闭运行环境 | 撤销显示、写入停止意图、正常关闭浏览器并清理当前资源；Home 保留 | Profile `stop` |
| 停用环境槽位 | 保留配置和 Home，禁止新的启动/复用 | 管理员或拥有 `manage` |
| 删除环境 | 删除前必须经过独立备份、无运行代次和显式管理员流程 | 管理员；本提案不实现 |

停止失败、响应不明确或资源清单不完整时，状态保持 `STOPPING`/`UNKNOWN`，显示访问阻断，允许重试或对账。按钮不能执行 `docker rm`、删除 Home 或跳过生命周期所有权检查。

## 安全与验收门槛

- 未授权账号不能列出、启动、查看健康状态或关闭其他 Profile；错误返回不能泄漏 Profile 存在性。
- 登录密码限速、短期 Cookie、CSRF、精确 Origin、显示 Cookie 和 Session 绑定继续有效；账号或权限变更撤销现有显示访问。
- 代理秘密不出现在客户端、Worker、镜像、Home、URL、普通日志或公开报告。
- 任意代理不可绕过 Guard/Relay；直连探测、私网/metadata/宿主机访问和协议不支持时必须拒绝。
- 指纹选择只能落到已通过验收的 Artifact 摘要；运行中变更必须拒绝，新的组合必须产生新的修订和 generation。
- 关闭后确认 Worker、显示、Guard、Relay、网络和占用清理；Home 数据、journal、修订和审计保留。
- launch plan 过期、重复使用、跨账号、跨 Profile 或修订漂移必须拒绝；所有修改具备幂等键和审计事件。
- 固定 Profile URL、现有 Trilium 使用方式和生产 Work 会话保持兼容。

## 实施顺序

该设计归入 R6，实施时分为独立可验收的子项：

1. 先做授权 Profile 列表和只读环境摘要，验证权限边界。
2. 复用现有 Stop 增加管理页面关闭按钮，完成显示撤销、失败保留和清理验收。
3. 增加已批准指纹环境的选择和 launch plan，完成 Home/Artifact/能力绑定验收。
4. 增加代理草稿、Secret Store、隔离探针和下一代绑定，完成无直连回退验收。
5. 在独立 QA 完成组合测试、备份/恢复、日志脱敏、客户端实机和回退后，再准备生产候选。

R4B、R2 和 R5D 的生产条件未因这份设计提案而完成；本文件不授权部署或改变现有 Profile。
