# DEV-064 · Work QA 把 Launch Context 当作浏览器导航

状态：已解决（工具修复、R7B 第六轮与清理通过）。日期：2026-09-21。
关联：[R7B](../work-items/R7B-2026-09-21-managed-work-egress.md)。

R7B 第三轮独立 QA 通过 Firefox/Wayland 进程检查后，在公网页面断言处发现浏览器仍为 `about:blank`。同一代次的 DIRECT Relay、Guard、Worker namespace 和经 Relay 的 HTTPS 探针均已通过。原因是测试直接调用 SealSkin `POST /api/launch/url` 后，把请求中的 Launch Context URL 当作生产兼容 Firefox legacy 应用已经完成的页面导航；该应用本身按固定启动命令打开 `about:blank`，真实入口的后续导航语义不属于该直接生命周期调用。

影响仅限新增 R7B QA 编排，没有生产变更，也不表示受管理 DIRECT 失败。第三轮失败代次已按精确 generation 身份正常 Stop，资源归零，证据保留。

决定：保留生产兼容应用定义不变；QA 在确认唯一 Firefox 原生 Wayland 进程后，通过既有本机 BiDi 控制端显式导航到固定公开 HTTPS 测试页，并在有界等待内要求 BiDi 端口、导航命令与 `document.readyState` 完成，再执行 DNS/TLS/页面、失效关闭和持久化断言。第五轮首代次已完成真实公开页面与网关故障关闭，第二代次暴露进程出现早于 BiDi 端口监听的正常就绪竞态，已纳入同一有界等待；失败代次正常 Stop 且资源归零。完整重跑通过后标为已解决。

最终结果：第六轮两个 generation 的 BiDi 就绪与显式导航均在界限内完成，页面、故障和三类存储恢复全部通过；最终资源清零。
