# R6J1 日志专用生产部署验收 · 2026-10-01

结果：本次生产日志维护通过。用户明确授权正常停止、备份并重建现有浏览器，使日志限额立即生效。[工作项](../../docs/work-items/R6J1-2026-10-01-log-deployment.md)已收尾；客户端画面未在本轮复测，不扩大为完整 R7F/R7G 或整机灾备完成。

## 版本与范围

生产控制器：`sha256:ad21dd6de070fce88e59a6c32fd213c017fcb587dffd3cac907693cb7b3b6525`，本机标签 `browser-platform/sealskin:r6j1-log-only-20261001`。基线为原生产 `sha256:bfcd878f693578b65d2911015aedd3a6a79cc25f20619c0c36525f8e19dd90e3`。

完整应用由 96 个文件变为 97 个：仅修改 network_runtime.py、providers/docker_provider.py，新增 bounded_logs.py；其余内容和原文件/目录权限逐项匹配。未含 R7G 动态上游代码。Adapter 保持 `7f4e2a1aee6c79de904e19b2e40c2c69c6ec39152fbc0ff13798db6ef1c49635`，未发布 R6I。

所有新建 Worker、Relay、Guard、临时启动探测采用 json-file / 每文件 10 MiB / 最多 3 文件 / compress=true；应用 overrides 无法取消。11 个当前生产容器的实际 HostConfig 均匹配：控制器、旧静态 Relay、三个 Home 各自的 Worker/Relay/Guard。轮换按大小，不承诺按天删除或文件系统硬配额；共享 journald 预算仍属后续审计。

## 验证与维护

- 日志专用源码在相匹配的静态控制器夹具上 **550 passed，2 项依赖弃用提示**；初轮漏异步模式的失败保留，补齐 asyncio-mode=auto 后重跑。
- 实际隔离 Worker/Relay/Guard/probe 创建事件均观察到限额，刻意设置的应用 `log_config=none` 被平台覆盖；HTTPS 与禁止直连通过。
- 原 CLI 无新代次 start。一次性工具从封存 R7F 源码准备，只增加离线维护分支，使用现有 service lock、Inspect、Ensure、Stop。第二个状态持有者被拒绝及正常启停均通过 QA。工具未安装为生产 Adapter。
- 首个镜像目录权限错误在 QA 发现，逐文件 COPY 修复后核对全部内容/权限并重新运行；[DEV-087](../../docs/deviations/DEV-2026-10-01-087-log-candidate-directory-mode.md)已解决。旧 QA Worker 不具备显示认证能力的问题通过使用已有兼容镜像修正，保留失败及正常清理记录。
- 备份时原 Adapter 二进制临时监听另一私有 loopback 端口，保留账号、认证及状态路径，避免公开入口重开待备份 Home。三个 Home 均正常停止、核实全部资源为零且无挂载后创建 age 密文；verify 和独立 restore 后比对原 Home 的内容、权限与链接。恢复副本未激活。

| Home | 独立恢复比对条目 | 重建后状态 |
| --- | ---: | --- |
| Work | 5,920 | healthy，浏览器/显示正常，受管理 DIRECT 与 HTTPS/绕过拒绝通过 |
| Personal | 1,359 | healthy，浏览器/显示正常，原 tw r1、HTTPS/绕过拒绝通过 |
| 测试 | 1,541 | 资源正常重建；随后以正常窗口关闭流程恢复用户意图，BROWSER_EXITED，显示/网络仍通过 |

上述数字仅为 Home 条目，不是密文归档中包含配置/密钥等材料后的总条目数。“测试”来自动态目录，备份的私有配置副本补充其精确 id/app/Home；真实配置未修改。

控制器与静态 Relay 的 Compose 仅改变控制器 image 和两项 logging；原环境变量、挂载、端口、重启策略与实际容器匹配。三个 Home 的 operation/Session/容器均为新代次，Home 路径、Worker 镜像、应用、网络策略、Profile 修订、目录/账号/配置摘要保持。公开固定入口已恢复，监控 timer 保持启用；维护期间的本机异常/恢复历史保留。

## 证据与恢复

私有材料位于被忽略的 `infra/sealskin/runtime/r6j1-log-deployment-20261001/`：源码前后摘要、installed-audit、550 项测试、真实 QA、Compose 变更核对、维护工具和日志、三份密文/回执/独立恢复比对、部署后健康/网络/实际 HostConfig、验收与恢复说明。QA 容器、网络、进程和临时密钥/tmpfs 已清理。

原生产镜像及精确原 Compose 链保留，回退只操作匹配服务和正常生命周期；不得回放旧账号、Home 或共享 journal。旧控制器不为后续新建容器设置限额，回退须明确记录生效范围。历史 R7F 352 文件包仍为 2026-09-30 快照，本次增量材料与其共同定位当前版本；两者均依赖本机镜像和独立 age 密钥，不能宣称异机整机恢复已通过。
