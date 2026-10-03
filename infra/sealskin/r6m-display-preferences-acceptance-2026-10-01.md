# R6M · 指纹引擎信息与显示偏好 · 2026-10-01

状态：固定模板范围的代码、隔离回归及最小生产部署通过；旧 Work 自动分辨率路径支持保留后续，目标客户端实机反馈未提供。

## 最终行为

- 浏览器/指纹选项显示引擎及目录绑定版本；编辑中的引擎/版本选择仍受 accepted 三元组合、同 Home 引擎边界及停止门禁约束，不是任意 UA 或二进制版本选择。
- 自定义指纹作业明确显示 Camoufox / 152.0（目录绑定版本）；这是当前固定执行器支持的目标。提交其他引擎/版本拒绝，不伪装支持 Chromix 自定义生成；固定 Chromix 模板仍可正常选择。执行器实际发布版本和镜像锁保持原值。
- `display_preference` 在 Profile 目录随 revision 原子保存，空值继承旧行为，`contain` 保持比例，`fill` 铺满。运行时可保存，刷新远程显示页后各客户端按同一 Profile 设置读取。不更改 screen/DPR、网络、Home、种子或 Worker。
- Session 授权和当前绑定检查之后，仅对两份精确摘要匹配的已安装 Selkies JS 变换固定画面几何；WebRTC/WebSocket 指针与分辨率命令代码保持。清除相关缓存校验和长度并保持 no-store，不使用 URL 参数或客户端存储决定偏好。
- 旧 Work 未登记固定显示模板，使用 Wayland 自动分辨率；其偏好控件明确提示暂不支持，服务端拒绝非空设置。见 [DEV-095](../../docs/deviations/DEV-2026-10-01-095-legacy-display-preference.md)。其他未知前端摘要也不应用变换。

## 验证及限制

最小生产源码完整 Go tests/vet 通过。专项覆盖持久化/重新加载、非法值、陈旧 revision、身份/无停止副作用、行级回显与表单保存、非法生成引擎拒绝、不同 Profile 隔离、无认证上下文和未知脚本不变换。当前仓库对应专项通过。

两份实际已安装 JS 的摘要校验和两种模式输出通过，保留原始文件及变换后文件。独立无网络 Chromium 执行相同固定几何片段，在 1280×800、390×844、1600×600 三视区、两传输路径、两模式共 12 组验证实际布局及三个点击坐标；窄屏截图保留。此项是实际浏览器几何夹具，不等同完整远程流/用户 Mac 端到端验证。生产 Session 的既有授权回归保持，未向生产注入 QA 账号或调试端口。

生产 Adapter `ec3d4d73cd8195bc082129ce825af205b0d3401b82be798f2e9e39f3c0130a4e` 已部署，配置/模板目录/Profile 目录摘要和全部运行容器 ID/启动时间保持；服务 active/readiness 200。首次发布后补充 legacy 提交/展示限制，第二次发布前没有用户保存新偏好，两次部署材料分别保留。生产浏览器未重建。

私有证据位于 `runtime/r6m-display-20261001/`，包含 source-review、diffs、assets、pinned_live_test.go.txt、geometry/geometry-result.json、两次发布记录、回退二进制、健康和 manifest。用户尚未反馈新偏好的目标客户端视觉/坐标结果，不能标记为已实机验收。

## 回退

未保存新字段前可精确恢复旧二进制；用户保存 display_preference 后，旧版严格目录解析不兼容，不能直接回退。优先使用支持新字段的修复版本；必要时受控备份并导出偏好、仅移除新增字段后再回退，保留其他用户改动。变换未知资产时保持原客户端，不能扩大摘要白名单跳过验收。

[工作项](../../docs/work-items/R6M-2026-10-01-environment-display-preferences.md)

最终只读健康：Personal、Work、Chromix 均新鲜 healthy（stale=false）。QA 几何容器已自动清理。
