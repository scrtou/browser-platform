# Camoufox 受管桌面恢复候选验收 — 2026-09-29

## 范围与结论

R7F 生产新建的模板化 Camoufox 在使用中崩溃后，旧健康提示将用户引导到基础桌面的系统 Firefox。本候选完成两层修正：

- Adapter 对已登记浏览器模板的 `BROWSER_EXITED` 改为“安全关闭原代次 → 固定入口重建”，不再提示右键启动 Firefox；历史无模板原生 Firefox 保留兼容路径。
- Camoufox Worker 候选从 Openbox 默认菜单移除 FireFox 项，移除 `/usr/bin/firefox` 和 `firefox.desktop` 启动入口，并默认启用 `HARDEN_OPENBOX=true`。Camoufox 二进制、指纹配置、seeds 和 preferences 不变。

代码、静态镜像检查、完整重放及独立正常 Selkies/Openbox GUI 验收通过。这里的结论保留候选阶段边界；候选随后已在本报告末尾的生产追跑中部署并恢复服务器端代次，但目标 Mac/Trilium 和生产远程桌面右键的直接用户证据仍待真实客户端验收，因此 [DEV-073](../../docs/deviations/DEV-2026-09-29-073-managed-browser-desktop-recovery.md) 保持处理中。

## 固定输入

| 项目 | 值 |
| --- | --- |
| 父 Worker | `sha256:10f6420a1e409ce98cdc18a8830f023b46a30e4697d258126d6bf591c8fcc371` |
| 候选 Worker | `sha256:9a128663eb05d1b7a64a9519b597b745ba2b9be76af7b6649755a2a50d168306` |
| 桌面输入摘要 | `4d5b382eb26f3c1289b543adbc69a4b61765e89fdf0af44974608bdedf48f2a6` |
| 新产物 | `artifacts/env-tw-camoufox-r10.json` |
| 产物 SHA-256 | `f785549f883c73556adc89881046b3c79fdfd4459e20df7dd6332d17523810b9` |
| 成功报告 | `evidence/acceptance-r10-2-2026-09-29.json` |
| 首轮失败报告 | `evidence/acceptance-r10-1-2026-09-29.json` |
| GUI 报告 | `evidence/sealskin-gui-r10-2026-09-29.json`，SHA-256 `6e03ec351b9f3028575146ccbf39d06368e69c4e277888807326f9a363730970` |

候选镜像保留父镜像的 `browser-shutdown=1` 标签，`worker-base` 精确指向上表父 Worker；重绑工具核对层前缀、标签和完整环境产物后才生成 r10。

## 验证结果

| 场景 | 结果 |
| --- | --- |
| `configure-desktop.py` 正常、幂等与非预期启动器拒绝 | 2 项 `unittest` 通过 |
| Adapter 模板化/历史浏览器恢复分流、只读健康语义与入口错误 | `internal/profile` 和 `internal/httpapi` 通过 |
| Worker 静态桌面限制 | `HARDEN_OPENBOX=true`；Openbox 默认菜单无 `/usr/bin/firefox`；`/usr/bin/firefox` 与 `firefox.desktop` 不存在；Camoufox 窗口规则保留 |
| 产物单元检查 | 通过 |
| 错误产物/环境启动前拒绝 | 11/11 通过 |
| 两个独立 QA Home，每个 10 次重建及初始观测 | 22/22 存储与配置通过，稳定字段无差异 |
| Home A 离线复制后第 23 次观测 | 存储恢复、稳定字段和固定配置通过 |
| 直连阻断与测试网页 | 经现有受管 Relay 网络通过；没有将 QA Home 与生产 Home 混用 |
| 正常 X11/Selkies 入口 | 独立 QA Home 和 QA 显示材料启动；1920×1080、1.5 CPU、1536 MiB，冻结页面字段与重放参考差异为 0 |
| 桌面右键与系统 Firefox | 隐藏 Camoufox 窗口后在桌面实际发送右键，X11 窗口树不变；`/usr/bin/firefox`、`firefox.desktop` 和 Firefox 进程均不存在 |
| 正常停止 | `docker stop -t 30` 经镜像退出层完成；QA Home 锁可重新取得且未生成 core |

第一轮使用不含 Relay 的纯内网，在 Home A 首次测试网页访问处以 `NS_ERROR_UNKNOWN_HOST` 失败；这是 QA 拓扑缺少必需 `profile-relay` 服务，不是候选稳定性通过证据。失败报告保留，第二轮使用验收工具原有的受管 Relay 网络完整通过。

GUI 首次直启没有挂载 r7 要求的专属显示材料，按设计在 `/init` 以 `SESSION_AUTH_INPUT_INVALID` 拒绝；补齐独立 QA tmpfs 材料后才进入上述成功检查。页面字段检查前由测试端受控导航至测试页，因此本项证明正常入口、渲染和输入路径，不单独证明应用起始 URL 配置。

## 生产影响、清理与剩余条件

- 未替换 Adapter、控制器、模板目录或任何生产 Worker；未停止或重启新建浏览器。
- 新建浏览器的 Home、Session、core、Relay、Guard 和网络资源保留原状。
- 第一轮专用临时网络已删除；重放及 GUI QA 容器均已删除。GUI 临时 Home 和专属显示材料已清理；重放 QA Home 与报告保留用于复核。
- 候选阶段生产前置条件（已在下节追跑）：将 r10 纳入 accepted 模板目录并发布 Adapter/Worker，使用管理生命周期安全关闭当前故障代次、确认资源归零后从固定入口恢复；目标 Mac/Trilium 实测仍未完成。

## 生产恢复追跑 · 2026-09-29

上述候选随后按已授权的维护顺序完成生产落地：登记器补齐 R7D 元数据并通过 9 项单测，r10 以 artifact SHA `f785549f…` 登记，Adapter 候选 SHA `bbef7657…` 原子替换并重启。管理员在管理页完成近期密码确认，将“测试”提交为 Profile revision `7`，绑定 `env-tw-camoufox-r10`；旧故障代次先安全关闭，Home 保留且 records/workers/orphans/resources/relays/guards/networks 均归零。

用户随后从固定入口重新打开。只读 `inspect`/强制 `probe`（Adapter `readyz` 为 200）于 14:04 UTC 观察到：

- `status=running`，1 record、1 Worker、5 resources、1 Relay、1 Guard、2 networks；
- 环境为 `env-tw-camoufox-r10`，artifact SHA 与登记值一致；
- `overall=healthy`，`BROWSER_RUNNING`、`DISPLAY_READY`、`PROXY_OK`、`SESSION_RUNNING`、`REPORT_FRESH` 全部通过；
- 未出现 recovery 阻断提示，Home 未删除或重建为其他 Profile。

这证明生产固定入口和 r10 代次已恢复。目标 Mac/Trilium 的独立复测，以及生产远程桌面中实际右键后无 Firefox 菜单的直接用户证据仍未取得；因此 DEV-073、DEV-074 和 R7F 不在本节提前宣称完全收尾。
