# R6F 组合 QA、真实客户端、生产候选与回退阶段验收

日期：2026-09-19（UTC）

本报告记录 R6F 已完成的隔离检查、管理面安全子集生产部署、现有环境 overlay 组合验证和当前未测项。R6F 尚未收尾；生产 Adapter、账号表和控制器镜像已更新，Personal/Work 的 Home、Session 和运行代次保持。详细日志、候选二进制摘要、部署前备份和运行态位于被 Git 忽略的 `runtime/r6f-release-combination-2026-09-19/`。

## 已完成的隔离检查

- 当前源码基线为 `97105e5d912fb4c3b90fee4c2338df225b8e6d09`。Adapter 在固定 Go 1.27.1 环境中通过 `go test ./...`、`go vet ./...` 和格式化检查；固定 Go 容器内 `CGO_ENABLED=1`、串行 `go test -race -p 1 -count=1 ./...` 通过，日志末尾为 `exit=0`。
- 固定 Camoufox r9 镜像内执行 `acceptance.py --phase unit`，artifact 单元验收通过。直接在宿主 Debian 12 执行同一组 artifact 测试会因 Python 3.11/运行架构与固定产物不匹配返回 `ENVIRONMENT_VERSION_MISMATCH`，因此不把宿主结果写成通过。
- R6E 主机执行器/准备器的 21 项 Python 回归继续通过；真实 R6E 作业的 10 次重建、目录追加和夹具清理沿用 R6E 报告，不扩大为 R6F 组合通过。
- 使用固定 age v1.2.1 工具和 checks 镜像重跑备份测试：修复前 115 项通过；新增 version 2 账号表回归后 116 项通过、0 项失败。此前一次执行中的 `test_legacy_cli_uses_real_socket_age_and_offline_restore` 泛化失败在同一源码、同一镜像、同一固定 age 工具和 `/repo` 挂载条件下复跑通过；初次未提供 age 工具的运行记录为 skipped，不计入验收。最终结果保存在 `combination-backup-1/backup-tests-full-age.log`。组合复核首次使用当前 version 2 账号表时发现旧校验器拒绝 `role` 字段，见 [DEV-055](../../docs/deviations/DEV-2026-09-19-055-encrypted-backup-account-version.md)；修复后在不停止生产 Profile 的前提下，以停止且不再绑定生产的旧 QA Home 收集当前控制根、Session/Secret Store、账号表和 r9 环境资产，完成 4543 个成员的 age 加密归档、verify 与离线 restore，恢复目录和 tmpfs 均通过检查。
- 使用与 R6D 候选一致的控制器 checks 镜像、R6D 补丁树只读挂载和无网络运行参数重跑全量控制器回归：545 项通过，0 项失败，2 个既有依赖弃用警告；结果保存在 `controller-tests-rerun.log`。该结果确认补丁输入和测试树可复现，但不扩大为真实控制器/Worker 组合通过。
- 通过 [`prepare-r6f-candidate.py`](checks/prepare-r6f-candidate.py) 重新生成 R6F 隔离审查候选 `candidate-14`：使用固定 `golang:1.27-alpine` 容器构建 `profile-adapter`/`profile-accounts`，源码输入绑定当前 HEAD `129b844`；manifest 为 `browser-platform/r6f-candidate/v2`、`ISOLATED_REVIEW_ONLY`，`production_changed=false`、`deployment_authorized=false`。候选二进制摘要为 Adapter `7f699ce3…`、账号 CLI `8d6eee72…`，与当前生产 Adapter 文件及已核对的账号 CLI 摘要一致；候选未安装服务。
- 构建了隔离审查候选 `candidate-1`：`profile-adapter`、`profile-accounts`，并以源码、控制器第二层补丁、固定 r9/SealSkin/checks 镜像摘要生成 manifest。候选标记为 `ISOLATED_REVIEW_ONLY`，未安装为服务。
- 直接读取生产状态：Docker、Caddy、用户 Adapter 均 active，`Linger=yes`；Personal 为 1 record/1 Worker/5 resources/1 Relay/1 Guard/2 networks、network phase running；Work 为 1 record/1 Worker、无 Relay/Guard/network；入口边界为登录 200、两个 Profile 未登录 303、Session 根 404。此检查只读，生产未变。
- 只读复核历史 R4B `release-ready-2` 时按预期拒绝 `live input drift`：其准备摘要早于当前 r9 配置/状态写入。该差异已登记 [DEV-052](../../docs/deviations/DEV-2026-09-19-052-stale-release-package.md)；历史包继续作为回退材料，不能直接冒充 R6F 新候选。
- 之前的 `candidate-10`（Adapter `136ddac0…`）记录首轮安全子集切换；后续生产 Adapter 已更新为 `7f699ce3…`，账号 CLI 为 `8d6eee72…`，并由 systemd 用户服务在 10:34 UTC 重启后保持 active/enabled。`candidate-14` 只读复核确认当前源码与运行二进制一致，未再次重启控制器或浏览器容器。
- 本机复核通过 `go test ./...`、`go vet ./...`、`gofmt -l adapter` 和新增候选准备器/组合脚本的 Python 编译检查。主机未安装 gcc，直接运行 `CGO_ENABLED=1 go test -race` 只能得到环境缺失错误；全模块 race 结论继续采用固定 checks 镜像中既有的 `go test -race -p 1 -count=1 ./...` 通过记录，不把本机限制写成代码失败。
- 生产只读复核确认用户 Adapter 服务 `active`/`enabled`；通过公网 Host 路由访问 `https://mybrowser.azhen.de/healthz` 和 `/readyz` 均为 200（`{"status":"ok"}` / `{"status":"ready"}`）。Docker、SealSkin、Personal/Work Home、Relay/Guard 容器仍在运行；未执行生产写操作、停止、重建或回退。
- 固定 r9 artifact 在 r9 镜像内按正确运行环境变量重跑 `acceptance.py --phase unit`：17 项通过，0 项失败；结果保存在被忽略的 `runtime/r6f-release-combination-2026-09-19/camoufox-unit-rerun-3/`。此前一次手工调用因未注入 artifact 运行环境变量而得到 `ENVIRONMENT_CONFIG_DRIFT`，不计入验收。
- 组合控制根备份使用临时 Unix control socket 返回已停止且清单为空的 QA Profile；生产 Adapter、SealSkin、Personal/Work 容器、Home、账号表和 Secret Store 未写入。私有证据为 `runtime/r6f-release-combination-2026-09-19/combination-backup-1/`，公开记录不包含 identity、凭据、Cookie 或授权 URL。
- R6E 执行器/迁移相关主机 Python 回归重新运行：21 项通过，0 项失败；`environment-job.py` 编译检查通过。该结果仍只证明执行器与迁移工具隔离行为，不证明 R6F 控制器/Worker 组合。

