# Profile Relay

[文档导航](../docs/README.md) · [当前架构](../docs/design.md) · [开发进度](../docs/progress.md) · [运维说明](../docs/operations.md)

这是按 Profile 运行的 SOCKS5 转接器原型。Worker 只连接 Relay 的内部监听地址；Relay 再使用固定的上游 SOCKS5 端点，可选地完成用户名/密码认证和远端域名解析。上游失败时只返回 SOCKS 错误，不会直接连接目标网站。

配置只保存上游地址和凭据文件路径，凭据文件必须是普通文件且权限不允许 group/other 读取。Relay 启动时读入凭据；日志只使用稳定错误码，不输出凭据、目标 URL 或完整连接异常。生产部署应把凭据文件放在 tmpfs/Docker Secret，并让每个 Profile 使用独立 Relay 和网络命名空间。

静态 Personal 基线通过 [Compose overlay](../infra/sealskin/compose.proxy.yml) 运行，当前保留给独立 Camoufox。受管理的新 Personal 会话使用 SealSkin 的 [动态网络生命周期](../infra/sealskin/lifecycle/README.md)：每代独立分配网络、Relay 和 Guard；Guard 先安装 nftables 规则，Worker 再共享其命名空间，主动出站仅能到自己的 Relay TCP 1080。Relay 的长期进程也在安装规则后丢弃全部 capabilities，只连接控制器在分配时解析并冻结的上游 IPv4／端口。

浏览器 DNS／IPv6／STUN／UDP443、代理故障、控制容器重建和独立 Docker daemon 恢复已完成限定范围的 [验收](../infra/sealskin/network-isolation-acceptance-2026-09-13.md)。正式主机重启和公开 DNS 轮换仍待验证。现有 Work／Personal 会话没有迁移，新策略在下一次 Personal 启动时生效。

```bash
cd relay
go test ./...
go build -trimpath -o /tmp/profile-relay ./cmd/profile-relay
/tmp/profile-relay -config relay.json
```

构建最小 `scratch` sidecar 镜像：

```bash
cd relay
PATH=/path/to/go/bin:$PATH ./build-image.sh
```

`build-image.sh` 先使用本机 Go 构建静态二进制，再生成 `browser-platform/profile-relay:relay-v1`。修改协议或安全边界时必须创建新标签并记录镜像 ID。

受管理网络使用包含规则初始化器的镜像：

```bash
python3 relay/build-guarded-image.py --go /path/to/go/bin/go
```

从项目根目录执行，结果写入 `relay/build/guard-image.json`。脚本按 Go 二进制、Guard 源码、Dockerfile 和构建上下文规则生成版本标签，复用经过输入摘要核对的同版本镜像，不覆盖已存在的版本。当前生产引用 `browser-platform/profile-relay:guard-v1-89e6f53c68ef900f`；策略还固定完整 image ID。保留部署镜像的版本标签，避免覆盖唯一标签后旧 image ID 无法再次查找。
