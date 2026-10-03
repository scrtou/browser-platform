# R7F · 当前 Work 发布组合的独立恢复与实际回退 — 2026-09-30

[验收索引](../../docs/acceptance/README.md) · [R7F 工作项](../../docs/work-items/R7F-2026-09-23-production-release.md) · [生产迁移验收](r7f-legacy-migration-acceptance-2026-09-30.md)

## 结论与范围

独立 QA 已完成真实管理员登录/近期密码确认、旧 Work 迁入 DIRECT、原生 Wayland Firefox 公网页面、正常停止后新代次三类存储读回、网关故障关闭、实际回退和重新批准迁移后的数据读回。生产三个浏览器保持原目录、Session、容器及运行身份，没有停止、回退或修改真实 Home。

这是当前线上二进制和镜像组合的隔离验收，不是生产 Work 的停止重建、真实站点登录或目标 Mac/Trilium 完整矩阵。R7F 父项仍进行中，R7G 未部署。

## 固定输入与隔离

| 输入 | SHA-256 / 范围 |
| --- | --- |
| Adapter | `7f4e2a1aee6c79de904e19b2e40c2c69c6ec39152fbc0ff13798db6ef1c49635`，复制线上二进制 |
| 控制器 | `bfcd878f693578b65d2911015aedd3a6a79cc25f20619c0c36525f8e19dd90e3`，无代码覆盖挂载 |
| 原 Work 父镜像 | `ec848635e68db2d1c805fcf9972ef4586bcd86a9ed14b2075b0c5a40fbbc503f` |
| 受管理 Work 镜像 | `895907b7cecf793db5b5b108e9a9ac371d0d381833e729d0b5cc16f8eee8e356` |
| DIRECT Relay | `a785d443bf7ede16e0f4728bbcc552a17f6340e6a3fea2d01bd839776716888a`，复用线上批准解析器与探测设置 |

QA 另建控制器配置/存储、Home、应用、账号、Profile 目录、策略表和显示 tmpfs，Docker 代理限定 QA owner 与 scope。源应用从已批准的完整 Work 定义派生，显式替换 QA 身份/源站、BiDi 启动脚本和资源限额，去掉生产剪贴板挂载。没有复用生产 Home 或会话；本报告不覆盖剪贴板、上传、远程桌面视觉效果。

## 实际检查

| 检查 | 结果 |
| --- | --- |
| 真实管理入口迁移 | QA 私有 HTTPS → 登录 → CSRF/Origin → 密码确认 → 管理页迁移；完整 resolved App 只改变批准镜像与独立 policy |
| 固定入口启动 | GET 取得 CSRF/launch plan，POST `/browser/{profile}/start`；授权交接 URL 不输出到公开记录 |
| 浏览器公网与进程 | 真实 Firefox 原生 Wayland，BiDi 导航 `https://example.com/`，标题为 Example Domain；每代次精确目标镜像，1 record/1 Worker/5 resources |
| 正常停止与重建 | 管理页 stop 后 record/Worker/resource 全归零；再次打开的 operation 与浏览器启动时间改变 |
| 三类浏览器存储 | 同源 Cookie、localStorage、IndexedDB 写入测试值，IndexedDB 等待事务完成；新代次逐项一致 |
| QA 网关故障 | 只停止本 QA Relay；健康报告明确 relay fail，Worker 对公网 TCP、Docker DNS、公网 DNS、metadata 的绕过仍明确被拒绝 |
| 实际回退 | stopped/0 resources、disabled 后经近期认证回退；完整原 App 与原 Definition 精确恢复，Home 普通文件、journal、账号与不可变策略表摘要保持 |
| 再批准与迁移 | 以回退后的新 revision 和新备份/恢复摘要重新批准；真实管理页迁移、固定入口新代次再次读回三类测试值 |
| 备份边界 | 最终 QA 的 133 个普通文件 age 密文归档、解密 tar 摘要与独立目录逐文件比对一致；2 个非普通节点列入排除清单，副本未激活；不称为完整控制根灾备 |
| 清理与生产保持 | 首轮及干净复跑均确认 QA 代次、控制器/上游、网络、匿名卷、三个私有进程和显示 tmpfs 清理，端口关闭；生产三者原身份保持，最终 15:29 UTC 均新鲜 healthy |

共享 [Worker 绕过探针](checks/worker-bypass.py) 发出完整 29 字节 DNS 查询，仅权限或本地路由明确拒绝算 blocked；超时、对端拒绝连接均不能冒充隔离。3 项针对性回归通过；[DEV-078](../../docs/deviations/DEV-2026-09-30-078-work-dns-probe-evidence.md) 的早期单字节查询历史结果不被改写。

## 工具与失败保留

新增 [迁移/恢复检查器](checks/check-work-migration.py)，提供 `prepare`、`run`、`cleanup` 三阶段。依赖已有 `prepare-network-qa.py` 的独立环境、固定二进制、私有发布基线与批准源定义，具体参数见 Work 组件说明。

首轮准备暴露的工具问题已保留：完整应用应从列表读取；本机 Python 不支持 `tarfile` 的 `filter` 参数，改为只恢复已验证路径的普通文件；管理写入需策略父目录 0700；账号工具需先有目录；就绪检查需正确 Host；Firefox 专用目录需预建；固定入口须执行表单 POST；原始 inventory 无独立 `orphans` 字段，零 Worker 已覆盖残留检查。第一次权限拒绝留下 `migrating`，修复 QA 权限后相同管理员/幂等键继续成功。没有改产品代码或降低验收条件；中断续跑读取原 marker 与首代次证据，没有重新写入测试值冒充恢复。

私有材料在忽略目录 `infra/sealskin/runtime/r7f-work-recovery-20260930/`，包括原失败、批准条目、age 密文/恢复副本、运行结果、完整状态和清理/生产保持回执。修正后的完整脚本于新目录 `r7f-work-recovery-20260930-final/` 从干净环境完整复跑通过：基础准备、认证准备、8 项实际检查、清理和生产保持全部成功；保留 `prepared.json`、`results.json`、两轮批准/备份、三代运行证据、`cleanup.json`、`production-after.json` 与工具摘要清单。两个 QA 作用域均已清理。 文档收尾核对 12 份文档、573 个相对链接/锚点、4 个 Python 文件语法及 `git diff --check` 通过。

## 后续边界

生产 Work 的真实 Home 停止重建与数据确认仍未执行；实际回退机制已由本 QA 补证，不为验收而回退正在成功运行的生产实例。完整 Mac/Trilium 首页、网络代理 Tab、模板选择与 r10 远程桌面证据，特定旧恢复管理员身份拒绝仍归 R7F 后续。设计与管理规格契约不变。
