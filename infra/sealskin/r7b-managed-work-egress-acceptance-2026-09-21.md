# R7B · Work 受管理 DIRECT 与无直连验收 — 2026-09-21

[验收索引](../../docs/acceptance/README.md) · [当前进度](../../docs/progress.md) · [R7B 工作项](../../docs/work-items/R7B-2026-09-21-managed-work-egress.md) · [R7 v4](../../docs/browser-workspace-plan.md) · [DEV-061/063–066](../../docs/deviations/README.md)

日期：2026-09-21，UTC。状态：**候选镜像、隔离真实浏览器验收和清理通过，未部署生产**。生产 Work 保持停用、停止和 0 资源；Personal 的 Session、Worker、Relay、Guard 与网络代次未改变。

## 候选与边界

| 对象 | 固定版本 / 结论 |
| --- | --- |
| Work 父镜像 | `sha256:ec848635…`，既有 Firefox legacy / Wayland、正常退出和显示认证候选 |
| 受管理网络候选 | `sha256:895907b7…`；完整保留父层，只增加 Firefox `profile-relay:1080` SOCKS5、远端 DNS、禁用 DoH/WebRTC 直连候选；输入摘要 `d9c842fa…` |
| DIRECT 网关 | 固定 `sha256:a785d443…`，标签 `direct-egress=1`；独立 QA policy、Home、Profile 和应用 |
| 控制器 | R5E 固定构建的机械副本，挂载只读宿主 IPv4 地址证据；不复用生产 Session、目录或策略 |
| 生产范围 | 0 mutation；没有为 Work 启用、启动或绑定候选，最终发布与回退归 R7F |

主机只读前置确认存在一个可用原生公网 IPv4，满足受管理 DIRECT 的地址证据要求；地址本身不进入公开报告。生产控制器当前尚未挂载该只读证据，现行 Relay 镜像也不是 DIRECT 候选，因此本项结果不能误写为生产已可用。

## 实际结果

第六轮在与生产 Work 相同的 Firefox/Wayland/退出/显示认证父层上通过 4 组检查：

1. 唯一 Firefox 主进程持有原生 Wayland 资源；浏览器显式访问固定公开 HTTPS 页面，页面主机、标题和完成状态正确。健康报告为 `mode=direct`、enforcement v1、Worker 共享 Guard namespace、经 Relay 的上游探针通过。
2. Worker 对公开 TLS、Docker DNS、公开 DNS 和 link-local metadata 四类原始绕过目标全部不可达。浏览器公网访问只能经固定的 generation Relay/Guard。
3. 主动停止 DIRECT Relay 后，健康报告转为网关失败；相同四类绕过仍全部不可达，没有回退直连。
4. 浏览器写入 Cookie、localStorage 和 IndexedDB；正常 Stop 清空首代次后创建新 generation，三类数据全部读回，Firefox 启动身份已变化；最终 Stop 后 record、Worker 和 network resource 全部为 0。

前五轮失败均保留独立目录，且每轮通过 reservation 精确正常 Stop 后确认资源归零：进程参数/`/proc` 权限识别、Launch Context 与实际导航差异、现行 Work 缺少 Firefox Relay 配置，以及新代次 Firefox 进程早于 BiDi 端口就绪。它们分别形成 [DEV-063](../../docs/deviations/DEV-2026-09-21-063-work-qa-firefox-argument.md)、[DEV-064](../../docs/deviations/DEV-2026-09-21-064-work-qa-launch-context.md) 和 [DEV-065](../../docs/deviations/DEV-2026-09-21-065-work-firefox-proxy-policy.md)；没有降低原验收断言。

## 自动化与构建核对

| 检查 | 结果 |
| --- | --- |
| Python `py_compile` | PASS：构建器、准备器、DIRECT runner、QA 清理器 |
| 候选离线构建 | PASS：精确父 image ID、父能力标签、完整父层前缀和不可覆盖输入标签 |
| 镜像内配置摘要 | PASS：autoconfig `4ed547ad…`、Firefox policy `86913a01…` 与构建输入一致 |
| 第六轮 `check-work-direct.py` | PASS，4/4；`engine=firefox`、`display=wayland`、`network=managed-direct`、production mutations 0 |
| `git diff --check` | PASS |

私有证据位于忽略目录 `infra/sealskin/runtime/r7b-work-egress-2026-09-21/`：固定 build、候选镜像记录、attempt 1–6、最终结果及清理摘要。公开记录不包含凭据、Cookie 值、Session URL、私钥、内部地址或授权参数。

## 清理与生产保持

聚焦 QA 的完成摘要通过显式清理证据门槛；观察器先核对 QA 标签与唯一挂载，再按精确容器 ID 删除。最终清理结果：generation resources 0、QA containers 0、QA networks 0、控制器与专属 Docker proxy 已停止、临时凭据/证书/显示目录已删除。清理器泛化记录为 [DEV-066](../../docs/deviations/DEV-2026-09-21-066-focused-network-qa-cleanup-evidence.md)。

清理后生产只读复核：Work `stopped`、0 record/Worker/orphan/resource/Relay/Guard/network；Personal 仍为原 Session，1 record/1 Worker、5 resources、1 Relay、1 Guard、2 networks，三个生产容器 ID 与镜像均未变化。真实 Home、账号、Profile 目录和 Caddy 未修改。

## 未生效与下一步

R7B 只交付经过验证的 Work 受管理 DIRECT 候选。R7C 继续实现统一代理目录、Secret Store 引用、探针/修订/撤销与无隐式 Stop 的绑定语义；R7F 才把固定控制器、DIRECT 网关挂载、候选 Work 镜像和策略打入发布包，完成回退和 Mac/Trilium 真实 Work 公网验收。
