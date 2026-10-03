# DEV-157 · HTTPS响应头超时截断180秒启动预算

状态：已解决（R6AX范围）。关联 [R6AX](../work-items/R6AX-2026-10-03-v1-release.md)。

修复DEV-156的QA网络隔离后，独立机Firefox冷启动仍在约31秒返回409模糊启动，控制器随后有运行Worker。请求日志没有ERR_NETWORK_CHANGED，Adapter仍未完整等到正常启动响应。源码确认 `access.SessionTransport` 设置30秒 `ResponseHeaderTimeout`；`sealskin.NewClient` 的长请求虽然使用180秒Client预算，却直接共享该Transport，因此仍先被30秒响应头限制截断。此前R6AS测试只缩短了Client总预算，未覆盖生产使用的自定义HTTPS Transport。

选择修复长请求专用Transport：克隆已有标准HTTP Transport并保留TLS/CA/DNS/代理/重定向等安全配置，只让长请求的响应头等待不短于既定180秒总预算；普通查询和显示仍保留原30秒限制。未设置响应头限制或非标准自定义RoundTripper保持其原契约。调用者取消和180秒总预算继续生效，突变不自动重放，未知代次必须reconcile。

增加真实HTTPS延迟响应测试，覆盖生产式自定义Transport、普通查询仍超时、长启动成功、调用者取消/总预算失败及单次请求/幂等键保持；重新构建、全Go回归和独立机三引擎冷启动通过后才能发布。原attempt7事件、409和unknown状态保留，不以延长QA等待掩盖实现超时。

新增真实TLS测试在旧实现上复现延迟启动失败；修复后普通查询保持短超时，长启动/取消/总预算与单次突变均通过，完整Go test/vet通过。新Adapter为 `dd8b34e6f1499629efed17d09209e236cbbc73d860da72941c9b1819f34ba5bc`，待独立冷启动及部署复核；旧日志保留。

attempt11独立机三引擎均完成正常冷启动、显示、实际键盘输入、正常关闭和SQLite历史读回；最新程序成功使用既有180秒预算。服务/主机重启及正式生产切换仍随R6AX推进。

最终核对：R6AX最终包新安装、相同最终程序三引擎输入/关闭、服务与主机重启及保护生产部署已通过；本记录原失败与处理过程保留。具体适用证据见[R6AX最终验收](../../infra/sealskin/r6ax-v1-install-acceptance-2026-10-03.md)。
