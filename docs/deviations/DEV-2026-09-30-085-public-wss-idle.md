# DEV-085 · 公网 WSS 验收连接空闲超时

状态：已解决。工作项：[R7G](../work-items/R7G-2026-09-27-dynamic-upstream-hot-switch.md)。

预期：检查同一条 WSS 在真实公网 DNS 切换前后仍可回显。实际：首轮两个 Home 的认证 HTTPS/WSS 通过，切换后旧连接 BrokenPipe。端点 `pipe()` 明确限制 15 秒空闲；运行器采集证据与等待 DNS 期间不发任何报文，超出夹具空闲限制。

处理：修复 QA Worker，在等待命令时每 3 秒通过原 WSS 发送并核对 nonce 回显；不重连、不修改产品、端点超时或 DNS 条件。失败证据保留在私有 `runtime/r7g-public-authorized-20260930/dynamic-failed-idle/`；补回显后重新执行完整公网往返，结果待验证。

首次保活重试暴露 QA stdin 的 TextIO 预读与 select 不一致，导致已缓冲命令没有及时处理。改为有界逐字节读取，select 和命令消费使用同一描述符；失败单独保留，继续真实重跑。

最终验证：三组真实公网往返检查通过，外部 UDP/TCP 可达，临时规则精确回收并核对原链一致，QA 和远端资源清零、生产保持。详见[公网验收](../../infra/sealskin/r7g-public-acceptance-2026-09-30.md)。原防火墙持久化配置未调整，未来复用 QA DNS 必须再次核对当前状态。
