# DEV-2026-09-14-007 · Relay 凭据读取会丢弃边缘空白

状态：已解决（代码与隔离验证，未部署生产）。发现日期：2026-09-14。关联工作项：[R5A](../work-items/R5A-2026-09-14-proxy-protocols.md)。

## 预期与事实

认证应使用所引用版本的准确凭据。原 [config.go](../../relay/internal/proxy/config.go) 对文件内容执行 `strings.TrimSpace`，会静默改变用户名/密码的首尾空格；`os.ReadFile` 没有大小限制，`os.Stat` 会跟随末级符号链接。事实来自源码，不声称真实生产凭据受影响。

## 处理决定

在增加 Basic 认证前修复读取契约：仅去掉可选的一个 LF/CRLF 文件行尾，保留所有空格；单值文本限制 4096 字节，SOCKS5 再限制为 1–255 字节，HTTP Basic 用户名不得含冒号。拒绝控制字符、末级符号链接、非普通文件、宽权限和超量读取。常规单行文件保持兼容；依赖旧 trim 行为的异常文件需要新版本修正，不能静默继续使用不同字节。

受控 Secret Store、principal 授权、运行时注入和撤销仍由 R5B 交付，本次读取修复不代替 S01–S05。凭据明文和测试证据只放独立私有 QA 目录。

## 验证与收尾

R5A 的 Go 协议测试以真实上游认证校验首尾空格；配置测试覆盖单值字节、LF/CRLF、文件限额/权限/链接拒绝及协议长度。全套测试、race/vet 通过，证据在 `runtime/r5a-proxy-protocols-2026-09-14/relay-tests-v1.log` 与 `relay-race-vet-v1.log`，Relay README 与工作项已同步。没有原地改生产凭据或部署新镜像；Secret Store 的完整条件继续保留给 R5B。
