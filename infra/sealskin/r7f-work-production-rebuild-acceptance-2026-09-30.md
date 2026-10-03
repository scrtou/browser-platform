# R7F · 生产 Work 正常停止、备份与重建 — 2026-09-30

[验收索引](../../docs/acceptance/README.md) · [R7F 工作项](../../docs/work-items/R7F-2026-09-23-production-release.md) · [独立 QA 恢复与回退](r7f-work-recovery-acceptance-2026-09-30.md)

## 当前结论

17:08 UTC Work 经 Adapter 正常停止，Session 记录、Worker、Relay、Guard、网络及占用全部归零，没有强杀或直接删容器。新停止时点 5,938 条目 age 加密备份、verify 和独立 restore 通过；17:10 UTC 原 Home 与恢复副本的 5,740 个普通文件，以及目录和符号链接的内容/类型/权限逐项一致。恢复副本未激活，生产原 Home 保留。

**本次 Work 正常重建维护已完成。** 用户经固定入口重开，17:15 UTC 核实新 operation/Session/Worker/Relay/Guard、原 Home/完整应用/目录/策略与健康网络；用户回复“1.正常 2。不适用”，确认公网页面和输入正常，原书签/登录项不适用。文件一致性与用户页面确认分别留证，不记为生产三类存储读回或既有登录恢复。R7F 父项继续进行，R7G 未部署。

## 固定输入与维护边界

| 输入 | 核对结果 |
| --- | --- |
| Adapter | `7f4e2a1aee6c79de904e19b2e40c2c69c6ec39152fbc0ff13798db6ef1c49635`，本轮未部署 |
| Work | revision 8、启用、managed DIRECT，原 `work` Home / `firefox-work` 应用 |
| Worker | `sha256:895907b7cecf793db5b5b108e9a9ac371d0d381833e729d0b5cc16f8eee8e356`，与原受管理镜像构建 artifact 一致 |
| 完整应用 | 经控制器加密管理员 API 读取，与原批准迁移结果逐项相同 |
| 停止前运行 | 新鲜 healthy，1 record / 1 Worker / 0 orphan / 5 resources，1 Relay / 1 Guard / 2 networks；原 Home 挂载、Guard namespace 和正常退出能力符合要求 |
| 其他 Profile | Personal 与“测试”的目录、Session、容器启动身份保持；“测试”窗口此前由用户主动关闭，不在本次维护范围 |

本次沿已有 R7F 维护授权只正常停止 Work，再以原 Home 创建新代次；不部署代码、切换网络、回退应用、覆盖旧共享 journal/账号/Session 或删除 Home。当前完整应用和配置/目录/账号/策略摘要保持。原备份和所有失败材料保留。

## 停止与恢复证据

| 检查 | 结果与范围 |
| --- | --- |
| 正常停止 | 私有 control socket → Adapter Stop → 控制器正常 Wayland 关闭及资源回收；命令成功，全部计数为零 |
| Home 无占用 | 检查全部 Docker 容器（含已退出），没有挂载该 Home 的容器 |
| 匹配时点证据 | 采用原受管理 Work 构建 artifact 和本轮实际健康/运行观察的 `fixed-runtime-image/v1`；不沿用旧镜像验收或伪造存储测试 |
| 加密归档 | 5,938 条目，密文 SHA-256 `9b1eedbeb027e3d0744faa9ffb9e6472123e5eadcdfa457d364c816f28623a56`；工具再次检查停止及源文件稳定性 |
| 独立校验与恢复 | age verify 与全新私有目录 restore 成功；tmpfs 中间明文自动清理，副本 `ready_to_activate=false`，保留恢复门禁 |
| Home 一致性 | 5,874 个持久条目，包括 5,740 个普通文件；摘要、大小、目录/链接类型和权限一致 |
| 运行节点排除 | 仅按现有工具契约排除 1 个停止后残留 Wayland socket；无持久数据，原节点保留，由新桌面重建；其他特殊节点不放宽 |
| 其他状态保持 | 停止与备份后配置/目录/账号/应用/策略摘要及其他 Profile 的 Session/容器身份与维护前一致 |

初次预检在执行任何维护前因要求 `disabled` 显式为 false 而中断。实际记录省略该字段，符合 `Definition.Disabled` 的 Go `bool` / `omitempty` 契约；按实际默认值修正本机预检后通过，没有修改生产目录。该失败和前后证据保留，不属于产品行为偏差。

## 重开与剩余条件

固定入口为 `https://mybrowser.azhen.de/browser/work/`。用户已通过现有登录和启动流程重开；未使用仅恢复休眠代次的 `resume-profile`。

| 重开后检查 | 结果 |
| --- | --- |
| 新代次 | operation/Session 均改变，Worker/Relay/Guard 三容器均为新 ID；1 record / 1 Worker / 0 orphan / 5 resources |
| 原绑定 | revision 8、完整应用、Home 挂载、精确镜像与独立 DIRECT policy 保持；其他 Profile journal 逐项一致 |
| 新鲜健康 | 17:14:56 UTC `healthy`，BROWSER_RUNNING / DISPLAY_READY / DIRECT_OK，报告未过期 |
| 实际网络 | Worker 经代次 Relay 解析域名并通过 TLS/HTTPS 200，Example Domain 内容符合预期 |
| 绕过拒绝 | 公网 TCP、公网 UDP DNS、metadata 得到 ENETUNREACH；有效 Docker DNS 查询在 send 得到 EPERM；没有用超时冒充拒绝 |
| 用户客户端 | 用户重开后页面/输入“正常”，原书签/登录“不适用”；未重新提供客户端版本/视区，不推断双客户端完整覆盖 |
| 其他 Profile | Personal 新鲜 healthy；“测试”仍为用户主动关闭后的 BROWSER_EXITED，显示/代理正常；Session/容器和 journal 保持 |

生产未写入合成 Cookie/localStorage/IndexedDB 测试数据。三类存储重建和实际回退的自动化证据仍限于同日独立 QA；本轮恢复副本一致也不替代真实站点登录确认。客户端精确尺寸、Trilium 菜单和最终发布包封版继续由 R7F 承接。

私有脚本、原失败、完整应用、前后快照、age 归档/回执、未激活恢复副本和文件清单在忽略目录 `infra/sealskin/runtime/r7f-work-production-rebuild-20260930/`，证据根 0700，脚本/JSON/回执 0600。设计与管理规格契约不变；本轮没有产品代码或部署变更。

重开前阶段复核通过 11 份文档、484 个相对链接/锚点、2 个私有 Python 脚本语法与 `git diff --check`；解密 tmpfs 已清理，恢复副本未激活。重开后的完整 journal/状态/健康/网络及用户原始反馈也存于同一私有目录；本维护范围已完成，R7F 父项仍待客户端尺寸/菜单和发布包封版。

重开后收尾检查：11 份文档、484 个相对链接/锚点、2 个私有脚本语法和 `git diff --check` 通过；新证据权限、tmpfs 清理与恢复副本未激活状态再次核对通过。
