# R6N · 自动分辨率验收

状态：服务器交付已部署；目标 Mac 实机反馈及生产实例主动切换待用户操作。工作项：[R6N](../../docs/work-items/R6N-2026-10-01-auto-resolution.md)。

## 契约与版本

Chromix 154.0.8037.57 / Linux / en-US / UTC / X11，独立自动屏幕产物 `chromix-154-en-us-utc-auto-r1`，显示模板 `chromix-x11-auto-r1`。远程屏幕随客户端窗口及客户端像素密度变化；远程 DPR 固定 1，最大 3840×2160，超限按比例缩小。模式随 Profile 模板绑定保存，不使用 localStorage 保存模式，不通过固定缩放偏好切换。

最终镜像 `sha256:e7e71db14431fa944b0593b5160104ecf61565b756e82cbeaf86f075b6b0af29`。固定 cjk-r2 字体/浏览器二进制和网络/退出层保持；新增自动模式启动契约、显式持久种子与标量默认值，以及精确摘要的 Selkies 布局上限/尺寸通知/绝对坐标映射补丁。不是固定环境所有指纹 API 等价性的证明。

## 证据与范围

- 10 项 Python 测试通过：固定/自动参数拒绝、尺寸限制、seed/Home 排他、字体与归档保护。
- R6M 精确部署源码上的最小 Adapter 候选完整 Go test/vet 通过；新增兼容目录、模式持久化、非法缩放拒绝、固定回退绑定和自动页面展示检查通过。未携带 R6I 容量或 R7G 发布改动。
- 最终镜像七组真实 Selkies WebSocket 客户端通过：1280×800、1600×900、800×600、回到 1280×800；新客户端 1024×768 的 DPR 1/2；2560×1440、DPR 2 超限到 3840×2160。全部检查真实远端 screen/窗口/DPR、可见画面中的点击和输入；三组重连使用新客户端上下文。
- 最终镜像的控制器 DIRECT / 认证代理无旁路、故障拒绝、三类存储与 seed 保留、正式入口、管理创建/回显、关闭拒绝后原资源保留、正常重试及加密新 Home 恢复均通过。实际固定模板应用和自动历史回退通过，Home/应用身份保持。结果见 `integration-final/` 与 `binding-cycle-result.json`。
- 初版超大客户端未调整屏幕，后续仅限后端的版本仍有前端画面/坐标差异，均保留失败与正常清理记录。修复见 [DEV-096](../../docs/deviations/DEV-2026-10-01-096-auto-resolution-limit.md)。早期无头探测、候选启动器挂载和中间镜像结果不替代最终镜像验收。

私有证据根：`infra/sealskin/runtime/r6n-auto-20261001/`。关键材料为 `client-final/`、`integration-final/`、`source-review.json`、`catalog-release/`；部署完成后另记录 `deployment.json`。详细日志/账号/Session URL 不公开。

## 发布与限制

仅追加自动模板并更新最小 Adapter，不停止或重建生产 Worker。现有 Chromix 需在管理页面停止后选择匹配自动指纹与显示模板，再应用并打开。固定分辨率模板仍可选，原 Home/seed 保持；切换是环境修订操作。

本项新增仅支持 Chromix。旧 Work 原有自动模式保持；Camoufox 自动屏幕、WebRTC 传输专项、触屏/多显示器并发、Mac 实机仍未验收。Linux QA 的成功不替代目标 Mac 用户反馈。

回退：只在配置未发生后续写入时恢复部署备份。任一 Profile 或历史中已出现新 `resolution_mode` 时保留兼容 Adapter，不以旧二进制解析新 schema；通过正常停止/模板回退恢复固定模式，不能覆盖用户后续修改。

上线收尾：最小 Adapter SHA-256 `a840a43f9d1e8cecfd1e49cf97c1ce7ba30a90527a7f93fe4621a3143a47413b`，两个目录仅追加自动条目，所有原条目/顺序保持。部署前后容器 ID/启动时间、Profile 目录及 Personal/Work/现有 Chromix 绑定一致；三者新鲜健康均为 healthy。QA 代次、控制器、上游、后台进程与显示 tmpfs 已清理，私有证据保留。未新建或重建任何生产 Home，没有启动下一计划。

用户后续反馈（2026-10-01）：已切换自动分辨率，使用正常；左侧 UI Scaling 未生效作为 R6O 独立修复。原测试未覆盖此控件，不改写成已经验收。
