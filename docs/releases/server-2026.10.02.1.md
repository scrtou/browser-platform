# server-2026.10.02.1

2026-10-02本地服务器版本已封存。提交`c08d19381c3eab5cbed15442245385c909f51de1`，分支`release/server-2026.10.02.1`，附注标签`server-2026.10.02.1`。这是独立的已部署源码树，未把开发工作树提交或推送，也没有再次部署服务。

包含统一侧栏/列表/弹窗与页签、已验收引擎指纹联动、已有代理选择、引用删除保护、统一密码确认及4字节密码策略。容量由机器CPU/内存/磁盘自动计算，并保留覆盖值与实时内存保护；已有会话保持。详见[容量策略](../capacity-policy.md)。

| 组件 | 发布身份 |
| --- | --- |
| Adapter | `b813f00bd6a4c07d18462840c8fe2fc3845e46a422f210dcea97c27de7f41c4b`，R6AI完整冻结源码 |
| 控制器 | `sha256:1d93d6b8a92e7d431a603d4f2778b92aa2e91e8943df25c73f49f9013ef8a40e`，R6W含R6J1日志限制的实际97文件 |
| 执行器 | R6Z1窗口修复冻结源；完整摘要和14个当前镜像引用见[发布清单](server-2026.10.02.1.json) |

源码树296文件含逐文件清单；清单SHA-256 `98d0d974c05fec0ce68c1341bbd49ce1b465c7463d2ff46b5240139e8f18cc5e`。R6AI Go/test/vet/race、R6AJ本机自动回归通过；R6AK另对实际部署控制器源码重跑554项通过，修正[DEV-126](../deviations/DEV-2026-10-02-126-controller-test-source-provenance.md)所述旧测试目录差异。完整验收见[R6AK](../../infra/sealskin/r6ak-release-acceptance-2026-10-02.md)。

本机私有运行目录`infra/sealskin/runtime/r6ak-release-20261002/artifacts/`保留源码包和Linux amd64服务器包；后者附原始Adapter二进制。两包均已解包并验证源码、二进制摘要。

| 文件 | SHA-256 |
| --- | --- |
| `browser-platform-server-2026.10.02.1-source.tar.gz` | `7c300a25b481589df72b837150f491feec44a7b1e35217b921163097593b1477` |
| `browser-platform-server-2026.10.02.1-linux-amd64.tar.gz` | `c2dd07249c861bbf23d6edad6d23ac76c42a3871c22007689d4f9b76387d97f1` |

只读查看版本：`git show server-2026.10.02.1:release.json`；导出源码：`git archive server-2026.10.02.1`。解包后运行`python3 verify-release.py`，服务器包再加`--binary bin/profile-adapter`。原始Go二进制含旧工作树VCS元数据，在新标签重编译不保证相同二进制摘要；原始二进制与源码清单分别核对。

源码标签和包都不包含真实Home、账号/凭据、Cookie、私钥、Session URL、作业产物和Docker镜像层。私有依赖盘点不是业务一致性备份。原R7F/R6K材料继续保留；当前数据的一致性备份、离机密钥、完整镜像闭包、Mac/Trilium精确矩阵、商业供应方DNS漂移与异机冷恢复仍属原计划。R7G未发布改动不在此版本内。

包内RECOVERY.md说明成对回退Adapter/配置、R6W授权兼容性和异机前置；不得用旧账号/目录/journal/Home覆盖当前数据来做程序回退。
