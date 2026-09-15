# R4A · 客户端边界与 Camoufox 隔离迁移验收

状态：已收尾（代码、Linux 隔离验收与迁移准备；未部署生产候选）。开始日期：2026-09-13，收尾日期：2026-09-14。

## 目标与范围

用户要求按计划完成项目至可发布。本项承接 [R4](../roadmap.md#r4)，前置 [R3](R3-2026-09-13-lifecycle-protection.md) 已收尾。实施前将 R4 分为两部分：先由 R4A 完成当前 Linux 主机可隔离交付的客户端矩阵、非文本可行性、Camoufox 受管理网络与迁移准备；再由 R4B 完成目标 Mac/Trilium 实机验收及实际入口切换。父计划全部完成条件仍保留，R4A 通过不代表 R4 或版本发布通过。

本项完成条件：

1. 建立客户端矩阵和可重复的观测页面/步骤，分别记录显示比例、输入法、screen/DPR、坐标、导航、标签页、断线重连、Files、大文本和异常复制；历史用户反馈只覆盖原范围。
2. 在固定 Electron/WebView 权限模型下验证反向图片和其他格式的可行性，明确格式、大小、权限和交互限制，再决定交付路径；合成事件和额外权限不能证明目标客户端通过。
3. 独立 Camoufox 应用支持当前受管理 generation 网络，保留冻结产物、独立 Home 和 SealSkin 生命周期所有权；隔离验证真实 Camoufox 的显示/输入/环境、网络故障与停止重建。
4. 提供核对新旧 Home、应用、环境产物、网络修订和运行绑定的切换/回退准备；实际生产切换须待 R4B 通过，保留原 Firefox Home。
5. 写入有范围的验收报告、清理 QA、更新文档；实机和维护条件明确留在父计划。

验证环境：Debian 12、独立 QA 控制器/用户/Home/网络、Chromium 151 Linux、Electron 43.4.0 权限探针。目标仍为 Trilium 0.105.0 / macOS Sequoia 15.1，工具不能代替该客户端操作。生产 Work/Personal 不退出、不重建、不切换。

## 阅读与代码核对

| 入口 / 材料 | 事实 |
| --- | --- |
| 文档导航、进度、计划、流程、设计、代理环境规格 | R1/R3 已收尾；R2 有管理员和维护窗口条件；E05、46.5/46.6、MVP 与 R4 要求保留 |
| [客户端说明](../trilium-client.md)、[反向复制验收](../../infra/sealskin/native-copy-acceptance-2026-09-13.md) | 文字/截图主流程已有用户反馈，细项、反向图片和 Camoufox 目标客户端仍缺证据 |
| [剪贴板桥接](../../infra/sealskin/screenshot-paste.js) → [安装器](../../infra/sealskin/enable-screenshot-paste.py) → 客户端 QA | copy 只写 text/plain；图片只实现本机到远程；远程右键复制不触发本机事件 |
| [应用准备器](../../infra/camoufox/prepare-sealskin.py) → environment.py → SealSkin runtime | 只支持静态 internal 网络；产物/报告/镜像已固定；动态网络继续由 SealSkin 分配 |
| [网络 QA](../../infra/sealskin/lifecycle/prepare-network-qa.py)、[浏览器 QA](../../infra/sealskin/checks/prepare-network-browser.py) | 可复用隔离控制器与 Docker API 范围限制；应用/调试入口只适用 Firefox，须独立验证 Camoufox |
| 工作区 / 生产 | 保留已有未提交 R1/R2/R3 改动；只读 Docker 核对为控制器、静态 Relay 和两个原 Worker，无运行中 QA |

## 实施与偏差

已实现受管理网络和客户端包引用校验、正常桌面 QA 工具、观测页/矩阵、非文本探针、只读迁移候选与回退配置生成。客户端包内容命名且不覆盖旧目录。抓包方向的 [DEV-003](../deviations/DEV-2026-09-13-003-packet-direction.md)、Unicode 与 QA 系统 locale 的 [DEV-004](../deviations/DEV-2026-09-13-004-unicode-input.md) 已修复并通过隔离回归；没有修改 Selkies 后端或冻结环境产物。

清理工具补充了仅使用 SealSkin API、未启动 QA Adapter 的路径：缺少 PID 文件时先核对无对应进程，再清理其余已确认归属的空环境。组件说明中落后的健康版摘要、132 项测试和已完成待办已按当前 lifecycle-v2 的真实记录修正。新包仅 QA 使用，实际生产切换仍留 R4B。

## 验收复核

| 原要求 | 证据 | 结果 |
| --- | --- | --- |
| 客户端矩阵与 E05 | [矩阵](../client-matrix.md)、`client-boundary-v6`、新包完整 copy/paste 回归 | R4A Linux 范围通过；Mac 原生输入法/Finder 未测，未扩大 E05 结论 |
| 非文本能力/权限 | Electron 43.4.0 权限/格式探针 | 评估完成；反向仅纯文本，HTML/图片/RTF/文件未交付，实际 OS sandbox 未测 |
| Camoufox Home / 网络 / 故障 / 重建 | `network-v2` 11 项、`rebuild-v1` | 正常冻结 Camoufox + Guard 通过；停止重建保留 Cookie/LocalStorage/IndexedDB、环境与资源限制 |
| 切换/回退准备与绑定核对 | `migration-preparation-v2`、8 项准备器测试 | 候选生成与当前实际绑定核对通过；未执行生产切换 |
| 目标客户端 / 生产切换 | R4B | 待外部条件，Linux QA 不能代替 |

公开证据见 [R4A 验收](../../infra/sealskin/client-migration-acceptance-2026-09-14.md)。QA 全部清理；原生产 4 个容器和配置/状态/应用定义摘要一致。安装器的升级、幂等、旧包回退后再升级、未知/篡改拒绝均通过；23 个 Python 文件语法检查与 `git diff --check` 通过。

## 文档与收尾

- [x] 核对原需求、父计划、设计、实现及验收。
- [x] 更新客户端矩阵、操作说明与非文本限制。
- [x] 更新 Camoufox/SealSkin 说明、设计/规格及运维迁移步骤。
- [x] 更新验收索引、偏差、进度、计划和工作项索引。
- [x] 核对 QA 清理、原会话保留、回滚、链接和 git diff --check。

收尾结论：R4A 约定范围已完成。30 份变更 Markdown 的 502 个本地链接/锚点检查通过；候选和回退配置可由当前 Adapter 加载并只读检查原绑定。R4B 实机/切换条件保留，完整 R4 和发布仍未通过。下一步登记 R4B 的外部条件，在等待期间可推进独立的 R5 服务端范围。
