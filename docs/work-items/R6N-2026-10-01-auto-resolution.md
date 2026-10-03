# R6N · 自动分辨率

状态：服务器交付已收尾、已部署；现有生产 Chromix 未切换，目标 Mac 实机反馈待用户操作。

用户希望增加与 Work 相同的自动分辨率，偏好仍按远程浏览器保存、跨客户端共用。本项单独推进，R6M 已部署的固定画面缩放保持。

范围：核查 Selkies 自动调整桌面、Chromix/Camoufox 屏幕指纹与窗口观测的关系，定义固定/动态环境边界，再实现可用模式。用户已明确选择与 Work 相同：网页可见屏幕也随窗口变化；不得以关闭全部指纹来默认为用户实现。

代码地图：管理页面 → Profile directory/revision → template_catalog 的 screen/scaling 兼容校验 → environment artifact 与 Worker 启动器 → Selkies 分辨率请求 → X11/Wayland 后端 → 浏览器 screen/outer/inner/DPR。Gateway 的 R6M CSS 几何变换只处理固定缩放，不能替代真实远端 resize。

已核对：Work 使用 Wayland 且没有 MANUAL_WIDTH/HEIGHT；Chromix 启动器强制 X11、固定尺寸与 fingerprint-screen 参数，目录只接受数值 screen。已安装 Selkies 的 display_utils.py 有 X11 xrandr resize 路径，不能据此声称真实端到端已通过。Chromix 固定源码 3b338c8bfda663d597d383d24f8fc20870d219e4 的 flags 文档说明省略 screen 参数仍有平台默认值；实际二进制行为待隔离核查。

完成条件：定义明确且不静默改变固定环境；按 Profile 保存并正确回显；支持范围内真实桌面、screen/window/DPR、宽窄窗口、输入坐标、重连、正常停止/恢复通过独立 QA；非法/不兼容组合拒绝；最小部署和健康复核；未支持引擎明确提示。全部条件达到前保持未完成。

验证与维护：只使用新建隔离 QA Home、无外部网络的能力探测；正式模式再做认证显示与完整生命周期验收。保留现有脏树、生产 Home/Session/容器，不全量部署；最小 Adapter 候选以 R6M 已部署源码为基线。探测证据存 ignored runtime。新契约待确定，尚无需要改写设计的已实测偏差。

文档更新清单：设计、规格 46.5、管理 UI、Adapter/相关 Worker README、操作与客户端说明、验收与索引、progress/roadmap、工作项索引。当前仅登记工作与核查事实，未修改正式能力契约。

隔离探测结果：精确 cjk-r2 镜像、无网络、新 tmpfs Home、保留 Chromium sandbox 的 headless 实测中，窗口由 1280×720 改为 1600×900，固定参数的 screen 始终 1280×720；省略两个 screen 参数后 screen 始终 1920×1080。说明不能靠移除参数实现动态屏幕。`fingerprint=off` 对照读取 headless 虚拟屏幕 800×600，不证明真实桌面自动调整可用，更不授权关闭生产指纹。DPR 均为 1。证据 `infra/sealskin/runtime/r6n-auto-20261001/probe.py`、`probe-result.json`；QA 容器自动清理。该探测仅核查屏幕参数与窗口关系，X11/Selkies 完整 resize、Camoufox、用户客户端仍未测。功能保持进行中，等待用户对屏幕变化含义的选择；未修改运行代码与生产配置。

实现进展：Chromix 候选启动器支持 screen.mode=auto，width/height 为初始窗口尺寸、DPR 固定 1，MAX_RES=3840x2160，禁止 MANUAL 尺寸锁；采用显式持久种子和 CPU/内存/存储默认值、native GPU 策略，避免 public fingerprint 自动注入固定 screen。它是独立环境修订，不声称与固定模式所有指纹 API 完全等价。隔离真实 X11/Selkies 后端四次调整、页面 screen/outer/inner、语言/时区/DPR 和正常退出通过；首轮固定 Xvfb 上限失败及清理回执保留。新目录契约 auto@1/scaling=auto 仅允许 Chromix/X11，Profile 的 resolution_mode 由模板绑定保存并随回退恢复，自动模式拒绝固定缩放偏好；尚未注册 accepted 模板、未部署。管理端与客户端端到端验收仍进行中。

2026-10-01 后续：DEV-096 记录超限请求及输入映射偏差，最终候选 e7e71db14431… 七组真实 Selkies WebSocket 客户端窗口/点击/输入/重连/DPR/超限均通过；当前重跑最终镜像网络/恢复/管理验收。前述“等待用户选择”是早期时点，用户现已明确选择动态 screen。最终运行上限需前后端共同同步，不能仅设置 Xvfb MAX_RES。

收尾复核：用户明确选择真实动态 screen；最终 e7e71db14431… 镜像通过七组客户端、最终 DIRECT/认证代理、入口、创建/回显、关闭拒绝、加密恢复及实际固定/自动回退。10 项 Python 与最小 Adapter 全 test/vet 通过，DEV-096 已修复并部署。最小 Adapter/追加目录上线，生产容器/目录/三者绑定保持，Personal/Work/Chromix 新鲜 healthy。组件、设计/规格、UI、操作、客户端、验收/索引、progress/roadmap 已更新。新增范围仅 Chromix 默认 WebSocket；Camoufox、WebRTC 专项、触屏/多显示器及 Mac 实机未测，作为明确后续范围保留。本次不开始下一计划。

用户后续反馈（2026-10-01）：已切换自动分辨率，使用正常；左侧 UI Scaling 未生效作为 R6O 独立修复。原测试未覆盖此控件，不改写成已经验收。
