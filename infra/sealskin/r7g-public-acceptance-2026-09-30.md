# R7G · 受控公网动态端点往返验收

日期：2026-09-30 UTC。结论：三组真实公网检查通过，生产快照保持，所有本轮临时资源已清理。范围是两个隔离 Home 的公共递归 DNS、认证 SOCKS5、Worker 内 HTTPS/WSS；不代表商业供应方自然漂移、GUI 或生产部署验收。

控制器 `sha256:37345e2fa5d92379719ffb8398795fb12d115d76e0f583df361e35db8793130a`、Relay `sha256:9d3928f045dd95a0eb41d3a280f388b8b11dca82c4619fad6eb56fc36f27db4f`、Worker `sha256:895907b7cecf793db5b5b108e9a9ac371d0d381833e729d0b5cc16f8eee8e356`。产品候选沿用已通过 557 项控制器测试的版本，没有改动产品代码。

| 场景 | 实测结果 |
| --- | --- |
| 公网前置 | 新随机 DNS 名称、独立凭据和短期 CA；两台外部机器查询权威 UDP/TCP 均返回成功；本地端点协议检查通过 |
| 双 Home 初始连接 | 通过公共递归 1.1.1.1 解析引导地址，认证 SOCKS5 到真实公网 HTTPS/WSS；两个 endpoint lease 不同，revision 1 |
| A→B | 权威更新、真实 monitor 切到 B / revision 2；新 HTTPS 的 socket 来源为 B；原 WSS nonce 继续回显，Worker/Session 身份不变；两个 Home 四类绕过均拒绝，实际 nft 仅放行 B |
| B→A | monitor 返回 A / revision 3；新连接来源恢复 A，原 WSS 继续回显；两 Home 绕过仍拒绝，实际 nft 仅放行 A |
| 清理 | 正常生命周期清零 QA 代次、容器、网络和显示 tmpfs；仅删除本轮 DNS 名称并递增 SOA，权威恢复原停止状态；两个远端进程正常停止并精确 purge；本地临时凭据、私钥和归档删除 |
| 主机与生产保持 | 用户明确允许的 eth0 → 23.19.231.152 UDP/TCP 53 两条临时规则按注释/地址/协议/handle 核对后删除；前后链一致（忽略计数）；生产配置摘要、Profile 记录、容器身份/镜像/启动时间一致 |

首轮旧 WSS 失败：夹具隧道限制 15 秒空闲，运行器等待 DNS 时未保活。第二轮发现 TextIO 预读与 select 的命令读取不一致。两轮完整失败证据分别保留；最终 Worker 每 3 秒在同一连接发送并验证 nonce 回显，输入改为有界描述符读取，不重连、不延长端点 120 秒生命周期、不调整产品或 DNS 成功标准。见 [DEV-085](../../docs/deviations/DEV-2026-09-30-085-public-wss-idle.md)。最终三组全部通过，独立管道/保活回归与 5 项 zone 所有权测试通过。

入口：[公网运行器](checks/check-dynamic-public.py)、[Worker 客户端](checks/dynamic-public-worker.py)。私有证据根 `runtime/r7g-public-authorized-20260930/`，含 `dynamic/summary.json`、三阶段 journal/nft、来源 nonce、外部 UDP/TCP 回执、两轮失败、远端停止/删除、精确规则与 `final-status.json`。未公开凭据、私钥或带授权参数的 Session URL。

R7G 仍需商业供应方自然漂移认证及最终发布材料收束；客户端按用户要求暂缓。受控公网通过不改变生产部署边界，也不代表容量、监控、灾备、Chromium 等后续计划完成。
