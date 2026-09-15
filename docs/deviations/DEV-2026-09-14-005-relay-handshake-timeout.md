# DEV-2026-09-14-005 · Relay 上游握手没有超时

状态：已解决（代码与隔离验证，未部署生产）。发现日期：2026-09-14。关联工作项：[R5A](../work-items/R5A-2026-09-14-proxy-protocols.md)。

## 设计预期

[规格 45.4/45.6](../specs/proxy-environment/specification.md#454-启动流程与失败处理) 要求依赖失败有明确结果、没有直连兜底；Relay 的 `dial_timeout_seconds` 应限制建立可用上游隧道的等待，不能让沉默端点无限占用连接和 goroutine。

## 实际事实与证据

源码核对：[server.go](../../relay/internal/proxy/server.go) 原 `dialUpstream` 只给 `net.Dialer` 配置超时，TCP 成功后的 greeting、用户名/密码与 SOCKS CONNECT 读写没有 connection deadline。客户端的 deadline 不会中断正在读取上游的 goroutine。当前事实来自源码，未声称生产已发生挂起；回归失败与修复证据保存在独立 R5A runtime。

## 影响与处理决定

修复实现：为 TCP/TLS/认证/CONNECT 使用有界总握手时间，成功后恢复隧道 idle deadline；取消服务时终止连接。新增沉默上游回归、正常/异常协议及并发测试。保留原错误码脱敏与不直连条件。此修复随新镜像交付，不重启生产 Relay 或 Worker。

## 实施、验证与文档同步

| 材料 | 更新 / 结果 |
| --- | --- |
| 实现 | TCP/TLS/认证/CONNECT 共用总超时，取消关闭活动连接；HTTP 头 32 KiB 上限 |
| 验收与证据 | `runtime/r5a-proxy-protocols-2026-09-14/relay-timeout-baseline.log` 保留旧实现失败；`relay-tests-v1.log`、`relay-race-vet-v1.log` 验证修复、沉默端点及取消 |
| 设计 / 规格 / Relay README | 已同步总握手预算及隧道每方向 idle 超时的区别 |
| 进度 / 计划 / 工作项 | R5A 进行中，生产版本保持 |

## 最终复核

失败回归与修复验证均已保留，Go 测试/race/vet 通过，源码与超时契约一致。随 R5A 的新 Relay 交付，生产仍使用原镜像；整体验收及版本见 R5A 记录。
