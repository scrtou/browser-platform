# R4B · 迁移能力修复与目标客户端阶段验收

[工作项](../../docs/work-items/R4B-2026-09-14-target-client-migration.md) · [DEV-040](../../docs/deviations/DEV-2026-09-15-040-migration-controller-capabilities.md) · [DEV-041](../../docs/deviations/DEV-2026-09-15-041-camoufox-window-size.md) · [DEV-042](../../docs/deviations/DEV-2026-09-15-042-work-wayland-shutdown.md) · [DEV-043](../../docs/deviations/DEV-2026-09-17-043-caddy-api-config-persistence.md) · [DEV-044](../../docs/deviations/DEV-2026-09-17-044-production-maintenance-runner.md) · [客户端矩阵](../../docs/client-matrix.md) · [运维步骤](../../docs/operations.md#camoufox-入口切换与回退准备)

日期：2026-09-15–17，UTC。状态：**已收尾，生产切换、目标 Mac 与正式 Caddy/Docker/VPS 重启通过**。迁移前能力检查、失败代次清理和生产启动保护已验证；用户确认 r7 Mac 基础分项，并提出窗口过小。r9 已通过完整产物、正常桌面、Linux 公网客户端及实际截图预览验收；用户随后确认 r9 按钮和页面图片预览，但仍看到固定画面上下留边。新的 `fill-r10` 客户端候选已在同一 r9 环境与 QA Home 上通过全视区缩放和坐标回归，用户已确认 Mac 视觉铺满且点击映射正常，但反馈 Trilium 未横向展开时字体细长、分辨率观感与 Work 不同；该非等比显示取舍已记录。Work Firefox/Wayland 的新建兼容候选已通过退出、显示、恢复和秘密边界组合验收并清理专用 QA。`release-ready-2` 已部署共享控制器、账号入口、Work 兼容镜像和 r9/fill-r10 Personal；本机/公网认证、目标 Mac 生产入口及正式 Caddy/Docker/VPS 重启通过。R2 的退出全部登录与 Debian 13 在本报告收尾时仍待外部条件，用户于 2026-09-20 后续取消两项。

## 发现与实际处理

本轮开始时，生产配置已经指向 `personal-camoufox-r7` / `camoufox-personal-r7-guard`，此前两次启动未成功，当前 operation 为 `unknown`。Session/Worker 为 0，但有 reservation、launch、Guard、Relay 和两个网络，共 6 项资源；另有使用独立 debug Home、`network=none` 的调试容器。旧控制器未具备 r7 的显示材料和正常退出能力，调试日志出现 `SESSION_AUTH_INPUT_INVALID`，此前进度遗漏了已发生的切换和失败。

通过当前 Adapter 的原配置执行 `stop`，确认 records/workers/resources 均为 0，绑定转为 `stopped`。调试容器核对精确 ID、镜像、挂载及无浏览器进程后正常停止并带匿名卷删除；debug Home、旧 Personal Home、新失败 Home、两个 R2C age 归档及最新 journal 保留。没有恢复旧 journal 或启动真实旧 Personal 浏览器。

准备器现在按产物绑定的精确镜像读取 `io.browser-platform.browser-shutdown` / `io.browser-platform.session-auth`，要求运行 Adapter 报告控制器实际版本；网络/启动日志和镜像要求缺失时，在生成候选前拒绝。匹配时写入 Profile 的 `required_runtime_capabilities`，结束时再次核对能力和输入。新 Adapter 在创建 Home、启动/复用、恢复前和启动后核对要求，能力不足返回 503；停止/清理仍可执行。新控制器增加 `session_auth_version: 1` 的能力声明，原 r7 镜像和产物保留；后续窗口修订另生成 r8/r9，不覆盖旧材料。

## 版本与证据

本机私有根：`infra/sealskin/runtime/r4b-production-migration-2026-09-15/`。下列路径相对该目录；详细 HTTP、账号、容器 inspect 与 Session 材料保存在忽略目录，不随公开仓库分发。

| 对象 | 版本 / 位置 |
| --- | --- |
| 控制候选 | `candidate-2/build/`，release `0.3.2-entry-auth-v1-2ba57382ce75c8f9`；runtime ID `sha256:9aac44025870667836a3043906ad5d0ecbd6cf7233b5425ade7163bc5474d80d` |
| 控制 tests 镜像 | ID `sha256:ac6c880d627b9c1a9807e09cf85f7ca1e73444e03663d0406cfb7ced13220d32` |
| 最终 Adapter | `candidate-4/bin/profile-adapter`；SHA-256 `7e7ab79ecd842e2cb40900c615f3e34b4639a88155b733dbd769e24bb9688463`；生产与 QA 运行二进制一致 |
| r7 原 Worker | `sha256:4baf6233f9410477937eeb4cca40e6a046b2cbed951ec3c49206c40976987d20`；用户首次反馈及 R5D/R5E 范围保留 |
| r9 最终 Worker | `sha256:10f6420a1e409ce98cdc18a8830f023b46a30e4697d258126d6bf591c8fcc371`；r7 的精确后代镜像，仅增加去边框桌面层 |
| r9 产物 | `infra/camoufox/artifacts/env-tw-camoufox-r9.json`；SHA-256 `b8d98426224be7abc5904c20f2ccf5283298930fc09f228b642d39cd8f322e95` |
| r9 完整验收 | `infra/camoufox/evidence/acceptance-r9-1-2026-09-15.json`；SHA-256 `a75978298efea79964e24c2a659b8322131e7881dbbdc2b7a16ef22215ea370d`；测试源码摘要 `d8304a2ed2ab90db859289d76761eff8e816eaa229eb44c01164bf51c69743d9` |
| 生产保持/清理/保护 | `continuation-1/` 保留初始处理；`continuation-2/production-protection.json` 为最终文案、Personal 拒绝及 Work 复用结果 |
| 迁移准备真实检查 | `migration-preflight-results.json`、`production-preflight.log`、`qa-migration-preflight/` |
| r7 Linux / 公网 | `candidate-2/client-boundary-1/client-boundary.json`、`mac-public-check-3/result.json` |
| 用户 r7 反馈 | `mac-client-user-report-excerpt-174804.json`、`mac-client-user-report-check.json`；摘录不是完整原始事件，完整输入保留在用户对话中 |
| r9 桌面与客户端 | `window-r9/stage-1/`、`window-r9/desktop-client-1/`、`window-r9/boundary-client-1/`；包含原生几何、画面、像素和文件摘要 |
| r9 构建与重放 | `window-r9/image.json`、`window-r9/build-2/`、`window-r9/replay-1/`；重放临时代理和两条网络已清理 |
| fill-r10 客户端候选 | `window-r10/stage-1/`、`window-r10/desktop-client-1/`、`window-r10/boundary-client-3/`、`window-r10/final-verification.json`；同一 r9 环境/Home，固定画面填满视区 |
| Work Wayland 退出候选 | `work-compatibility-1/shutdown-build-1.json`；`sha256:3077a7377df368bb90e0f9a83f6d6c8f0d66a4b0ee78585cf1a70d0113004198`，原 Work 镜像为完整层前缀 |
| Work 最终兼容镜像 | `work-compatibility-1/access-build-1.json`；`sha256:ec848635e68db2d1c805fcf9972ef4586bcd86a9ed14b2075b0c5a40fbbc503f`，退出/显示能力均为 1 |
| Work 组合与发布候选 | `work-compatibility-1/combination-1/`、`release-candidate-1/`；控制器/s6、入口/错误材料、恢复/秘密扫描通过，App 仅替换镜像，未部署 |
| 版本与发布复核 | `final-review-1/versions-and-production.json`、`final-review-1/migration-release-audit.json`；旧 `release-review-1/` 只适用 r7，不能用于 r9；完整发布仍为 `REVIEW_ONLY_BLOCKED` |
| 文档与静态检查 | `static-check-1/`–`static-check-10/` 保留前轮/中间结果；最终 `static-check-10/` 核对 51 个公开文件、23 份 Markdown/699 个链接、语法、格式与敏感扫描 |
| 生产发布 | `release-ready-2/deployment-2/`；控制镜像 `sha256:9aac4402…`，Work `sha256:ec848635…`，Personal `sha256:10f6420a…`；两次维护失败与最终续接结果均保留 |
| 正式重启 | `release-ready-2/after-caddy-restart-1/`、`after-docker-restart-1/`、`vps-reboot-1/`（`before.private.json`、`after.private.json`、`system-boot.log`、`adapter-boot.log`、`recovered-live-check/`、`health-result.json`、`authenticated-session-result.json`、`work-probe-after-expired/`）；`live-check-3/` 为重启后最终只读复核 |

## 已完成验证

| 场景 | 结果与范围 |
| --- | --- |
| 控制器回归 | 固定新镜像 **534 passed，0 skipped**；`candidate-2/controller-tests/`。包含新增能力声明检查，未重跑所有历史公开 DNS/故障矩阵 |
| Adapter | 候选 3 全包 `go test ./...` / `go vet ./...` 通过；候选 2 全包 race、候选 3 `internal/profile` / `internal/httpapi` race 通过。候选 4 仅修正维护文案及断言，受影响 HTTP test/vet 再通过；其余代码未变 |
| 应用/迁移准备 | **10 项** Python 检查通过；覆盖版本缺失/未知、布尔冒充整数、网络能力、原绑定和策略保持及账号/CA 相对路径 |
| 启动拒绝与保留 | 缺少能力时不创建 Home、不发 launch、不写新 journal；匹配允许启动，启动中能力漂移保留 unknown；降级后的复用/恢复拒绝，已验证停止仍可进行 |
| 实际生产拒绝 | 原控制器的两项版本均为 0；迁移工具拒绝且没有输出候选、新 Home 或输入变更。候选 3 连续三次 **503**，最终候选 4 POST start 再返回 **503**；Personal 保持 stopped、资源 0，operation 未改变 |
| Work 回归 | 最终候选 4 公网 GET **200**、POST start **303**，复用 R2C 于 14:05:15 UTC 启动的原 Work Session/Worker；其 `AutoRemove=False`，未重建 |
| 实际 QA 准备 | 相同 r7 输入在新 QA 控制器上成功生成仅供审查的候选，能力为 1；旧策略、journal、配置保持，新 Home 不存在 |
| r7 Linux 客户端 | 三组尺寸/DPR、15 次可信坐标点击、Unicode/composition、导航/标签/滚动、Files 按钮/拖放及远端摘要、显示断线与离线重载恢复通过；CDP 不能替代 Mac 输入法/Finder |
| 公网授权与串流 | Linux Chromium 以实际公开 HTTPS 登录，干净 Session 地址、12 个实际二进制显示帧、无 Cookie 返回 **401**、重载后新帧通过；仅覆盖本项 QA 路由 |
| Work 正常退出 | 10 项 Wayland 协议/身份检查及独立真实探测通过；控制器 stop 在关闭对话框存在时返回 **503** 并保留原 Worker/Home，取消后重试清空；没有发送终止信号或代按确认 |
| Work s6 与恢复 | `docker stop -t 30` 退出码 **0**；同一 Worker ID/Session resume，控制器停止前及 s6 停止前即时写入的 Cookie/localStorage/IndexedDB 均读回，私有显示材料重建 |
| Work 入口与材料 | 三个 Linux Chromium 入口客户端共 **44** 个真实显示帧，错误登录/无 Cookie/输入检查通过；缺失、错误 Session、权限过宽、符号链接、可写输入五类实际 `/init` 拒绝且无显示监听 |
| Work 秘密与清理 | 密封 Session 和只读材料挂载通过；正确 Basic Auth 1 次、缺失/错误 3 次拒绝；扫描 55 个进程、218 个 Home 文件、共 342 面无泄漏。专用代次/固定容器/网络/卷/进程/socket/tmpfs/端口清理完成，生产 Work 与 Mac r9 三容器身份保持 |
| 发布配置审查 | 旧 r7 审查包的两份 Caddy、临时账号配置和 Compose 合并通过。Work 新 App 私有候选只替换精确镜像且已核对；旧完整包仍不能用于 r9，须重新准备匹配 r9/Work 的组合配置，缺失前置保留，不套用 QA 账号 |
| 完整生产包 | `release-ready-2/` 状态 `READY_FOR_MAINTENANCE`；在原 38 文件包上补 Caddy API autosave systemd drop-in，共 39 文件。r9/fill-r10 Personal、Work 兼容 App、两 Profile 能力门槛、账号表、私有 TLS、Caddy、Compose、tmpfiles/Docker/Caddy 顺序和回退步骤通过独立复核 |
| 生产维护与入口 | 旧 Work 经生命周期停止且资源归零；候选控制器密封 Session 状态，两个 App 精确安装。登录 200、未登录 Profile 303、Session 根 404、两个精确 Session 无 Cookie 401；登录/交接/最终 Session 200，Caddy 运行 JSON 与候选一致 |
| 生产代次 | Work 为 1 record/1 Worker、资源 0，能力 1/1；Personal 为 1 record/1 Worker、5 resources/1 Relay/1 Guard/2 networks，能力 1/1、network phase running。旧 Personal Home、r7 Home、新 r9 Home 和 Work Home 均保留 |
| 上线后只读复核 | `check-r4b-production-live.py` 核对 Docker/Caddy/Adapter active+enabled、`Linger=yes`、Caddy autosave drop-in 与精确运行 JSON、两 Profile 数量/镜像/能力、静态 Relay 身份、四个 Home、秘密文件权限、本机/公网未登录边界和精确 Session 无 Cookie 401；`live-check-1` PASS，不输出或保存 Session 值 |
| 目标 Mac 生产复测 | 用户在 macOS 15.1 / Trilium 0.105.0 打开正式固定入口，确认生产账号登录、Personal 画面铺满、点击映射、实际图片预览和 Work 打开全部正常；脱敏 `target-mac-production-1` 及随后 `live-check-2` PASS，不含凭据或 Session URL |
| 正式 Caddy 重启 | 14:01 UTC 新 Invocation 使用 `--resume` 启动；autosave 运行 JSON 与候选精确一致，公网登录页/固定入口/Session 边界及 Work/Personal 运行态由 `after-caddy-restart-1` 全部复核通过 |
| 正式 Docker 重启 | `live-restore=false`；14:05 UTC 新 daemon 后控制器/静态 Relay 自动恢复，Personal Worker/Guard/Relay 与 Work Worker 同 ID/镜像休眠；14:06 UTC Adapter 启动对账约 12 秒恢复。两 Profile healthy，Personal `PROXY_OK`，登录/交接/最终 Session 200，Caddy 候选保持；私有证据 `after-docker-restart-1/` |
| 正式 VPS 重启 | 14:16 UTC `sudo reboot`；关机时两个 Worker `BROWSER_SHUTDOWN_CONFIRMED`、六个容器退出码 0。新 boot 14:16:44 UTC linger 启动用户管理器/Adapter（早于 14:16:55 UTC 首个 SSH 登录），Caddy `--resume`，Docker 14:16:45 UTC 自动拉起控制器与静态 Relay；Adapter 14:16:58 UTC 取得控制面后 Relay 14:16:59 → Guard 14:16:59（规则就绪）→ Personal Worker 14:17:02 → Work Worker 14:17:07，14:17:09 UTC 对账完成。boot id 变化，六个容器 ID/镜像与两 Session 不变，四个 Home 保留，策略/账号表/密封密钥摘要不变；14:21 UTC `recovered-live-check` PASS，登录/交接/Session 303/303/200，Personal healthy/`PROXY_OK`；Work 首份为 14:20:07 UTC 的过期缓存报告（`unknown`/`REPORT_EXPIRED`，其余分项通过），14:36:46 UTC 重采集 healthy/`REPORT_FRESH`。未采集启动窗口抓包/事件流，未读回浏览器存储 |
| 重启后最终复核 | 15:15 UTC `live-check-3` PASS：Docker/Caddy/Adapter active+enabled、`Linger=yes`、Caddy `--resume` 与 tmpfiles/Docker 顺序 drop-in 生效、运行 JSON 与候选精确一致、两 Profile 数量/镜像/能力、静态 Relay 身份、四个 Home、秘密材料权限、公网/本机边界 200/303/303/404、精确 Session 无 Cookie 401；不记录敏感值 |

生产现已使用共享认证控制器和 Adapter 网关；静态 `profile-relay-personal` 身份保持，Work 与 Personal 均为新代次。该事实只表示 R4B 组合已部署，不追写 R5D/R5E 当时的 QA 范围；目标 Mac 生产实测与正式 Caddy/Docker/VPS 重启均已单独记录。

## 窗口修订与目标客户端

用户记录的目标为 macOS 15.1 (24B83) / Trilium 0.105.0，本机 1280×800、正常显示、macOS 系统中文输入法。用户确认 r7 的五个按钮/中文/😀/𠮷及候选取消、双向文字、Files 按钮选择/Finder 拖放、后退/前进、新标签页与断网恢复重载通过；截图只确认桥接成功提示，未确认页面预览。17:48 UTC 报告中的五个可信点击均命中，三类测试存储值一致；完整测试序列及 Mac 本机 DPR 不能从这一份远端报告推断。

r7 的远端 screen 为 1920×1080、DPR 1，但窗口 outer 1600×900、inner 1600×844、位置 (160, 90)。`resize-window.py` 保留完整 BrowserForge 来源、设备/种子/preferences，生成全桌面窗口的新修订；r8 正常桌面的四侧 1 像素边框仍导致客户区与重放不一致，因此在精确 r7 镜像上加 `keepBorder=no` 桌面层并重绑为 r9。没有修改冻结 screen/DPR 或在旧产物下临时最大化。

| r9 场景 | 实测结果 |
| --- | --- |
| 窗口准备器 | 3 项检查通过：原来源/设备保持、非法修订拒绝、位置与窗口一致 |
| 完整产物 `all` | 结构检查、11 类启动拒绝、两个 Home 各 10 次重建及离线恢复通过；23 次环境/窗口观测一致，三类存储恢复通过 |
| 正常 Openbox 桌面 | 原生客户区位于 (0, 0)，1920×1080，四侧 frame extents 均为 0；实际网页 outer 1920×1080 / inner 1920×1024，与重放一致 |
| QA 升级与清理 | 原 QA generation 经生命周期正常 stop 后启动 r9，保留同一 Home；三类存储与用户 r7 报告一致。实机确认结束后，fill-r10 代次再经生命周期 stop，records/Worker/Guard/Relay/网络及显示材料归零；临时账号禁用、两条 route ID 删除、Adapter 停止，生产文件和进程身份保持 |
| 公网登录与坐标 | Linux Chromium 151 模拟 Mac 键位，1280×800 的 5 次和三组尺寸/DPR 的 15 次可信点击通过；干净交接、无 Cookie **401**、337 个显示帧及重载通过 |
| 真实截图预览 | 客户端原生剪贴板/CDP paste → Selkies → 远端页面实际预览通过；320×160 PNG，可信 paste、尺寸及完整 RGBA 像素 SHA-256 与源图相同；画面已查看 |
| 固定画面填充候选 | 用户反馈 r9 按钮和实际图片预览通过，但 1280×800 视区仍有上下留边。`fill-r10` 将 WebRTC/WebSocket 手动显示映射到客户端完整边界；1280×800 的 canvas/输入层均为 1280×800，三组尺寸/DPR 的 15 次可信点击和远端固定 screen/DPR 通过 |
| 客户端边界 | Unicode/composition 保留前缀，后退/前进、新建/切换/关闭测试标签页、滚动、Files 原生选择/可信 CDP 拖放通过；两个文件的远端 Home 摘要相同。断开 WebSocket 后重载、离线重载恢复通过，Worker 身份和存储保持 |
| 最终版本核对 | 50 个 Go 源文件、go.mod、四个构建二进制、生产/QA 实际运行 Adapter、32 个控制端运行文件和 5 个构建输入一致；r9 镜像层/标签、窗口产物/报告/测试源码、实际挂载页面一致 |
| 阶段静态收尾 | `static-check-10/` 的 51 个公开文件、23 份 Markdown 的 699 个本地链接/锚点，13 个 Python、1 个 JSON、1 段嵌入 JS 语法、7 个 Go 文件格式及 `git diff --check` 通过；已知 QA 密码/Cookie/授权参数未进入公开文件，私有材料保持忽略 |

本轮新预览区只用于测试图片，不改生产剪贴板桥接。大文本、反向复制、取消/权限异常及完整网络/一致性历史矩阵仍按 R4A/R5 各自版本引用，没有声明在 r9 全部重跑。Linux/CDP 结果不替代 Mac 原生输入法、Finder 或 Trilium 实机。

## Work Firefox/Wayland 兼容候选

生产 Work 原先运行 2026-09-15 14:05:15 UTC 启动的旧镜像 `sha256:7e3dbebd…`；2026-09-17 维护中经正常生命周期停止，随后用候选 `sha256:ec848635…` 新建。候选以旧镜像为基础，先增加固定 labwc/Firefox 的 Wayland 原生关闭层，再增加 R5D 的显示认证层；层前缀、能力标签和 12 个源文件摘要逐项一致。适用范围仅为独立 Worker 中唯一已核对的 Firefox 主进程、可信 labwc socket 和 version 3 顶层协议下无 parent 的 `firefox` 窗口。

完整组合使用独立控制器、Adapter、临时 Home、账号、网络、入口和显示 tmpfs。实际关闭对话框使 stop 在约 12.5 秒后返回 503，Worker、浏览器身份和 Home 占用保留；取消对话框并移除页面处理器后，同一路径重试正常停止。随后新建代次、恢复三类存储，再以 `docker stop -t 30` 触发 s6 down，容器退出码为 0；控制器 `resume` 接回同一容器和 Session，并读回停止前即时写入的三类存储。首个重试仍保留页面处理器而再次失败，作为测试操作历史保留，没有改写为通过。

真实入口三轮分别取得 6、11、27 个显示帧。五类错误显示材料全部在候选镜像的实际 `/init` 阶段以 `SESSION_AUTH_INPUT_INVALID` 拒绝，未监听显示端口。密封状态、正确/错误 Basic Auth、只读输入和 342 面秘密扫描通过。私有发布候选以生产 `firefox-work` 原始/解析定义为输入，只把镜像改为精确候选 ID；生产 origin、原生 Wayland 启动脚本、Files/剪贴板挂载、用户和自动更新设置保持，QA 的远程调试参数不存在。

最后一次真实控制器 stop 后 records/workers/resources 均为 0。清理脚本先后误判成功响应的嵌套结构和 Adapter 自动删除控制 socket，两个失败文本保留；续清理最终移除两个固定容器、两个匿名卷、专用网络、三个私有进程、剩余 socket、空显示 tmpfs 并确认六个端口关闭。生产 Work 与 Mac r9 的 Worker/Guard/Relay ID、镜像、启动时间在清理前后相同。该结果解决 Work 后续新建兼容前置，候选仍为 `REVIEW_ONLY_BLOCKED`，没有执行生产 App 更新。

## 失败历史与未完成条件

`candidate-1/` 的失败启动和调试证据保留。首次 Adapter 重启后的检查早于 socket 就绪，改为有界就绪等待；首版能力拒绝被通用错误处理映射为 502，随后修正为 503 并复测，记录在 `continuation-1/entry-rejection-first.json`。没有把首次结果改写成通过。

公网检查首轮使用了不匹配实际 HTML 的 button selector；第二轮将缺失 Cookie 的正确 401 错误预期为 403。修正测试假设后第三轮通过，未放宽身份检查。Caddy 的非 root CLI 检查无法读取既有只读 CA；固定 Caddy 容器只挂载该公开 CA 和候选配置完成验证，生产 TLS 配置未放宽。

候选 4 的 manifest 首次假设标准库 Go 项目有 `go.sum` 而失败；测试/build 已完成，随后按实际 `go.mod` 记录输入，没有创建空依赖文件。生产 Work 复用首次检查错误地按大小写查找 `Location`，而 Caddy 返回小写 header；按已保存响应作大小写不敏感校验后通过，没有重复发启动请求。最终维护文案移除了“未启动新会话”的过度保证，launch 后能力漂移仍保留 unknown。

r8 首轮重放引用已清理的旧 QA 网络，在浏览器启动前失败；第二轮新增窗口断言误复用存储期望变量，实际三类存储一致但比较对象错误；修复后第三轮完整重放通过，随后正常桌面揭示 1 像素边框问题。r9 桌面层首轮构建把裸 image ID 用作 BuildKit `FROM` 而失败，改用核对到同一 ID 的本地标签后构建成功。r8 staging 还修正了对合法 `embedded=true` 的过严断言和旧 published 元数据缺少 routes 的处理；已从实际 runtime/route 续接核对，没有重复创建或覆盖旧证据。上述失败均保留在各轮目录。

用户已反馈 r9 五个按钮可点击、页面可见图片预览，但固定画面没有铺满，且 Work 页面显示正常。只读核对确认 r9 远端桌面/浏览器原生几何已经铺满，留边来自客户端 `contain` 缩放；`fill-r10` QA 已按同一 Home/环境重新启动并通过 Linux 画面边界、点击、截图和存储回归。用户已确认 fill-r10 在 Mac/Trilium 视觉铺满且点击映射正常，同时观察到窄视区的非等比缩放使字体细长；该结果完成 DEV-041 的客户端验收，固定分辨率取舍保留。确认结束后，账号已禁用，浏览器、Guard/Relay、网络和显示材料归零，私有 Adapter 停止，两条专用路由删除；QA Home、基础 QA 控制器和验收证据保留。生产文件及容器身份复核不变。Mac 新修订反馈与其他未测边界分别登记，**不据此宣布 Mac 全矩阵或生产迁移通过**。

首个生产包准备和独立验证未改动生产；发现 API 加载的 Caddy 配置不能跨服务重启后，`release-ready-2` 增加 autosave drop-in 并重新完成 39 文件复核。管理员已安装 tmpfiles、Docker/Caddy systemd drop-in 和 0700 `/run/browser-platform/session-secrets`。维护过程的控制 socket 指纹、QA 管理端口、多 Cookie、根路径状态和 `embedded` 断言失败均保留，修复后从当前 journal/阶段续接，详见 DEV-043/044。

本报告收尾时仍缺 R2 的退出全部登录持续运行验证与 Debian 13；Caddy/Docker/VPS 正式重启已经通过。目标 Mac 已确认生产账号登录、Personal 画面/点击/图片预览和 Work 打开正常；回退材料已保留但没有为了验收而破坏当前成功代次执行回退。上述结果完成实际切换、本机/公网认证、生产实机、daemon 与整机恢复验证；R4B 已收尾。2026-09-20 用户后来取消退出登录与 Debian 13 两项，它们保持未执行且不记为通过。
