# server-2026.10.02.3

2026-10-02 已封存并完成独立机器归档验证。发布提交 `278c5ea7719f9419aff004909aa0442c8ee36734`，分支 `release/server-2026.10.02.3`、附注标签 `server-2026.10.02.3`，父版本为 `.2`。封存期间未重启服务、未切换开发分支或推送 Git；文档收尾另行提交。

包含当前 R6AS Adapter（R6AR 缩放保存/旧 Work 兼容与原生启动 180 秒预算）、R7G1 动态控制器/Relay、R6Z1 runner 与 journald 512/64 MiB、最长 30 天预算。

| 组件 | 精确身份 |
| --- | --- |
| Adapter | `63d88d1e152285983cc8c55ab41f1f6b2d849df51da5505139eb137041742aa0` |
| Controller | `sha256:33a6d2fcd00502f6df7b8e75a2b3eaa70c0e933077919cbdda5dbe77d5fb7b57` |
| 新代理 Relay | `sha256:d57f441789051be7d7a3770d66211f680741a5b413ca8c5dcc765b8ec8bd286d` |
| 保留 DIRECT/static Relay | `sha256:a785d443bf7ede16e0f4728bbcc552a17f6340e6a3fea2d01bd839776716888a` |
| Native targets | `226a4b731ac91b4e5b011efe738cdf8ec68bb53451f219c9aab71de3afb017bb` |

源码清单 358 条，连同清单共 359 文件；程序包另外包含原始 Adapter/Relay 两个二进制。清单 SHA256 `da17d7362ddd76eda860ca80cb13e5031602b0b87415f8dbd2ed55b4946cf641`。实际 Adapter、控制器 98 文件、runner 54 文件/目标清单和 journald 配置匹配冻结输入；标签逐文件、完整文件集合、篡改/缺失/多余/符号链接/错误 pin 拒绝均通过。

| 归档 | SHA256 |
| --- | --- |
| `browser-platform-server-2026.10.02.3-source.tar.gz` | `27fbf2b197d6417cd1436cac58bf41dc5b5798ba1ee1252f2b1ee75247dd3e38` |
| `browser-platform-server-2026.10.02.3-linux-amd64.tar.gz` | `2276abf60c3e8519fbfb71ad7111b9563aed42bca724d4cd31e84215febdcc8a` |

本机路径 `infra/sealskin/runtime/r6at-unified-release-20261002/artifacts/`；独立机路径 `/root/browser-platform-recovery/server-2026.10.02.3/`。独立机两个归档解包/逐文件/两个二进制/16 个固定镜像 ID 校验通过，未激活生产身份，QA 已退役。精确机器结果见[版本 JSON](server-2026.10.02.3.json)。

解包后执行 `python3 verify-release.py --manifest-sha256 da17d7362ddd76eda860ca80cb13e5031602b0b87415f8dbd2ed55b4946cf641`；程序包可加 `--binary bin/profile-adapter`，存在 bin 时两个二进制都会检查。恢复操作和依赖边界以包内 RECOVERY.md 为入口。

验证沿用未变化组件的真实证据：R7G1 571/52/22 组、R6AR 30 显示场景、R6AS 18 协议/210 网络/66 DIRECT/9 升级阶段与旧 Work 及三个固定目标的异机合成恢复。9 阶段升级的 Adapter 目标实际是 R6AR `8fb90eb2…`；最终 `63d88d1e…` 另有完整 Go test/vet、两次真实慢启动和后续 Firefox DIRECT 恢复检查，不能称所有场景均在最终二进制重跑。

回退到 R6AR 可只恢复程序；降到 `.2` 须先正常退役动态代次、确认无动态租约/待处理事务，并用当前授权 API 将非零缩放复位为 0、确认字段省略。保留最新 Home、Session、账号/凭据、目录、journal 和墓碑，不恢复旧在线状态覆盖新操作。`.2` 标签保留为历史静态基线。

本包不含镜像层、真实业务数据或秘密。镜像、入口/信任和加密材料单独保留；真实历史 Home 加当前元数据仍为 OFFLINE_ONLY，不能称为当前业务时点一致的备份。商业供应方自然漂移与新供应方 GUI 切换未测；未提供 accepted 目标的任意浏览器大版本迁移未测。journald 30 天自然到期观察尚未经过。当前客户端验证按用户已确认记录，历史精确参数不补造。

见 [R6AT 验收](../../infra/sealskin/r6at-unified-release-acceptance-2026-10-02.md)及[本轮执行核对](../remaining-work-2026-10-02.md)。
