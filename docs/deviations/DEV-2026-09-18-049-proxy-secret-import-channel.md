# DEV-2026-09-18-049 · 代理凭据导入与策略修订的控制器接口

状态：已解决（候选补丁，未部署）。发现日期：2026-09-18。关联工作项：[R6D](../work-items/R6D-2026-09-18-proxy-drafts.md)。

## 设计预期

[管理面规格](../specs/proxy-environment/management.md#代理配置) 写明面板创建代理草稿时“由 Adapter 调用同一导入路径（tmpfs 0600 输入、只返回引用）”，并由 Adapter 管理面“写入新修订（只追加）”到 `profile-network-policies.json`。[Secret Store 说明](../../infra/sealskin/lifecycle/secret-store.md#配置与导入) 描述的导入路径是控制器容器内的离线 CLI 与 tmpfs 输入文件。

## 实际事实与证据

- Adapter 以独立 systemd 用户服务运行在主机上，Secret Store、主密钥和策略注册表都在控制器容器的 metadata 目录内；Adapter 没有这些文件的挂载，也不应持有主密钥。
- 固定上游加 R5 生命周期补丁只提供 `POST /api/admin/profile-secrets/revoke`，没有导入凭据、追加策略修订或探针的管理员接口（`profile-lifecycle.patch` 的 `secret_runtime.py`、`network_runtime.py`）。
- 让 Adapter 直接写 tmpfs 文件再调用容器内 CLI 需要 Adapter 获得 Docker exec 或共享挂载，违反“Adapter 不直接操作控制器文件、SealSkin 是唯一 Docker 所有者”的边界。

## 影响与处理决定

- 处理方式：修订设计的实现路径，保留契约。第二层 [environment-management.patch](../../infra/sealskin/lifecycle/environment-management.patch) 新增管理员加密路由 `/api/admin/environment-management/`：`proxy-secrets`（调用同一 `FileSecretStore.put`，在凭据锁内写入版本，只返回两个 `secret://` 引用）、`proxy-probe`（见 [DEV-050](DEV-2026-09-18-050-proxy-draft-probe-scope.md)）、`network-policies`（在注册表锁内用控制器 `NetworkPolicy` 模型校验、按控制器规范摘要计算 SHA、只追加；同内容重试返回相同摘要，不同内容同 ID 拒绝；HTTPS 上游 CA 作为 `network-secrets/` 下 0600 独占文件写入）。
- 凭据只出现在 Adapter 表单请求与到控制器的加密请求体中；Adapter 不落盘、不记日志，目录只保存引用与版本号。表单字段在处理后立即清空。
- 对当前交付的影响：Secret Store 的授权、不可覆盖版本、撤销 tombstone 和 Relay 租约行为不变；离线 CLI 导入继续可用。生产控制器未应用该补丁，缺少接口时 Adapter 的草稿创建返回不可用，不会回退到明文文件策略。

## 实施、验证与文档同步

| 材料 | 更新 / 结果 |
| --- | --- |
| 实现 | 控制器 `environment_management.py`、`api.py` 路由注册；Adapter `sealskin` 客户端新增导入/探针/追加/撤销方法，`profile/proxy.go` 草稿流程 |
| 验收与证据 | 控制器 pytest：导入只返回引用且密文不含明文、重复版本 409、非管理员 403、策略追加幂等/不可变/摘要与 `network.digest` 一致、HTTPS CA 私有落盘；Adapter fake 客户端与服务测试。见 [R6D 验收](../../infra/sealskin/proxy-drafts-acceptance-2026-09-18.md) |
| 设计 / 规格 / 组件说明 | [管理面规格](../specs/proxy-environment/management.md#代理配置)、[Secret Store](../../infra/sealskin/lifecycle/secret-store.md)、[生命周期 README](../../infra/sealskin/lifecycle/README.md) 已注明控制器接口路径 |
| 进度 / 计划 / 工作项 | R6D 工作项、进度与计划已更新 |

## 最终复核

规格中的“同一导入路径”按“同一 Store 实现与授权模型、经控制器加密管理员接口”落实；凭据边界、版本不可覆盖与撤销语义保持。补丁只在隔离 checks 镜像验证，生产未部署。
