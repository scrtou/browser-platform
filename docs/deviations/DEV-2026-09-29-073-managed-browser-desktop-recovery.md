# DEV-2026-09-29-073 · 模板化浏览器退出后错误引导启动系统 Firefox

状态：处理中。发现日期：2026-09-29。关联工作项：[R7F R7 组合候选、生产发布与目标客户端验收](../work-items/R7F-2026-09-23-production-release.md)。

2026-09-30 16:55 UTC 新观测：“测试”r10 的新鲜健康为 `BROWSER_EXITED`，Worker/显示/代理/Session 均正常；Personal/Work 新鲜 healthy。本轮没有停止或重建该浏览器，用户随后确认“主动关闭过”，本次退出与其操作相符，不认定为新的崩溃；保留当前状态及 Home、core 和运行资源。Trilium 菜单未测条件继续保留，偏差状态不变。

## 设计预期

浏览器运行模板、指纹产物、Home 和显示模板是一组经验收的绑定。浏览器主进程退出后，恢复不得从远程桌面启动另一个未绑定的浏览器；模板化 Profile 应经既有生命周期所有者安全停止原代次，再从固定入口创建新代次，同时保留 Home。

## 实际事实与证据

- 2026-09-29 用户新建的 Camoufox 模板化 Profile 出现窗口消失；Profile 目录记录仍为 `ready`，Worker、Relay 和 Guard 仍在运行，浏览器主进程已退出，健康报告为 `BROWSER_EXITED`。
- Home 中的 ELF core 映射主程序为 `/opt/camoufox/browser/camoufox`，最终信号为 `SIGSEGV`；Docker 记录 `OOMKilled=false`，不是容器内存上限杀死。原始 core 和详细调试输出仅保留在忽略的运行目录，未读取或公开网页数据。
- 容器基础桌面保留 `/usr/share/applications/firefox.desktop`，命令是系统 `/usr/bin/firefox`，不是受管 Camoufox 启动器。
- [`selectRecovery`](../../adapter/internal/profile/health.go) 对所有 `BROWSER_EXITED` 统一提示“右键 → FireFox”，无视 Profile 是否绑定受管浏览器模板；用户按该路径实际启动了系统 Firefox。

## 影响与处理决定

- Profile 记录和 Home 没有丢失；当前故障是浏览器进程崩溃，不是 Profile 被删除。
- 从桌面启动的系统 Firefox 不能证明已应用 Camoufox 指纹、启动校验和绑定产物；不能把它当作受管浏览器恢复成功。
- 处理方式为修复实现：已登记模板的 Profile 改为提示“管理页安全关闭 → 确认资源释放 → 重新打开固定入口”，并明确禁止使用桌面的其他浏览器图标；无模板元数据的历史原生 Firefox 保留旧恢复路径。
- 隐藏或禁用基础桌面 Firefox 需要新 Worker/应用模板修订和真实客户端验收；r10 已完成独立正常 GUI 验收，但在生产发布和目标客户端恢复完成前本偏差保持处理中。
- 本轮诊断不停止、重启或删除用户的新 Profile、Home、Session、core 或网络资源。

## 实施、验证与文档同步

| 材料 | 更新 / 结果 |
| --- | --- |
| 实现 | Adapter 已按模板元数据分流恢复提示，入口冲突错误改为可执行步骤；Worker r10 候选移除系统 Firefox 菜单/启动入口并启用 Openbox 受管模式 |
| 验收与证据 | core 只读诊断、Adapter 两包、2 项桌面单测、静态镜像检查、11 项启动拒绝、两 Home 各 10 次重建及离线恢复通过；独立正常 X11/Selkies GUI、桌面右键无窗口、系统 Firefox 缺失及正常停止通过；9 月 30 日 Mac 用户确认实际右键无 Firefox；Trilium 0.106.0 菜单反馈“无法检查”，仍未验证 |
| 设计 / 规格 / 组件说明 | 已同步 Adapter、Camoufox、设计、运维和客户端边界；验收见 [r10 候选报告](../../infra/camoufox/managed-desktop-recovery-acceptance-2026-09-29.md) |
| 进度 / 计划 / 工作项 | R7F 已记录生产事件，未验证、未部署的修复不记为完成 |

## 最终复核（阶段性）

隔离实现与验收已完成，QA 临时容器、Home 和显示材料已清理。2026-09-29 已完成生产 r10 发布、旧故障代次安全关闭、管理页绑定和固定入口恢复；用户打开后强制健康探测为 `healthy`，浏览器、显示、代理、Session 和报告新鲜度均通过，Home 保留。当时生产实际右键及 Mac/Trilium 用户证据仍缺失；9 月 30 日已补齐下方 Mac 结果，Trilium 随后反馈菜单“无法检查”，因此本偏差保持“处理中”。

2026-09-30 客户端续跑补证：生产 r10 revision 7 的只读检查确认系统 Firefox 启动器与 desktop 文件不存在，默认菜单无 Firefox，受管 Camoufox 进程存在、系统 Firefox 进程为 0。未对生产桌面发送输入，故不代替 Mac 实际右键结果；本偏差仍处理中。见 [页面与 r10 核对](../../infra/sealskin/r7f-client-ui-acceptance-2026-09-30.md)。

同日用户反馈：Google Chrome / macOS 15.1 (24B83)，对“测试”远程桌面右键是否有 Firefox 回复“没有”，补齐本次 Mac 实际菜单观察。Chrome 版本与当前视区未提供；用户当时仅确认能够使用 Trilium，不能据此关闭 Trilium 范围或整个 R7F；其后实际反馈如下。此次仅登记证据，没有停止或重建生产浏览器。

同日 Trilium 0.106.0 补测反馈：前四项页面、下拉和输入正常，桌面右键为“无法检查”。该项保持未验证，不据此推断菜单存在或不存在，也不要求关闭生产浏览器取得证据；偏差状态不变。
