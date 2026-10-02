# R6AR · 缩放百分比持久化与旧 Work

状态：已收尾并部署。开始：2026-10-02。前项 R6AQ 已收尾并提交 66193f0。

范围：用户已要求完成缩放百分比保存与旧 Work 显示支持。新增 Profile `ui_scaling_percent`，0 沿用客户端默认，100–300 的 25 步长为显式百分比。支持已登记 auto@system 模板与旧 Wayland Work；固定屏幕/DPR1、旧 auto@1 不能写非零值。百分比与 contain/fill 分开：后者仍只适用于固定画面。旧 Work 自动显示提供百分比设置，不伪装为固定画面比例模式。

入口与状态：管理 update → BrowserPatch/目录 revision 原子保存；当前 Session 授权与绑定 → 精确摘要 Selkies JS 读取已保存 DPI → 原生 scaling_dpi 消息改变显示。远程 UI 的手动更改通过该已授权 Session 的专用同源/CSRF 入口保存，不能选择其他 Profile；允许已有显示控制权的用户修改这一低影响设置。并发以目录 revision 检测冲突，不自动重试覆盖他人设置。新客户端/重新加载读取最新值，已打开的其他页面须刷新；不保证多个同时控制者的实时同步。

默认未设置不改原始环境/模板/Worker/Home。支持客户端初始化按保存百分比覆盖本地值；重置为0恢复客户端默认 DPI。新模板绑定清除百分比，避免把可变 DPI 套到固定契约。未知资产摘要不变换；固定模板的原几何与输入路径保持。

完成条件：字段白名单/持久重载/并发与权限隔离；管理回显、远程 UI 保存、重连/不同客户端 DPR、旧 Work 和 auto/system 三引擎代表性真实画面/输入验证；固定模板拒绝且原行为通过；精确当前 Adapter 基线上的最小增量全 test/vet、保护部署、文档与 Git 收尾。此次新增持久化的跨客户端实测与用户既有反馈分别记录。

代码地图：`service.go`/`directory.go`/`template_catalog.go` → `manage.go` → `access/proxy.go` 的 Session gate → `display_preference.go` 的资产摘要校验及新增 scaling 模块 → 固定 Selkies `uiScalingSelect` handler / localStorage 初始化 / scaling_dpi WebSocket。生产基线为 `.2` R6AM Adapter，R7G1 控制器与 R6Z1 runner 保持。

测试资源独立，真实 Home/会话/操作日志保持。私有证据 `runtime/r6ar-display-persistence-20261002/`。旧 Work 原缺口见 DEV-095；新增偏差即时登记。

文档清单：Adapter/显示组件 README、显示设计/管理规格、DEV-095、验收及索引、progress/roadmap/剩余执行表、工作项/索引、部署恢复限制。

- [x] 实现和精确源码回归
- [x] 真实显示/持久化/隔离/兼容
- [x] 保护发布、文档、恢复增量和 Git

实施进展：字段、管理表单、Session CSRF/归属、revision 冲突和精确资产变换完成；候选全 Go test/vet 通过，真实显示验证进行中。QA 首轮修正了合成 Basic 用户必须为规范 UUID、只读客户端的临时配置目录、`__Host` Cookie 根路径和隔离网络到宿主监听不可达等夹具问题；失败日志保留在任务运行目录，未影响生产。真实显示夹具改为与 QA Worker 共用隔离网络命名空间，未修改宿主防火墙。

真实显示发现当前镜像的 Selkies 摘要白名单缺口，见 [DEV-130](../deviations/DEV-2026-10-02-130-scaling-asset-coverage.md)，先修复当前资产覆盖再继续验收。

收尾：实际 Adapter `8fb90eb2…`；30 个真实显示场景、两套完整 Go test/vet 与针对性 race、15 路径补丁/120 文件重放、前后生产保护和 128 文件异机增量全部通过。DEV-095/130 关闭，组件/设计/规格/操作/验收索引与进度计划更新。详见 [验收](../../infra/sealskin/r6ar-display-persistence-acceptance-2026-10-02.md)。开发树原有改动保留，本项源码按精确 .2 基线补丁提交；下一项完整固定版本矩阵具备开始条件。