## 现有环境组合验证

- 在当前管理员身份和现有 Compose 项目上安装 `r6f-existing-overlay-recheck` 控制器镜像；`production-overlay-1/install.log` 记录 Compose 只重建 `sealskin`，Personal/Work Worker、Guard、Relay 和 Home 未重建。当前 `sealskin` 镜像为该 overlay，health/ready 仍分别返回 200。
- 使用固定 r9 artifact 创建临时固化指纹 Profile，完成固定入口启动、1 record/1 Worker/5 resources/1 Relay/1 Guard/2 networks 的运行检查和健康报告；随后按 Stop/资源归零/Home 归档/应用撤销路径清理，Profile 目录保留 `deleted` 审计记录。
- 使用 R6E 生成的自定义 artifact `env-custom-804399c31829bb18` 创建临时自定义指纹 Profile；运行报告绑定该 artifact 摘要，entry/control/session/worker/browser/display/proxy/freshness 全部为 pass，代理探测约 971 ms。完成后清理并保留 `environment_source=custom` 的 `deleted` 审计记录。
- 固化 Profile 的真实上游代理探测约 945 ms；上述代理凭据只保存在受保护的 Secret Store/运行目录，公开记录不包含凭据或授权 URL。临时 Profile 的网络策略、应用和 Home 已清理，当前生产只保留 Personal/Work 两个运行 Profile。
- 组合验证中创建的 QA 管理员 `r6f-qa-admin` 已禁用；`owner` 保持启用管理员，`test` 保持启用普通账号且仅授权 Personal。两个生产 Profile 的 operation、Session、状态和资源计数复核未变。

