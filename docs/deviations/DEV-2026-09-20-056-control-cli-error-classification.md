# DEV-2026-09-20-056 · 运维 CLI 把命令拒绝误报为 Adapter 停止

状态：已解决（代码/固定容器回归，未部署生产）。发现日期：2026-09-20。关联工作项：[R6F](../work-items/R6F-2026-09-19-release-combination.md)。

## 预期

通过私有 control socket 执行 `inspect`、`stop`、`reconcile` 或 `resume` 时，CLI 应保留脱敏边界，同时输出稳定、可区分的错误代码；Profile 已完整停止而非休眠时，`resume` 应明确分类为 `PROFILE_NOT_DORMANT`，不能暗示 systemd Adapter 服务已经停止。

## 实际事实

- Personal 完成受控停止和备份后，`-resume-profile personal` 经当前 `0600` control socket 返回失败。
- Adapter systemd 用户服务和 control socket 均保持 active/listening；失败来自 Profile 已是 `stopped`，不满足只恢复既有容器的 dormant 契约。
- CLI 顶层对所有 `run` 错误统一记录消息 `profile adapter stopped`，最终脱敏层只保留错误类型，导致正常的命令拒绝被误读为服务停止；R6F 私有证据和 2026-09-20 补充记录因此曾使用了不准确措辞。

## 处理选择

修复实现而不放宽脱敏：control reply 增加固定错误码，客户端返回带 HTTP 状态和错误码的类型；CLI 命令失败使用独立消息 `profile command failed`，只记录 action、Profile 和白名单错误码，仍不输出后端文本、URL、凭据或任意异常内容。保留旧 reply 的稳定文本到错误码映射，以便新 CLI 对旧运行 Adapter 给出正确分类。

同步更正 R6F Personal 备份记录：原失败只能证明 resume 被拒绝，不能证明 Adapter 服务停止。Personal 已是完整 stopped，恢复必须通过已认证固定入口创建使用原 Home 的新 generation；Work 在 Personal 恢复前保持运行，不进入停机备份。

## 验证与影响

- 已新增 control handler/client 错误码与旧 reply 兼容回归，覆盖 10 类生命周期拒绝和未知后端错误；未知详情不进入响应或日志。
- 最终 safelog 回归确认输出固定 action/Profile/error_code，同时删除任意后端私密详情。
- 固定 Go 1.27 Alpine 容器中 `go test ./...`、`go vet ./...`、`gofmt -l .` 和 `CGO_ENABLED=1 go test -race -p 1 -count=1 ./...` 全部通过。
- 使用新源码临时构建 CLI 连接当前旧 reply 格式的生产 Adapter；`-resume-profile personal` 安全拒绝并输出 `profile command failed`、`PROFILE_NOT_DORMANT` 和 `*control.CommandError`，证明旧 reply 兼容映射有效。命令未创建容器，Personal/Work 状态不变。
- 本修复仍是未部署候选，不自动替换生产 Adapter，不启动 Personal、不停止 Work，也不执行回退。
