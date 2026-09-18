# Secret Store 与加密恢复

[生命周期](README.md) · [Relay](../../../relay/README.md) · [R5B 工作项](../../../docs/work-items/R5B-2026-09-14-secret-store.md) · [安全规格](../../../docs/specs/proxy-environment/specification.md#50-secrets--proxy-credential-security)

R5B 增加 FileSecretStore、Relay 代次租约和 age 加密备份。候选代码和 [独立 QA](../secret-store-acceptance-2026-09-14.md) 已通过，资源和临时密钥已清理，生产尚未使用。控制能力为 `secret_store_version: 1`，Relay 镜像必须声明 `io.browser-platform.secret-lease=1`。R5D 的组合候选已使用包含正常退出和显示认证的 r7；R2A 另补本文的旧部署加密路径，不能据此把旧生产视为已采用 Store。

## 存储与引用

配置保存一对引用：`secret://<id>/username/<version>` 和 `secret://<id>/password/<version>`。ID 只接受字母、数字、下划线和连字符；版本是 1–999999999 的整数。两项必须同 ID、同版本、字段正确，不能使用路径、查询参数或远程 URL。新策略使用 `username_secret_ref` / `password_secret_ref`，并明确设置 `upstream_protocol` / `upstream_auth`。凭据文件字段与引用互斥；参考 [策略示例](network-policy.secrets.example.json)。

每个版本用 AES-256-GCM 加密；随机 nonce、版本、Store 身份和授权元数据共同参与认证。版本不可覆盖。授权精确绑定 `owner`（SealSkin 身份）、`profile`、`home`、`app`，任一不符都拒绝。主密钥是独立目录中的 32 字节随机文件，Store metadata 只保存随机 Store ID 和密钥摘要。路径必须规范，目录/文件归执行 UID 所有，目录 `0700`、文件 `0600`；密钥/凭据文件拒绝符号链接、多重硬链接和超长输入。

Store 固定在 `<SealSkin metadata>/proxy-secret-store/`，含 `store.json`、`versions/`、`revocations/` 和进程间锁。撤销 tombstone 永久禁用对应版本，不依赖主密钥解密；不要删除它来恢复旧凭据。恢复时的 `.recovery-pending` 标记拒绝解析和新增版本，直到离线合并当前撤销状态。

## 配置与导入

控制器读取 `<metadata>/profile-secret-store.json`，格式见 [配置示例](secret-store.example.json)。主机的密钥目录只读挂载到 `/run/browser-platform-key`；一个归控制 UID 所有的主机 tmpfs 目录读写挂载到 `/run/browser-platform-secrets`。运行目录必须是真实 tmpfs，并是控制器实际 bind mount 的精确目标；普通磁盘目录或控制器内部独有的 tmpfs 不满足给 Relay 分发的要求。

准备器生成的 `payload/app/secret_store.py` 也可离线导入，需要 Python 与 `cryptography`。部署前先在受控目录初始化一次；不要把密钥或输入 JSON 放进镜像构建目录：

```bash
python3 /private/build/payload/app/secret_store.py \
  --directory /private/config/.config/sealskin/proxy-secret-store \
  --key-file /private/master-key/master.key init

python3 /private/build/payload/app/secret_store.py \
  --directory /private/config/.config/sealskin/proxy-secret-store \
  --key-file /private/master-key/master.key put \
  --input-file /run/user/1000/proxy-import.json
```

输入文件须为 `0600`，父目录须为 `0700`；在 tmpfs 中准备，导入后删除。字段为 `secret_id`、`secret_version`、`grants`、`username`、`password`；`grants` 是由上述四项精确身份组成的列表。CLI 只返回引用，不接受命令行凭据值。其文件锁允许与控制进程安全地串行新增版本；紧急撤销必须调用下述控制 API。

R6D 候选另提供管理员加密接口 `POST /api/admin/environment-management/proxy-secrets`（[第二层补丁](environment-management.patch)）：请求体为 `secret_id`、`secret_version`、`grants`、`username`、`password`，调用同一 `FileSecretStore.put`，在凭据锁内写入并只返回两个引用；重复版本 409、格式错误 422、非管理员 403。该接口只由 Adapter 的独立管理员身份在草稿创建时调用，凭据不落 Adapter 磁盘或日志；离线 CLI 导入继续可用。生产控制器未应用该补丁，见 [DEV-049](../../../docs/deviations/DEV-2026-09-18-049-proxy-secret-import-channel.md)。

新增版本后生成新的策略 ID/摘要，绑定到应用和 Adapter Profile；旧 generation 的 reservation、引用和 tmpfs 内容保持不变。先验证新凭据，再正常停止旧 generation，然后发布绑定并启动。旧文件策略和其 SHA 继续兼容，但只有新引用路径获得本项存储与撤销保证。

## 生命周期与撤销

授权在启动和恢复时验证；Home 锁先于凭据锁，凭据锁覆盖代次创建/恢复提交。控制器只向对应 `generation-<identity SHA>` 写入 `username`、`password`、`lease`，Relay 只读挂载整个目录到 `/run/secrets`。Worker 不挂载 Store、主密钥或临时凭据。HTTPS 的代理 CA 另外挂载到 `/run/config/upstream-ca.pem`。

Relay 启动及每 100 ms 检查 `active:<generation identity>\n` 租约；文件丢失、损坏、代次错误、权限异常或被替换为 `revoked\n` 都关闭监听及已有隧道。挂载整个目录确保原子替换租约可见。这个检查间隔不是在 CPU 饥饿或主机故障下的硬实时保证；控制器还确认 Relay 已退出，必要时有界停止 Relay。Guard 的阻断规则继续保留。

管理接口采用既有加密请求与管理员 JWT：

```text
POST /api/admin/profile-secrets/revoke
{"secret_ref":"secret://proxy-personal/password/1","operation_id":"<32 hex>"}
```

撤销先持久化禁用，阻止并发启动/恢复，失效所有相关租约并确认出站已阻断，再逐 Home 正常关闭浏览器、清理网络和凭据。`cleanup_complete: true` 才表示全部清理完成。`SECRET_REVOKED_EGRESS_PENDING` 或 `SECRET_REVOKED_CLEANUP_PENDING` 表示需重试；保留 Home、占用和日志。重复撤销不会恢复密钥或重复启动。

普通 stop 同样先保存停止意图、阻断出站，再正常关闭浏览器。关闭被页面对话框阻止时保留 Worker 和占用，Relay 已退出；处理页面后重试。控制器启动及每两秒重新授权运行代次，处理撤销提交后中断、密钥丢失和尚未完成的停止；只阻断出站，未完成的清理通过 API 重试。不要用旧 journal 覆盖当前状态来解除占用。

## 加密备份与恢复

[secure-backup.py](secure-backup.py) 固定使用 **age v1.2.1** 的 X25519 接收者。创建时直接 tar → age，不生成磁盘明文归档；验证/恢复先在私有 tmpfs 中完成整个 age 流的认证和所有成员/摘要检查，才创建新的恢复目录。暂存容量必须覆盖未压缩归档；当前归档上限 8 GiB，超限拒绝。必须保存独立的 age 恢复 identity。

`create` 支持当前 `/config/.config/sealskin` 部署布局，先后通过 Adapter 控制 socket 核对目标 Profile 已停止、清单为空，并比较来源前后快照。维护期间应保持该 Profile 停止且不修改控制配置。包中包括 Home、Adapter 配置/journal/客户端私钥/服务公钥、固定环境产物和验收报告、Store/主密钥、控制授权与操作元数据、实际 `/config/ssl` 和管理员恢复材料；必要服务密钥缺失时拒绝。服务镜像和客户端代码仍由固定版本构建/发布材料提供，包不包含 Docker 镜像层。

R5E 补充 `control/coherence-assets/`，并在创建和解密验证时逐项核对策略引用的环境、成功报告及可选 GeoIP 文件：路径须为控制器固定资产目录内的直接文件，摘要、私有权限与大小限制须匹配。缺失或漂移拒绝，不能通过关闭策略补救。对应 [DEV-038](../../../docs/deviations/DEV-2026-09-15-038-coherence-backup-assets.md) 的 101 项新旧备份回归已通过；[R5E](../release-combination-acceptance-2026-09-15.md) 已通过单 QA Home 的新私有根实际浏览器恢复，备份后撤销及禁用账号保持；生产 S05 仍待 R2。

```bash
python3 secure-backup.py create --age /private/tools/age \
  --config /private/adapter-config.json --profile personal \
  --storage /private/storage --sealskin-config /private/config/.config/sealskin \
  --artifact /private/environment.json --acceptance /private/acceptance.json \
  --master-key-file /private/master-key/master.key \
  --recipient "$BP_AGE_RECIPIENT" --output /private/backups/personal.age

python3 secure-backup.py verify --age /private/tools/age \
  --archive /private/backups/personal.age --identity /private/recovery/identity.txt \
  --scratch-root /run/user/1000/backup-scratch

python3 secure-backup.py restore --age /private/tools/age \
  --archive /private/backups/personal.age --identity /private/recovery/identity.txt \
  --scratch-root /run/user/1000/backup-scratch --target /private/restore/new-bundle
```

所有私有目录须归操作 UID 所有且为 `0700`。Adapter 私钥须为该 UID 的 `0600` 普通单链接文件；服务公钥可为 `0644`，但同样检查 UID、普通单链接及不可被组/其他用户写入。Adapter journal 必须已由真实生命周期操作落盘，缺失时返回 `BACKUP_ADAPTER_STATE_MISSING`，工具不伪造空状态。管理员 bootstrap 配置已移到离线存储时，用 `create --admin-recovery-file /private/recovery/admin.json` 指定私有恢复文件。目标必须不存在；任何认证、内容、路径或文件类型校验失败都不写入恢复数据。只支持 Home 内相对链接及 Worker `/config/` 内链接，链接最后创建、不跟随写入；Home 硬链接保存为独立文件内容。

恢复目录的 Store 默认被锁定。停止并退役原控制器，确认原 Store 与恢复包都没有容器挂载，保持原 Store 不再写入，才执行：

```bash
python3 secure-backup.py activate --bundle /private/restore/new-bundle \
  --current-store /private/config/.config/sealskin/proxy-secret-store
```

该步骤检查相同 Store/主密钥身份，持有两边文件锁合并最新撤销；既有 tombstone 保留。启用记录先原子持久化，再删除恢复锁并 fsync；中断可重试。`ready_for_offline_rebinding` 只表示可继续离线重绑，工具不会启动 Worker。原撤销状态缺失时，不能把旧包自行视为最新状态。

R5D 新 Session 状态另有 `session-secrets/state.key`，加密备份会验证密文与密钥配对并一同收集。启用入口登录时还保存账号表和 Session CA；恢复的 `activate` 必须额外传入 `--current-access-users /private/current/entry-users.json`，用包外当前受信任的账号/密码/授权替换旧快照，再继续离线重绑。对应路径为 `control/session-secrets/`、`adapter/access-users.json` 和 `adapter/session-ca.pem`，须同步修改新 Adapter 配置引用。Worker 临时显示目录不进入归档，恢复时由密封 Session 重建。旧明文 control-state 在存在 Session 库或登录配置时拒绝生成归档。37 项真实 age 备份控制测试及控制器/Worker 恢复已通过 [R5D 验收](../entry-authentication-acceptance-2026-09-15.md)；这不替代真实 Home 的新环境恢复。详细行为及代码回退限制见 [入口登录说明](../entry-auth/README.md)。

离线重绑时把 Home 放到新的隔离 storage，把 `control/ssl` 和 `control/admin.json` 还原到控制根目录，其余控制 metadata 放到 `.config/sealskin`；恢复 Adapter 身份文件及状态。重新映射 artifact/acceptance、主密钥和 tmpfs 的实际主机路径，保持内容/镜像摘要、引用和四维授权。先验证服务身份、凭据和浏览器存储，再将入口交给用户。不同 Store 身份或改换用户/Profile/Home/App 需要另行受控授权，不能改密文 grants 绕过认证。

旧 [backup-home.py](backup-home.py) 的历史 QA 归档为明文中间产物，实际备份使用上述加密路径。SSL 路径修复与旧证据限制见 [DEV-009](../../../docs/deviations/DEV-2026-09-14-009-backup-key-paths.md)。真实 Home 和整机维护演练仍归 R2。

## 旧部署的加密备份

无 Store、无入口登录且 Session 尚未密封的旧部署使用显式 `snapshot-legacy` → 停止确认 → `create-legacy`。旧格式为 `browser-platform/encrypted-legacy-backup/v1`，与原 Store 格式 `browser-platform/encrypted-backup/v1` 分开；原 `create` 不自动降级。存在 Store 配置/目录、Session 密钥、显示材料版本、`access` 或策略 `secret://` 引用时拒绝旧模式，即使对应目录为空也不例外。

先在 Profile 仍运行时生成 `0600` 快照，输出父目录须已存在且为 `0700`。该步骤只读配置、Adapter journal/控制 socket 和 Docker 清单，不读取或散列 Home 内容，不停止服务：

```bash
python3 infra/sealskin/lifecycle/secure-backup.py snapshot-legacy \
  --config infra/sealskin/adapter-config.json --profile personal \
  --storage infra/sealskin/storage \
  --sealskin-config infra/sealskin/config/.config/sealskin \
  --output /private/backups/personal-runtime.json
```

快照要求 Adapter 验证唯一 running Session/Worker、无孤儿，与 journal 同 Session，并核对唯一精确 Home `/config` 挂载及控制器。记录实际 Worker/控制器 image ID、启动时间、自动删除状态和少量环境引用；应用定义中的**下次启动镜像**单独保存。旧 journal 未包含 Home/App 时保留缺失形态，非空身份冲突仍拒绝；不补写生产 journal。输入摘要或容器身份在采样期间变化则失败。

在已安排的维护窗口，暂停入口新启动，经原 Adapter/原配置停止该 Profile 并确认 `stopped`、records/workers/resources 均为 0，再执行：

```bash
python3 infra/sealskin/lifecycle/secure-backup.py create-legacy \
  --config infra/sealskin/adapter-config.json --profile personal \
  --storage infra/sealskin/storage \
  --sealskin-config infra/sealskin/config/.config/sealskin \
  --legacy-snapshot /private/backups/personal-runtime.json \
  --age /private/tools/age --recipient "$BP_AGE_RECIPIENT" \
  --output /private/backups/personal-legacy.age
```

快照必须来自同一 operation，停止后 Session 已清空，原有可选身份字段和配置/应用/策略摘要保持；停止再新建过的代次不能复用旧快照。实际旧 Worker image ID 必须仍在本机可查。归档包含目标 Home、快照、Adapter 身份/journal、控制状态/SSL/admin 和旧凭据，发布密文前再次检查停止、来源和禁止降级条件。管理员离线材料仍可用 `--admin-recovery-file` 指定。`environment_evidence=observed-legacy-runtime` 表示只记录旧环境事实，不附造出的冻结产物或成功报告；这不是 E 组验收通过。

`verify`、`restore` 使用上一节的相同参数并识别格式。旧格式恢复只写新私有目录，返回 `offline_only=true`、`ready_to_activate=false`，写入 `.legacy-recovery-pending.json`；`activate` 拒绝旧格式。这个标记是离线维护提示，**旧控制器不会执行它作为启动门槛**。不得把恢复目录直接挂载到运行服务；先核对镜像、补丁/客户端发布材料、scope、身份、路径、网络策略和最新操作，再单独安排隔离浏览器恢复。一个归档仅含一个 Home，而控制 metadata 可能引用其他 Profile；整机恢复需要各 Home 的一致性备份，不能自动启动这些额外绑定。

包不含镜像层、热安装的控制 payload 或客户端代码；维护前另行保留匹配版本。当前旧 Worker 的正常退出能力也不能由新工具推定，仍需在窗口内确认数据已保存。2026-09-15 的 [R2A 验收](../legacy-backup-acceptance-2026-09-15.md) 覆盖真实 age、命令行/Unix socket 夹具和生产只读快照；生产 Home 备份、真实浏览器读取恢复数据及整机重启仍归 R2。

## 验证与回退

R2B 已发现停止后的旧 Wayland Home 可能保留 `.XDG/wayland-<数字>` socket，当前修复与验收见 [DEV-039](../../../docs/deviations/DEV-2026-09-15-039-legacy-wayland-backup-socket.md)。运行时 socket 不属于浏览器持久数据；备份将只排除这个精确位置和类型，记录并复核排除清单，未知特殊类型仍拒绝。不能靠删除真实 Home 节点绕过失败。

`test_secure_backup.py` 和 `test_secure_backup_legacy.py` 使用真实 age，后者覆盖旧 journal、运行快照、命令行往返和模式降级拒绝；Docker/API 清单除注明的生产只读快照外均使用夹具。`test_qa_secret_mount.py` 验证 QA 网关只允许该 Relay 对应的只读代次目录。`../checks/check-secret-store.py` 运行三协议、授权、轮换、撤销、并发及控制恢复；`../checks/check-secret-backup.py` 在全新 QA 根目录恢复服务身份、环境、凭据和 Cookie/localStorage/IndexedDB。工具与详细证据使用隔离 `runtime` 目录，公开结果只保留状态、版本和摘要。

回退控制版本前，使用支持 Secret Store 的版本正常停止全部引用型 generation，确认 Relay、网络、占用和临时材料都已清理，再切换匹配的应用/策略。旧控制器不提供新租约和后台授权检查，不能接管仍在运行的 Secret Store generation。保留加密 Store、最新撤销和 journal；主机重启/断电、目标 Mac 与实际入口切换不因本项 QA 自动视为通过。
