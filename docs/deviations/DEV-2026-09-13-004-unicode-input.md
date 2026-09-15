# DEV-2026-09-13-004 · 输入通道拆分 Unicode 代理对

状态：已解决（2026-09-14，代码与 QA；生产尚未部署新客户端包）。工作项：[R4A](../work-items/R4A-2026-09-13-client-migration-qa.md)。

预期：受支持的文字输入通道保留实际字符；不能将正常显示或剪贴板成功扩展为全部输入字符通过。

事实：真实 Camoufox 的三组客户端尺寸/DPR、15 个坐标目标通过；随后向 Selkies keyboard assist 输入 `camoufox-繁體中文😀`，远程实际仅收到 `camoufox-繁體中文`。固定 Selkies 前端的 `_handleMobileInput`、`_handleTextInput` 和 `_updateCompositionText` 按 UTF-16 code unit 使用 `charCodeAt`，将补充平面字符拆成两个 surrogate keysym。修复后补充平面汉字通过，emoji 仍失败，进一步发现 QA 启动请求错误地将 BCP 47 `zh-TW` 用作 POSIX `LC_ALL`：`xdotool type` 返回 Invalid multi-byte sequence，显式 UTF-8 locale 后相同输入通过。SealSkin 的 `language` 参数须为 `zh_TW.UTF-8`，已有 Camoufox 部署说明使用的正是该值。此前原生剪贴板的 emoji 验收仍有效，但不覆盖此输入通道。

证据：私有 `runtime/r4-client-migration-2026-09-13/client-boundary-v2/`、`client-boundary-v3/`、`unicode-input-failure.json`、`unicode-backend-probe.json`、`unicode-backend-type-probe.json` 和固定摘要的 `frontend-source.js`。

处理：修复固定前端安装器中的字符串迭代与 composition 差异计数，按 Unicode code point 转换 X11 keysym；修正 QA 请求的系统 locale。原环境产物、Selkies 后端、浏览器与 Trilium Core 不改动。继续用原中文加 emoji 条件，并增加补充平面汉字与原生剪贴板回归；Mac 输入法实机验收仍单列。

验收：新代次在正确 POSIX locale 下自动安装新包，`camoufox-繁體中文😀𠮷` 完整输入；组合更新最终为 `KEEP:😀𠮷`，前缀保留。CDP start/update 可信，commit 事件实际为 untrusted，未改写成原生 OS 输入法通过。完整文字复制/截图回归、旧包回退后重装、幂等和篡改拒绝均通过，见 [R4A 验收](../../infra/sealskin/client-migration-acceptance-2026-09-14.md)。

部署：`native-clipboard-c79102f832b141bd` 仅安装到隔离 QA，并准备为候选 Camoufox 应用的只读挂载。生产现有静态客户端和应用定义未更新；目标 Mac 实机及生产切换属于 R4B。旧失败目录与诊断证据保留。
