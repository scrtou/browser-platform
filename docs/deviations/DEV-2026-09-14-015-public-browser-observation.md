# DEV-015 · 公开 DNS 浏览器观测工具的剪贴板读取时序

状态：已解决（工具和实际 QA）。关联工作项：[R5C2](../work-items/R5C2-2026-09-14-approved-dns-ttl.md)。

预期：真实 X11 导航在提交前核对完整地址，复制页面结果并保留截图；窗口出现不等于剪贴板数据已经可用。

2026-09-14 16:26 UTC，两个正常 QA 浏览器及其网络已启动，公开 `before` DNS 采样成功。专用驱动在第一次 `Ctrl+C` 后立即读取默认 `STRING`，收到 `target STRING not available` 并终止。随后读取 `UTF8_STRING` 得到精确的测试地址，表明需要等待复制完成，而不是把瞬时不可用判为地址错误。失败证据保留于私有 `public-browser-1/cycle-1/failure.json`，不覆盖或改写为通过。

处理选择：修复验收工具，有限等待 UTF-8 剪贴板内容，仍要求地址和网页 nonce 精确匹配；核对候选 Worker 实际可用的截图方式。保留产品网络策略、浏览器启动与完整公开 TTL 条件。若当前 TTL 窗口不足，保留本轮并用新随机名称重新采样，不拼接过期的缓存证据。

另确认候选 Worker 没有 `scrot`，原驱动未经实际运行便使用了该命令；已改为镜像内已有的 `xwd -root`，保留原始截图，不临时改变 Worker 依赖。

复核：16:28 UTC 两个真实 QA 浏览器在 `cycle-1/before-retry-direct/` 与 `before-retry-proxy/` 均取得 nonce 一致的 HTTP/HTTPS/WS/WSS 四项旧端点结果，并成功保存 XWD 截图。工具偏差已解决。随后 `public-run-1/cached.failed.json` 是独立的公共递归缓存观测失败：部分回答已变新地址、另一个旧回答的 TTL 与首次采样不连续；未改写为通过，后续使用新随机名称和独立证据继续验收。影响文档为工作项、偏差索引、浏览器驱动说明和 R5C2 验收报告。