## 生产管理面安全子集

- [DEV-053](../../docs/deviations/DEV-2026-09-19-053-management-production-gating.md) 增加 `profile-accounts role` 无损角色修改和管理能力门控。页面与写入口只有在完整后端配置存在时才放行新增/归档删除、代理和自定义指纹；能力关闭回归覆盖页面不展示以及 create/delete/proxy/job/catalog 入口返回 404。
- 首轮 `candidate-10` 使用固定 Go 1.27 Alpine 构建并完成安全子集切换；当前 `candidate-13` 绑定同一组固定镜像和提交后的源码输入，Adapter SHA-256 为 `7f699ce3…`，账号 CLI 为 `8d6eee72…`，与当前 systemd 运行文件一致。最终源码全模块普通测试、vet、gofmt 通过；全模块 race 通过，目录入口门控也经 HTTP 包 race 复核。
- 部署前在私有目录保存旧 Adapter、配置、状态和 version 1 账号表并记录摘要。配置只新增 `profile_directory`；Adapter 原子替换后第 2 次 ready 轮询即恢复，health/ready 均为 200，`profiles.json` 以 0600、version/revision 1 导入 Personal/Work。
- 现有 `owner` 通过角色命令提升为 `admin`，账号表升至 version 2；密码校验值、Personal/Work 授权及启用状态与备份一致。旧登录可能因账号记录变化撤销，用户应使用原密码重新登录。
- 两次 Adapter 切换均未停止 SealSkin、Worker、Guard 或 Relay。最终复核中六个生产容器的 ID、启动时间和镜像与部署前一致；两个 Profile 的 operation、Session、状态和资源计数保持。未创建、删除、停止或迁移 Home。
- 当前生产保留管理员列表、账号管理、名称/起始页修改、停用/启用和安全关闭；overlay 组合验证期间新增/归档删除、代理草稿和自定义指纹作业按维护步骤临时启用并在清理后不保留测试 Profile。组合回退必须同时恢复旧 Adapter、旧配置和 version 1 账号表；不能只换二进制，也不能用旧状态覆盖部署后真实生命周期操作。
- 用户在目标 Mac/Trilium 提供生产管理面截图：原 `owner` 成功显示为启用的 `admin`，Personal/Work 列表、固定入口、修订、账号分配、修改/停启/安全关闭表单与账号区正常渲染；页面显示“新增与归档删除尚未启用”，未出现代理或自定义指纹入口。该证据确认登录、页面和能力门控，不确认任何写表单。截图只保存在用户目录，SHA-256 为 `f15da923…`，不提交公开仓库。
- 截图中的 Personal 健康为非阻断 `unknown / PROXY_UPSTREAM_UNKNOWN`；服务器同一时段缓存与一次强制探测均确认入口、控制面、Session、Worker、浏览器、显示和报告新鲜度通过，只有上游探测端点超时，`blocking=false`。Work 为 healthy。该结果不宣称 Personal 代理通过，也不要求停止或重建运行代次。
- 用户随后提交 Personal 名称修改；服务器端确认显示名称为“个人浏览器测试”、Profile 目录 revision 为 2、记录 revision 为 2、起始页保持 `https://example.com/`、状态为 ready 且未禁用，Work 保持 revision 1。该可逆写表单在 Mac/Trilium 上通过；未执行停用、启用、安全关闭或账号密码操作。
- 用户继续在 Mac/Trilium 中将 Personal 起始页临时改为 `https://example.org/` 并恢复为 `https://example.com/`；服务器端确认目录 revision 为 4、Personal 最终记录 revision 为 4、起始页原值、状态 ready 且未禁用，Work 仍为 revision 1。两次保存未改变 Session、容器或网络绑定，health/ready 仍为 200。该可逆写表单通过；未执行停用、启用、安全关闭或账号密码操作。
- 用户随后创建入口账号 `test`。服务器端核对确认账号表为 version 2：`owner` 为启用管理员并保留 Personal/Work，`test` 为启用普通用户且仅分配 Personal，QA 管理员 `r6f-qa-admin` 后续已禁用；密码内容未读取或写入公开记录。两个 Profile 仍 running，health/ready 为 200。创建账号通过。用户继续以 `test` 完成三项边界实测：可进入 Personal 固定入口，访问 `/manage/` 被拒绝，且管理面不可见 Work；服务器核对账号授权与启用状态未变。

