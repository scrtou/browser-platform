# DEV-156 · 新建浏览器网络导致同主机QA客户端中断

状态：处理中。关联 [R6AX](../work-items/R6AX-2026-10-03-v1-release.md)。

独立机真实入口QA的Chromium客户端最初用 `--network host` 访问仅回环监听的私有TLS入口。新建受管理浏览器创建Docker网络时，客户端收到 `net::ERR_NETWORK_CHANGED`，取消 `/browser/{id}/start` POST，Adapter据实保留unknown/模糊启动记录；控制器随后完成Worker/Relay/Guard创建。attempt6的Camoufox请求事件直接证明该原因，attempt5 Firefox取消属于相同执行环境下的已保留失败，未补造其缺失的网络事件。

Firefox通过运维reconcile核对已有代次后完成显示、键盘输入、正常关闭与SQLite历史读回。不能把一次恢复成功当作首次冷启动已通过。

选择修订QA网络隔离：客户端容器使用独立无网络namespace，经只连接既定回环19443的Unix socket转发TLS字节，证书/SPKI与双域名不变；不共享主机接口变化，也不开放管理端口到公网。保留原失败、状态及网络事件，按实际操作日志reconcile/正常停止已有QA代次，再用原Home重新走冷启动。三引擎新启动/显示/输入/恢复通过后才关闭本偏差，不修改生产生命周期或放宽超时。
