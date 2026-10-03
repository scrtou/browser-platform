# Browser Platform

自托管的浏览器 Profile 服务：在 Trilium 中打开固定入口，在 Linux 服务器上运行浏览器，并按 Profile 保留登录数据、代理配置和浏览器环境。

当前采用 Go Profile Adapter、SealSkin、Selkies 与 Docker。1.0 的全新部署、重启恢复及生产切换已通过验收；具体部署、生效范围和待办见 [开发进度](docs/progress.md)。

从 [文档导航](docs/README.md) 开始阅读。

开发前遵循 [工作流程指导](docs/workflow.md)，在 [工作项](docs/work-items/README.md) 记录实施与收尾，发现差异及时登记 [设计偏差](docs/deviations/README.md)。

| 想了解什么 | 文档 |
| --- | --- |
| 为什么开发、解决什么问题 | [开发背景与目标](docs/background.md) |
| 系统如何组成、谁负责什么 | [当前架构与决策](docs/design.md) |
| 已完成什么、当前部署到哪一步 | [开发进度](docs/progress.md) |
| 下一步做什么、怎样算完成 | [开发计划](docs/roadmap.md) |
| 全新安装、初始化管理员 | [1.0部署说明](docs/deployment-v1.md) |
| 开机、检查、停止、故障恢复 | [运维与恢复](docs/operations.md) |
| Trilium 接入、复制粘贴、截图上传 | [客户端使用说明](docs/trilium-client.md) |
| 验收结果与适用范围 | [验收索引](docs/acceptance/README.md) |

全新部署与管理员初始化见 [1.0部署说明](docs/deployment-v1.md)。初始网页账号和浏览器为空；登录管理员后创建浏览器，再将其固定入口加入 Trilium。原 Personal/Work 测试实例已按维护授权清理，不再作为默认入口。

构建与组件配置分别见 [Adapter](adapter/README.md)、[SealSkin](infra/sealskin/README.md)、[生命周期补丁](infra/sealskin/lifecycle/README.md)、[Relay](relay/README.md)、[Firefox Worker](infra/firefox-proxy/README.md) 和 [Camoufox](infra/camoufox/README.md)。