## 尚未完成

### 按现有环境推进的复核（2026-09-19）

- 按用户决定未建立专用 QA 环境或新入口，直接复用现有项目控制器、配置挂载和运行容器进行前置核对。
- 以当前生产基镜像 `browser-platform/sealskin:0.3.2-entry-auth-v1-2ba57382ce75c8f9-pkg-1661ffdddfdf` 叠加 R6C/R6D 工作树中的 `api.py`、`routers/homedirs.py`、`environment_management.py`、`proxy_probe.py`，构建现有环境候选 overlay；镜像 ID 和补丁文件摘要保存在私有 runtime 目录。
- overlay 在无网络、只读 checks 容器中通过 11 项 `test_environment_management.py` / `test_home_archive.py`，随后在维护步骤中安装并重建 `sealskin`；Worker、Guard、Relay 和 Home 未重建。无网络测试只证明补丁在当前基线上的单元兼容性，生产组合结论来自下方受控手工步骤。
- 接入运行控制器的历史核对曾发现管理员身份阻断：运行控制器的 `keys/admins/admin` 公钥与当时使用的仓库 `infra/sealskin/config/admin.json` 私钥不匹配；扫描当时的运行目录未找到匹配私钥，因此未重启控制器、未安装 overlay、未调用管理写 API。2026-09-19 后续只读复核确认当前本机挂载公钥与仓库私钥推导公钥一致，并以该身份完成管理员握手及 `GET /api/admin/apps/installed`（5 个现有应用）读取；历史不匹配不改写为当时通过。
- 后续重建的生产基线 overlay 与 checks 镜像均成功构建；在无网络、只读容器中重跑 `test_environment_management.py` / `test_home_archive.py` 共 11 项，11 passed。该结果仍不等于已安装生产控制器。

R6F 仍未完成真实 Personal/Work Home 的停机备份、真实 Mac/Trilium 上自定义 artifact 的视觉与交互验收、生产 Profile 的停用/启用/安全关闭写操作、账号密码操作和破坏性实际回退。现有 `run-release-combination.py` 仍绑定旧 R5E 资源，当前组合证据来自现有环境的受控手工步骤，不能把旧运行器结果扩大为 R6F 自动化组合通过。R6E 执行器仍未安装为常驻生产服务；自定义作业本轮以受控一次性执行完成并在清理后保留目录审计。用户已完成安全子集页面及普通账号边界实测，但不能扩大为真实 Mac 自定义产物通过。

R6F 保持“进行中”。overlay 安装、现有环境的固化/自定义指纹组合验证及组合控制根隔离恢复已完成并清理；下一步是真实生产 Home 停机备份、真实客户端自定义 artifact 验收、Profile 生命周期写操作和可逆回退演练。停用或安全关闭会影响现有浏览器，须单独选择 Profile 后再操作。在这些条件完成前，不得把 R6 父项标记为收尾。
