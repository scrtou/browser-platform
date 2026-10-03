# R6F 生产 Personal / Work Home 备份阶段验收

日期：2026-09-20（UTC）

本补充记录覆盖 R6F 中 Personal 与 Work 生产 Home 的受控停止、加密备份、校验、隔离恢复及固定入口重建检查；真实 Mac 自定义指纹产物和生产回退由 R6F 主报告的后续补充覆盖。

## 已完成

- Personal 通过受控停止流程完成停止确认：`status=stopped`，records/workers/orphans/resources/relays/guards/networks 均为 0。
- 使用当前控制根、Personal Home 和对应控制状态生成加密归档；归档权限为 `0600`，公开仓库不保存身份、私钥、Cookie 或授权 URL。
- 归档校验返回 `BACKUP_VERIFIED`，包含 928 个条目，格式为 `browser-platform/encrypted-backup/v1`。
- 归档恢复到隔离目标目录返回 `BACKUP_RESTORED`；目标未激活生产，结果要求后续访问复核。
- 用户从 Trilium 打开 Personal 固定入口后，服务器确认使用原 `personal-camoufox-r9` Home 创建新 generation；1 Worker、5 个受管理资源、1 Relay、1 Guard 和 2 个网络均运行，健康报告的 entry/control/session/worker/browser/display/proxy/freshness 全部通过，真实代理探测返回 `PROXY_OK`。
- Work 随后通过受控停止流程正常退出，`status=stopped`，records/workers/orphans/resources/relays/guards/networks 均为 0；源 Home、镜像、应用、最新 journal 和历史备份均保留。
- Work 当前 `firefox-work` 没有 Camoufox 环境字段，见 [DEV-057](../../docs/deviations/DEV-2026-09-20-057-fixed-runtime-backup-evidence.md)。工具新增显式固定运行证据模式，只接受完整镜像 ID、同镜像构建记录及绑定该 Profile/镜像的实际 `PASS` 运行证据；既有冻结环境和旧格式路径不自动降级。
- 使用 R4B 原始 Work 构建记录和生产 `PASS` 运行检查完成当前格式 age 加密归档；归档权限 `0600`、SHA-256 `843c9bff…`，包含 5,174 个条目，只排除 `home/.XDG/wayland-1` 运行时 socket。`verify` 返回 `BACKUP_VERIFIED`。
- 首次 restore 因目标父目录尚不存在而在写入前返回通用失败；创建独立 `0700` 父目录后，同一归档恢复到全新隔离目标并返回 `BACKUP_RESTORED`。恢复 Store 保持 `.recovery-pending` 锁，`ready_to_activate=false`，未执行 activate、未覆盖生产路径、未启动 Worker。
- 用户首次尝试时看到 `Login required`；只读公网核对确认正确 Work 固定入口未登录时 303 到 `/auth/login`，登录页为 200。用户随后经明确登录页和固定入口成功打开 Work，没有修改网关或绕过认证。
- 服务器确认固定入口使用原 `storage/profile-adapter/work` Home 创建新 generation；Worker 镜像仍为固定 `sha256:ec848635…`，1 record/1 Worker、0 orphan/受管理网络资源。强制新鲜健康探测为 `healthy` 且非缓存，entry/control/session/worker/browser/display/freshness 全部 pass，proxy 因 Work 未配置受管理网络而为 not applicable。

私有证据分别位于被 Git 忽略的 `infra/sealskin/runtime/r6f-release-combination-2026-09-19/personal-production-1/` 和 `work-production-1/`；age identity、密文归档及恢复副本不进入公开仓库。

## 未完成与影响

- Personal 归档后的 `resume-profile` 被拒绝；只读复核确认 Adapter 服务和 control socket 当时均 active/listening，旧 CLI 的顶层 `profile adapter stopped` 是误导性的通用错误消息，见 [DEV-056](../../docs/deviations/DEV-2026-09-20-056-control-cli-error-classification.md)。Personal 当时是完整 `stopped` 而非 dormant，最终已通过固定入口按契约创建新代次。
- Work 已由已认证固定入口按契约用原 Home 创建新 generation，服务器入口/绑定/镜像/显示/健康复核通过；浏览器内账号、标签页等用户数据仍须用户目视确认。
- Work 浏览器内数据已由用户确认正常；本记录之后的现有 Profile 完整停用/启用矩阵和实际回退见 R6F 阶段验收及其私有 `rollback-2026-09-20/restore/` 证据目录。
- 本阶段没有修改设计验收条件；其后生产回退、真实 Mac 自定义 artifact 和临时 Profile 清理均已完成，R6F 与 R6 管理面父项于 2026-09-20 收尾。

## 清理与安全边界

两个隔离恢复目标仅用于校验，没有切换生产 Home、Session 或账号状态。Work 已从源 Home 新建健康代次，隔离恢复副本仍未挂载或激活；浏览器内数据确认由用户在目标客户端完成。后续回退演练另行保存旧栈与恢复栈材料，未将旧快照的 `adapter-state.json` 覆盖回生产。

## DEV-056 补充验证

运维 CLI 的误导性顶层消息已在候选源码修复：control reply 增加固定错误码，CLI 命令失败与服务停止使用不同消息，并保留旧 reply 映射。固定 Go 1.27 Alpine 容器中的普通测试、vet、格式检查及全模块 race 通过；新临时 CLI 连接当前旧生产 Adapter reply 后，将 Personal 的安全拒绝分类为 `PROFILE_NOT_DORMANT`，未创建任何容器。候选尚未部署生产。

## DEV-057 补充验证

固定运行证据模式新增显式 CLI 开关，不允许环境字段齐全的应用进入该分支，也不接受标签、漂移镜像、缺失构建摘要或未绑定 Profile/镜像的运行报告。固定 checks 镜像中的四组新/旧备份回归共 118 项通过。实际 Work 归档使用 R4B 原始构建记录与生产运行验收，未新造成功报告；创建、verify 和隔离 restore 均绑定同一 `sha256:ec848635…` 镜像。候选工具未部署为生产服务，只有本次离线备份命令使用当前工作树脚本。
