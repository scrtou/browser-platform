# 客户端验收矩阵

[客户端操作](trilium-client.md) · [R4A 验收](../infra/sealskin/client-migration-acceptance-2026-09-14.md) · [开发计划](roadmap.md#r4)

本矩阵截至 2026-09-14。目标为 Trilium 0.105.0 / macOS Sequoia 15.1；用户当前版本、显示缩放与输入法名称仍待确认。历史反馈仅覆盖原 Firefox 的主流程，不能作为 Camoufox 或所有边界场景的实机证明。

| 场景 | Linux Chromium 151 + QA Camoufox | 目标 Mac / Trilium |
| --- | --- | --- |
| 固定入口与画面 | QA HTTPS Session 与真实串流通过 | 原 Firefox 主流程已确认；Camoufox 未测 |
| 尺寸、DPR、点击坐标 | 1920×1080/1、1280×720/1、1000×760/2；15 个可信点击通过，远程 screen/DPR 不变 | 缩放主流程已确认；具体缩放、screen/DPR、坐标未测 |
| 中文、emoji、补充平面汉字 | keyboard assist 完整输入通过 | 原 Firefox 中文主流程已确认；输入法名称、候选/取消/补充平面字符未测 |
| composition 更新 | CDP start/update 可信，commit 标记 untrusted；内容与前缀完整 | 原生输入法未测，Linux 结果不替代 |
| 后退/前进、标签页、滚动 | 独立分项通过 | 原 Firefox 滚动反馈已确认；其余分项和 Camoufox 未测 |
| 断线恢复 | WebSocket 中断后手动重载、离线重载后恢复均通过，Worker/数据不变 | 普通恢复会话已确认；这两种故障未测 |
| Files 原生选择 | Linux 原生文件选择框，自动选择后真实 Home 校验通过 | 原生选择未测 |
| 文件拖放 | 可信 CDP 文件拖放、Home 校验通过 | Finder 拖放未测 |
| 本机→远程文字/截图 | 25 MiB 限制；PNG 分块、像素与取消/权限回归通过 | 原 Firefox 主流程已确认；Camoufox 与异常分项未测 |
| 远程→本机文字 | 中文/emoji、1,200,015 字节及同值/延迟/Edit/焦点/断线回归通过；25 MiB 限制 | 原 Firefox 主流程已确认；大文本/异常分项与 Camoufox 未测 |
| 远程→本机图片、富文本、RTF、文件 | 当前桥接不支持；Electron 权限探针只证明所测 API/编码路径的结果 | 不支持；没有实机可行性证明 |
| 自动剪贴板 API | 被测 origin read/write 均 denied，实际 NotAllowedError | Trilium 原权限限制保留 |
| 健康恢复提示页 | R1 隔离验证；本项未故障操作生产浏览器 | 原 Firefox 无故障入口已确认；提示页操作未测 |

## 实机记录方法

使用专用 QA Home 与短期测试会话。由运维准备 [观测页面](../infra/sealskin/checks/client-fixture.html)，页面只写测试 nonce；不在公开报告保存真实 Cookie、登录内容或授权 Session URL。

1. 记录 Trilium、Electron、macOS 版本，显示器型号/缩放选项、Trilium 窗口大小、输入法名称和键盘布局。
2. 在 QA 页面按当前尺寸点击五个按钮，再改变窗口和系统显示缩放重复；用页面「复制验收资料（F9）」保存 screen、DPR、outer/inner 和坐标报告。
3. 用实际输入法输入 `繁體中文😀𠮷`，操作候选、替换、取消；确认前后已有文字未丢失。分别验证后退/前进、新建/切换/关闭测试标签页与滚动。
4. 断开客户端网络后恢复并重载，记录提示、恢复操作和数据。不要停止生产 Worker 或重启主机来代替该项。
5. 在 Mac 选择测试 PNG 并从 Finder 拖入，运维核对远程 QA Home 的摘要。测试原生文字/截图、远程文字大文本和 Copy 菜单；记录同值、迟到、焦点变化与取消表现。
6. 在 QA 会话验证浏览器退出、代理故障的恢复提示，按实际结果填写通过/失败/不支持/未测。只在适用分项通过后进入生产切换步骤。

记录至少包含：日期、客户端/服务端版本、QA Home/环境修订、每项操作和结果、观测报告摘要、未测项目及原因。R4B 的维护与真实站点登录证据另行登记；本表不授权停止真实会话。
