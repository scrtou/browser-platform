# DEV-2026-09-18-048 · Home 归档控制器 API

状态：已解决（候选补丁，未部署）

## 事实

R6C 需要在确认 Home 没有会话、Worker、网络或启动日志占用后保留 Home 内容并删除浏览器应用。固定的 SealSkin 上游接口只有创建和删除 Home，没有把 Home 移入归档命名空间的 API；Adapter 不能直接操作控制器拥有的 Home 文件。

## 处理

在固定上游 commit `2b13a42483c1dc7d367d5c340437bdc8ecd84bb4` 的生命周期补丁之后增加版本化 [environment-management.patch](../../infra/sealskin/lifecycle/environment-management.patch)。控制器新增 `POST /api/homedirs/{home}/archive`：沿用加密路由、Home 锁和 `inspect_home`，确认资源为空后在 Home 内写入 0600 的无敏感信息清单，再用同一文件系统 `rename` 移到 `.browser-platform-archive/<user>/<archive>`；同一归档请求可按清单重试。Adapter 只调用该接口，不读取或移动真实 Home。

`prepare.py` 对两层补丁逐一执行 `--check`，并把第二层补丁摘要写入构建输入和 manifest。控制器测试覆盖归档移动、清单字段和重复请求；Go fake API 覆盖 Adapter 的调用顺序、占用拒绝与失败重试。生产控制器仍为 candidate-4 所对应版本，没有应用该补丁。

## 影响与边界

缺少该补丁能力时，Adapter 删除操作会在归档步骤失败并保留 `deleting` 状态，不会删除应用或直接清理 Home。DIRECT 主机地址证据、网关镜像能力和 R6F 真实浏览器组合不由本记录证明，继续按 R6C/R6F 条件验证。

## 链接

- 工作项：[R6C](../work-items/R6C-2026-09-18-create-delete-launch.md)
- 规格：[R6 管理面](../specs/proxy-environment/management.md)
- 组件说明：[SealSkin 生命周期](../../infra/sealskin/lifecycle/README.md)
