# R6C 新增/删除浏览器、Home 归档与 launch plan 验收

日期：2026-09-18（UTC）

本报告覆盖 R6 管理面的第 3 步候选代码。生产 Adapter 仍为 candidate-4，未替换二进制、账号表、控制器、Caddy、真实 Home 或正在运行的 Session。详细脱敏结果保存在被忽略的 [R6C 私有结果](runtime/r6c-create-delete-2026-09-18/result.json)。

## 实现范围

- Profile 目录增加 `creating`、`ready`、`deleting`、`deleted` 状态；创建按操作者和幂等键派生固定 Profile、Home 与应用 ID，接受目录中 `status=accepted`、`source=frozen`、完整摘要和固定镜像的环境产物，并把不可变网络策略引用写入应用模板。
- 管理员客户端与启动客户端分离。管理员身份只用于应用安装/删除；Home 创建仍经生命周期客户端，Home 归档经控制器加密端点。创建失败保留 `creating` 可重试，删除复用 verified Stop 并在 resources/records/workers 清空后归档 Home、删除应用、撤销状态绑定，目录记录保留为审计。
- 固定入口为登录账号签发 90 秒、按 Profile 修订和一次性消费的 launch plan；跨账号、跨 Profile、过期、重复使用和修订漂移均拒绝。
- 固定上游没有 Home 归档接口，新增第二层 [environment-management.patch](lifecycle/environment-management.patch)。控制器在 Home 锁内写入 0600 脱敏清单后原子移动到归档命名空间，Adapter 不直接访问 Home 文件。该差异见 [DEV-048](../../docs/deviations/DEV-2026-09-18-048-home-archive-controller-api.md)。

## 隔离验证

在 `golang:1.27-alpine` 的只读源码挂载和独立 Go 缓存中执行：

```text
go test -count=1 ./...                 9 packages; 234 passed, 0 failed, 0 skipped
go vet ./...                           PASS
gofmt -l adapter/**/*.go               no output
go test -race -p 1 -count=1 ./...      PASS (9 packages)
```

Go 测试覆盖环境目录权限与尾随数据、固定应用模板、创建幂等/失败重试、删除前异属运行时拒绝、归档和应用删除顺序、目录审计状态、管理面表单/目录 JSON，以及 launch plan 的账号/修订/过期/单次约束。

控制器补丁在固定 R5D 测试树上以无网络的 SealSkin checks 镜像验证：`git apply --check`、Python `py_compile` 和 `pytest -q -o asyncio_mode=auto tests/test_home_archive.py` 均通过（1 passed）。测试创建临时 Home，确认资源为空后移动目录、写入清单，并用相同请求完成幂等重试；未挂载 Docker socket 或真实存储。

## 未覆盖与后续

本项没有验证生产 DIRECT 的主机 IPv4 证据、网关镜像和控制器能力；也没有实施 R6D 代理草稿/探针、R6E 自定义指纹作业或 R6F 真实客户端/回退组合。控制器第二层补丁尚未部署，因此生产删除路径没有变化。缺少该补丁时 Adapter 删除会在归档步骤停止并保留 `deleting`，不会直接清除 Home。

R6C 可收尾为未部署候选；下一计划项为 R6D。任何生产部署仍须等待 R6F 组合 QA、DIRECT 前置和明确维护授权。
