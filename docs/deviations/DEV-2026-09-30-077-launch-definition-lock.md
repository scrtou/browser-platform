# DEV-2026-09-30-077 · 启动等待生命周期锁时使用旧目录定义

[R7F 工作项](../work-items/R7F-2026-09-23-production-release.md) · [偏差索引](README.md)

状态：已解决（已部署）。发现日期：2026-09-30。

## 预期与事实

网络、模板及迁移变更在同一 Profile 生命周期锁中核对停止状态、写启动门禁并提交目录。`Ensure` 原先在取锁前读取 Record 和 Definition；请求等待锁时，变更操作可能已经写入 updating 或提交新修订，启动随后仍使用旧定义。仅持有写侧生命周期锁不能保证这个读侧契约。

## 决定与验证

修复实现：启动先取得 Profile 生命周期锁，再读取目录、状态、禁用标志和定义，后续 Home/Session/启动副作用保持在同一锁内。确定性等待锁测试覆盖停用、pending 阻断及新定义读取；原运行会话和生产 Home 不作为测试资源。全量 Go test/vet 和 profile race 通过，Adapter 7f4e2a1a… 已限定发布且运行身份保持；证据见 [R7F 本轮验收](../../infra/sealskin/r7f-legacy-migration-acceptance-2026-09-30.md)。
