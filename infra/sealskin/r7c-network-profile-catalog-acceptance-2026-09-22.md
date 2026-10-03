# R7C · 统一代理目录、Secret Store、探针与绑定验收 — 2026-09-22

[验收索引](../../docs/acceptance/README.md) · [当前进度](../../docs/progress.md) · [R7C 工作项](../../docs/work-items/R7C-2026-09-21-network-profile-catalog.md) · [R7 v4](../../docs/browser-workspace-plan.md) · [DEV-062](../../docs/deviations/DEV-2026-09-20-062-network-apply-implicit-stop.md)

日期：2026-09-22，UTC。状态：**Adapter 目录、管理 API、Secret Store/探针复用、浏览器绑定及隔离自动化通过，未部署生产**。本项没有启动或修改生产 Work，没有修改真实 Home、账号、Session、代理凭据、应用或网络策略；生产 Adapter 仍为 R6H `fe4e13c4…`。

## 实现范围

- 新增可选 `network_profile_catalog`，私有文件格式为 `network_profiles.json` version 1。目录以 0600、fsync、同目录临时文件和原子替换保存逻辑代理 ID、不可变修订、`pending / accepted / disabled / failed / revoked` 状态、脱敏探针结果、允许的浏览器授权集合及审计事件；明文用户名和密码不进入文件。
- 新代理修订先持久保留版本，再经既有控制器管理员加密接口导入 `network-<id>/<version>` Secret Store 版本；同一操作者/幂等键重试不增加版本。进程在“目录保留完成、Secret Store 导入前”中断时，同一请求可恢复原版本；失败或过期修订不复用版本。
- 探针继续复用 R6D 已验收的协议、认证、TLS 和公网地址边界。通过后修订变为 `accepted`；失败或过期时先撤销凭据，再写 `failed`。停用只阻止新绑定，已有浏览器绑定保持；撤销要求派生引用计数为 0，并先撤销 Secret Store 版本。
- 浏览器绑定只接受 `accepted` 修订。Adapter 按浏览器的 Profile/Home/App 派生精确 `proxy_required` NetworkPolicy，追加控制器 registry、补丁应用定义，再写 Profile 目录的 `network_profile_id / revision`。目录引用计数从当前 Profile 记录派生，不依赖可漂移的手工计数。
- 资源为空检查与 policy/app/Profile 变更全程持有同一 Profile 生命周期锁；普通绑定、旧 R6D 应用和 DIRECT 切换均不会隐式调用 Stop。运行中返回冲突且 controller append、应用补丁和 Stop 调用均为 0。
- 新增 `GET/POST /manage/network-profiles` 与 `POST /manage/browsers/{id}/network-profile`。能力未配置时为 404；列表和响应不含 secret refs、CA 内容或凭据；绑定要求该浏览器的 `manage` grant、近期重新认证、浏览器/代理修订和幂等键。R7E 才负责可视化“网络代理”Tab。

认证型修订的 Secret Store grants 在修订创建时冻结为当时的 ready 浏览器集合。后续新建浏览器不会静默获得旧凭据授权；管理员需创建新的代理修订，R7D/R7E 下拉只展示该浏览器可用的 accepted 修订。无认证修订不受该授权集合限制。这一边界保持四维 Secret Store 授权不可变，不通过扩大授权或保存明文来换取复用。

## 自动化结果

| 检查 | 结果 |
| --- | --- |
| 固定 `golang:1.27-alpine`、无网络：`go test -count=1 ./...` | PASS，全部 Adapter 包 |
| 同工具链：`go vet ./...` | PASS |
| `gofmt -l` / `git diff --check` | PASS，无格式或 whitespace 错误 |
| 固定 Go 1.27 工具链 + 既有 checks 镜像、无网络、`CGO_ENABLED=1 go test -race -p 1 -count=1 ./...` | PASS，全部 Adapter 包 |

新增测试覆盖：私有目录创建/重开、严格 JSON 与版本、原子持久化、明文凭据不落盘、创建幂等、Secret Store grants/引用、探针接受/失败撤销、引用中的停用/撤销、切回 DIRECT 后撤销、未来浏览器授权拒绝、浏览器 policy 身份派生、绑定幂等、运行中零 Stop/append/patch、副作用锁、配置依赖、HTTP 能力门控、manage grant、固定错误状态与响应脱敏。

race 使用一次性 Docker volume 把固定 Go 工具链只读挂入既有 checks 镜像；验证结束后该 volume 已删除。没有创建 QA 浏览器、容器、网络、Home、Secret Store 或真实凭据，故没有运行资源清理项。

## 未生效与下一步

本候选没有安装 Adapter、修改生产配置或启用 `network_profile_catalog`；现有 R6D 每浏览器草稿路径继续兼容，生产行为不变。R7D 下一步建立浏览器模板、指纹模板和显示模板兼容目录，并把 accepted 且对目标浏览器已授权的代理修订作为配置选择；R7E 再实现网络代理 Tab 与首页。任何生产发布仍归 R7F，需明确维护授权、固定候选、回退和真实 Mac/Trilium 验收。
