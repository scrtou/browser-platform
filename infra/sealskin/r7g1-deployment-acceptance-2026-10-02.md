# R7G1 · 动态代理热切换部署验收

日期：2026-10-02 UTC。结论：已通过隔离验收并部署；现有 3 个静态代次、Worker/Guard/Relay、Session、账号、目录、凭据及 R6Z1 runner 保持。用户已授权无商业供应方条件下部署；供应方认证下自然 DNS 漂移为 NOT_TESTED。

## 精确版本和改动

- 控制器：`sha256:33a6d2fcd00502f6df7b8e75a2b3eaa70c0e933077919cbdda5dbe77d5fb7b57`，标签 `browser-platform/sealskin:r7g1-dynamic-20261002`。
- 新建代理 Relay：`sha256:d57f441789051be7d7a3770d66211f680741a5b413ca8c5dcc765b8ec8bd286d`，标签 `browser-platform/profile-relay:guard-v1-f35ff66b6b9f3b9f`。
- Adapter 仍为 R6AM `b9e9832d9c24ed9abf2a4f8fb1d236eb8ba4c2c99562869d8f806d232bfaf288`。

以 `.2` 的实际 97 文件控制器为基线，只修改 api/network_dns/network_runtime 并新增 dynamic_upstream；最终 98 个实际安装文件逐一匹配。R6W 授权、R6J1 有界日志及全部 overlay 保留。Relay 固定 Python 更新为 3.12.15-r0，nftables/setpriv 和基础镜像保持，见 DEV-129。

## 验证

| 范围 | 结果 |
| --- | --- |
| 完整精确控制器源码 | 571 passed；两条上游弃用警告不影响测试 |
| Relay 与 Guard/QA 通道 | Go test/vet 通过，52 项 Python 检查通过 |
| 动态真实集成 | 8 组通过；双 Home 认证 HTTPS、新旧连接、DNS/认证失败、恢复、独立换代、规则双失败阻断及绕过拒绝 |
| 控制器事务恢复 | 4 组通过；三中断点和首次回滚失败后的重试 |
| 并发隔离 | 3 组通过；8 并发启动请求得到唯一代次、monitor/stop 同锁、陈旧 stop 拒绝与 peer 保持 |
| 静态升级/回退 | 4 组通过；当前 R6W 创建静态代次，候选接管不重启容器，静态/动态共存，清理动态后旧版本回退 |
| Secret Store 组合 | 3 组通过；独立只读凭据租约、端点更新保持凭据租约、并发撤销先阻断后清理与重启拒绝 |
| 发布与保护 | Compose 仅 controller image 改动；Adapter 配置仅 proxy_template.relay_image 改动；3 个旧代次重接且仍静态；实际程序/文件、ready 与完整保护比对通过 |
| 清理 | 全部 QA 代次、容器、网络、socket、显示及凭据 tmpfs 清理；合成证据私有保留 |
| 异机恢复增量 | 两镜像 121,003,076 字节完整校验/冷导入，174 个程序文件包 18,612,915 字节独立校验通过 |

集成使用隔离浏览器 Worker 内的真实 HTTPS/TCP 客户端；此次不把它扩充为 GUI 热切换或商业供应方自然漂移实测。当前用户客户端确认不补造新的 R7G 客户端观察。

## 生效和恢复

`compose.dynamic-upstream.json` 是当前控制器增量。新建域名代理策略使用新 Relay 能力；数值 IP 保持静态。既有策略及 DIRECT 默认镜像未修改，既有浏览器不会自动转换成动态代次。若复用已有策略，该策略原有镜像仍决定是否启用；需要动态能力时创建使用新镜像的新策略，正常停止后应用。

回退必须先用新控制器正常清理所有动态代次，核对无 endpoint/pending，再撤销 Compose 增量并恢复 proxy_template 的旧 Relay 默认值，重启 Adapter。保留当前 Home、Session、目录、Secret Store 和操作日志；不得用旧控制器直接接管动态事务。

精确旧基线为 `server-2026.10.02.2`。新恢复增量位于独立机器私有 `browser-platform-recovery/r7g1-images/` 和 `r7g1-program/`；本机忽略目录 `runtime/r7g1-deployment-20261002/` 保留校验、部署/回退和全部测试证据。程序包不含真实身份/Home；不能当作新的生产业务快照。最终统一版本归剩余矩阵后的封存收尾。

[工作项](../../docs/work-items/R7G1-2026-10-02-dynamic-deployment.md) · [剩余工作](../../docs/remaining-work-2026-10-02.md)
