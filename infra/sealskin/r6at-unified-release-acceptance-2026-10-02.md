# R6AT · 当前部署版本统一封存验收

状态：PASS，已收尾。工作项：[R6AT](../../docs/work-items/R6AT-2026-10-02-unified-release.md)；[版本与归档摘要](../../docs/releases/server-2026.10.02.3.md)。

发布 `server-2026.10.02.3`，提交 `278c5ea7719f9419aff004909aa0442c8ee36734`；独立分支/附注标签的父提交为 `.2` `f0b84fb409d6f78a6b9a911cc1fbd0457b08424e`。按用户已授权剩余工作统一封存当前程序，未重新部署或推送。

| 检查 | 结果 |
| --- | --- |
| 实际部署身份 | Adapter `63d88d1e…` 及 PID 保持；R7G1 控制器 app 98 文件与冻结清单完全一致；R6Z1 runner 54 文件、目标清单和 journald 摘要保持 |
| 冻结来源 | R6AS Adapter 121 文件、R7G1 controller 126 文件（98 app + 28 测试）、R6Z1 runner、R7G1 Relay 固定构建输入/原二进制、Python wheel 和恢复说明 |
| 标签和归档 | 358 条清单/共 359 源文件，标签逐文件相同；源码和程序归档解包通过，原始 Adapter/Relay 双二进制分别核对 |
| 完整性拒绝 | 篡改、缺失、额外文件、符号链接、错误独立 manifest pin 共 5 类均拒绝 |
| 秘密边界 | 固定输入白名单、实际敏感配置值/SSH 密码精确扫描、私钥及授权 URL 标记扫描通过；两个无效私钥头/单字符单元测试夹具经核对保留，没有真实密钥 |
| 独立机器 | 两归档和解包全部文件通过；16 个固定镜像按完整 ID inspect 可用；仅原停止的 arm64-debian11 容器保持，没有激活生产身份 |
| 生产/Git 保护 | Home/Session/目录/凭据/journal/runner/容器保护快照相同；Adapter PID/就绪和 journald 保持；封存期间原 HEAD/索引及 907 个已有工作区文件保持 |

Docker 默认 image ls 未列出已导入的部分无标签镜像，首次列表断言未通过；改为逐一 inspect 完整 ID 后 16 个镜像全部匹配。未重新导入、删镜像或放宽身份要求，原查询和最终结果均保留。

验证版本边界：R7G1 动态集成、R6AR 显示和 R6AS 矩阵沿用各自实际版本。三引擎9阶段程序矩阵目标为R6AR `8fb90eb2…`；最终R6AS `63d88d1e…` 的超时增量按完整Go回归、两次真实慢启动及后续Firefox DIRECT恢复验证。本项只封存与核对，未宣称重复执行所有功能矩阵。

包内 RECOVERY.md 明确 R6AS→R6AR 程序回退、降到 `.2` 的动态退役/非零缩放复位条件及 secret/display tmpfs、Caddy/Session信任、作业/产物依赖。真实历史Home与当前元数据保持OFFLINE_ONLY，不构成业务时点一致的备份；商业供应方自然漂移/新供应方GUI、无已验收目标的任意浏览器大版本迁移、30天journald自然到期观察保持证据限制。

私有证据：`infra/sealskin/runtime/r6at-unified-release-20261002/`，含 before/after、preflight/postflight、source-input-audit、secret-scan、verifier-audit、release-result、remote-image-inspect、remote-verification、完整源与归档。本轮剩余工作按范围完成；已更新版本、运维、组件/规格入口、验收/工作项索引及进度/路线图/执行表，没有自动启动新的功能范围。
