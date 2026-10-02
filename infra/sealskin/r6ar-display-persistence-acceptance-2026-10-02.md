# R6AR · 缩放百分比持久化与旧 Work 验收

结果：已部署并收尾。关联 [工作项](../../docs/work-items/R6AR-2026-10-02-display-persistence.md)、[DEV-095](../../docs/deviations/DEV-2026-10-01-095-legacy-display-preference.md)、[DEV-130](../../docs/deviations/DEV-2026-10-02-130-scaling-asset-coverage.md)。

当前 Adapter：`8fb90eb29208ccea7ba235c814b6669470af47ba6c026a5f53c03e9f2cf95393`，基线 R6AM `b9e9832d…`。仅 Adapter 重启；R7G1 控制器、Relay、R6Z1 runner、现有 Worker/Home/Session/目录/凭据保持。运行中二进制、正确 Host 就绪、登录页与保护快照相等均通过。

实现：Profile 保存 `ui_scaling_percent`，0 为客户端默认，100–300、步长 25 为共享百分比。管理页和当前已授权 Session 的远程 UI Scaling 都可保存；刷新/新客户端读取，已打开的其他页面须刷新。当前 Session 不能选择其他 Profile；同源、CSRF、绑定复核和 revision 冲突拒绝通过。固定画面/DPR1 和 auto@1 拒绝非零，换模板清零。旧 Wayland Work 使用原生自动 DPI 路径，不使用固定画面 contain/fill。

## 代码与隔离验证

- 精确 `.2` Adapter 基线 113 文件核验；15 个相关路径增量得到 120 文件候选；[版本化补丁](adapter-patches/r6ar-display-persistence.patch)独立重放后全部摘要相同。开发树原有混合改动保持。
- 候选与开发树完整 Go test/vet 通过；Profile/Access 的缩放与固定显示针对性 race 通过。
- Profile 文件持久重载、并发唯一成功/冲突、非法值/重复字段、管理回显、重置和模板转换、固定/auto@1 拒绝通过。
- 入口未登录、跨 Profile、跨 Origin、错误 CSRF、未知字段、陈旧 revision、失效绑定均拒绝；请求不转发到 Worker。
- 已审核资产：旧原版 `12d75adb…`、native-paste `628d1314…` 与当前自动运行时 `c7a3af93…`。最后一项只放行共享缩放，不扩大固定模式变换。动态布局/输入补丁逐项比对保留，未知资产保持原样。

## 真实显示

独立内网 QA Worker、实际候选 Gateway、真实 Profile 文件和单独 headless 客户端，通过正常登录/交接生成合成显示凭据。没有测试接口连接生产 Home 或 Docker socket。所有截图/详细证据在被忽略的任务运行目录。

| 运行时 | 镜像摘要前缀 | 实测场景 | 结果 |
| --- | --- | --- | --- |
| 旧 Wayland Work / Firefox 155.0.1 | `895907b7cecf` | 8 | PASS |
| Camoufox 152.0 auto@system | `f37c2f809411` | 8 | PASS |
| 原生 Firefox 155.0.1 auto@system | `ae7a4e612f16` | 8 | PASS |
| Chromix 154.0.8037.57 auto@system | `819a22563090` | 6 | PASS |

30 场景覆盖：实际 UI 保存 150%；刷新保留；新 DPR2 客户端仍为 150%；他方 revision 更新为 200% 后旧 UI 被拒绝且当前 DPI 不变；刷新读取 200%；Gateway 进程重启及新 DPR1 客户端读取 200%。前三类还实测重置 0 后 DPR2/DPR1 的各自默认。除专门冲突场景外均验证鼠标聚焦和键盘文字到达远程浏览器，全部无页面 JS 错误。QA 容器/网络已退役，合成 Home 和失败证据保留。

最初 QA 凭据/临时目录/Cookie/网络监听/目录元数据/Wayland autostart 路径问题保留原始失败记录。真实资产白名单缺口按 DEV-130 修复后重新通过。没有把失败次数或健康探针算成通过场景。

## 恢复与限制

128 文件、9,236,617 字节的程序增量已传至独立机器并逐文件核验；归档 SHA256 `e18285878c47cba097b30c5ddc4d4c544f2ecba74a5c47fafa77fff149e0ce3b`。包含精确源码/二进制、来源清单及 R6AQ journald 配置；没有生产身份/Home 数据。远端保留在 `/root/browser-platform-recovery/r6ar-program/`。

回退 R6AM 前，先用新 Adapter 的正常授权入口把所有非零百分比重置为 0，再核对当前 Profile JSON 不含新增字段；旧目录解码器严格拒绝未知字段。只回退程序，不用旧目录/凭据/作业覆盖新数据。R7G 控制器有独立的动态代次退役条件。

新 Mac/Trilium 精确硬件组合未测，原用户“缩放正常”反馈保留原范围。多客户端同时控制不实时同步 DPI；商业供应方自然漂移仍未测，与此项显示验收无关。完整固定版本网络/升级恢复矩阵继续下一工作项。

私有证据根：`infra/sealskin/runtime/r6ar-display-persistence-20261002/`，包含 source-audit、patch-replay、全部 Go/真实显示日志、before/after/deployment 与 program-transfer。
