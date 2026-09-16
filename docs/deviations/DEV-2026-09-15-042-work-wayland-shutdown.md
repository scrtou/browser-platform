# DEV-042 · 共享发布缺少 Work 的 Wayland 正常退出能力

状态：已解决（代码/隔离验收，未部署）。发现日期：2026-09-15。解决日期：2026-09-16。关联 [R4B](../work-items/R4B-2026-09-14-target-client-migration.md)。

## 预期与实际

共享控制器发布后，Work 应能保留当前 Firefox/Wayland 路径并正常新建、停止和恢复。显示认证构建器要求正常退出层，但当前退出层仅验证过 X11，不能直接把其能力标签用于 Work。

使用生产同一精确 Firefox 镜像、独立临时 Home、`network=none` 的探测容器已确认：Firefox 的顶层窗口由 labwc 的 `zwlr_foreign_toplevel_manager_v1` version 3 管理，app_id 为 `firefox`。旧退出脚本实际返回 `BROWSER_DISPLAY_UNAVAILABLE`，未关闭浏览器。R2B 的 BiDi 关闭只用于测试，不能作为生产后台退出接口。

证据位于本机忽略目录 `infra/sealskin/runtime/r4b-production-migration-2026-09-15/work-compatibility-1/`：`probe-created.json`、`probe-processes.json`、`wayland-discovery.json`、`old-x11-shutdown-on-wayland.log`。没有操作生产 Work 或用户 r9 QA 的桌面。

## 处理决定与验证

修复实现：为固定 labwc / Firefox 增加 Wayland 原生关闭路径，核对浏览器进程身份、桌面 socket 与 compositor 身份，使用标准窗口管理协议请求关闭。协议不提供每个窗口的 PID；因此适用范围限定为独立 Worker 中单一已核对的 Firefox 主进程和 `firefox` app_id，排除有 parent 的对话框与其他应用。浏览器、compositor、窗口状态无法核对时拒绝，不发送终止信号、不代按确认按钮、不启用生产调试端口。

完成条件保持正常退出和数据安全要求：普通关闭、关闭确认框导致超时且保留 Worker/Home、取消后重试、即时三类存储及容器/控制器恢复；新显示认证层还须通过实际入口、错误材料拒绝与秘密边界检查。新镜像有独立不可变身份，旧 r9 继续绑定此前退出层；不能扩大历史 X11 结果或直接加标签宣称 Work 通过。

最终候选以原 Work 镜像 `sha256:7e3dbebd…` 为完整层前缀，正常退出层为 `sha256:3077a737…`，叠加显示认证后的固定镜像为 `sha256:ec848635…`。10 项协议/身份单元检查通过；真实控制器 stop 在关闭对话框存在时返回 503 并保留同一 Worker/Home，取消后重试正常清空。`docker stop -t 30` 的 s6 路径退出码为 0，同一容器/Session resume 后读回即时 Cookie、localStorage、IndexedDB。

三个实际 Linux 入口客户端共取得 44 个显示帧并通过登录、Session 和输入检查。缺少输入、错误 Session、权限过宽、符号链接和可写输入五类材料均在实际 `/init` 阶段拒绝，342 个 Docker/进程/Home/日志面未发现材料泄漏。私有发布候选只替换生产 Work App 的精确镜像字段，保留 origin、启动脚本和剪贴板挂载；状态 `REVIEW_ONLY_BLOCKED`，未部署。

专用 Worker、控制器、上游、网络、匿名卷、私有进程、socket、显示 tmpfs 和端口均已按身份清理。清理脚本两次把成功响应嵌套和退出时自动删除 socket 误判为异常，失败记录保留，续清理最终通过；生产 Work 与 Mac r9 Worker/Guard/Relay 的 ID、镜像、启动时间前后相同。真实 Work 迁移、共享控制器发布及正式主机重启仍依赖 R4B/R2 的相应条件。
