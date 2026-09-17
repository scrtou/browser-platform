# DEV-2026-09-17-044 · 生产维护执行器错误复用 QA 假设

状态：已解决。发现日期：2026-09-17。关联工作项：[R4B](../work-items/R4B-2026-09-14-target-client-migration.md)。

## 设计预期

[R4B 工作项](../work-items/R4B-2026-09-14-target-client-migration.md)和[入口维护顺序](../../infra/sealskin/entry-auth/README.md#发布候选与维护顺序)要求：公网先进入 503，Work 经当前生命周期正常停止，候选控制器只用生产身份安装 App，登录后取得不含后端能力的 Session 地址，实际画面通过后才开放公网；失败必须保留 journal、Home、维护页和回退材料。

## 实际事实与证据

2026-09-17 的生产维护保留在私有 `release-ready-2/deployment-1/`、`deployment-2/`：

- `stop-profile` 通过正在运行的 Adapter 私有 Unix socket执行，并要求命令配置指纹与进程一致；首版执行器直接给命令另一个回环配置，故在维护页已加载时拒绝，Work 和生产文件未改变。
- 首版候选管理客户端沿用 QA 端口 `28110`，该端口属于保留的 QA 控制器；生产候选监听 `8000`，错误连接造成服务器签名验证失败。候选文件和控制器已经安装，但 App 尚未写入。
- 登录响应包含多个 `Set-Cookie`，普通字典只保留一个，导致登录后固定 Profile 页面重新跳转；保留原始头集合后通过。
- 未登录 Session 根路径的实际安全响应为 404，不是执行器预期的 401；精确当前 Session 路径无 Cookie 仍为 401。
- 最终交接 URL 只保留非能力 UI 参数 `embedded`；`ticket` 已在 `/auth/accept` 消耗。执行器最初把任何查询参数都当作后端能力而拒绝。

## 影响与处理决定

- 影响：维护时间延长并留下两次失败阶段；两个公网域名始终保持 503，旧 Work 先经生命周期停止，Home、journal、备份和静态 Relay 均保留，没有用失败假设放宽服务端认证。
- 处理方式：修复实现。停止阶段用同一路径回环配置短暂重启旧 Adapter并在 `finally` 恢复；管理客户端固定生产 `8000`；逐个读取 Cookie；根路径断言改为 404，精确 Session 仍核对 401；最终 URL 仅允许 `embedded`，其他查询字段继续拒绝。
- 恢复路径按 `files_staged` / `controller_ready` 的精确文件、状态、容器和能力继续，已运行代次采用幂等核对，不覆盖 journal 或重复创建 Home。
- 用户已授权当前 R4B 维护；本次没有新增数据删除或扩大生产范围。

## 实施、验证与文档同步

| 材料 | 更新 / 结果 |
| --- | --- |
| 实现 | `deploy-r4b-production.py` 修复控制 socket、生产端口、多 Cookie、根路径状态和 `embedded` 白名单；增加分阶段幂等恢复 |
| 验收与证据 | `deployment-2/deployment-result.json` PASS；Work/Personal 各 1 record/1 Worker，能力均为 1；Personal 5 resources/1 Relay/1 Guard/2 networks；公网登录 200、固定入口 303、根路径 404、精确 Session 无 Cookie 401 |
| 设计 / 规格 / 组件说明 | 本记录与 R4B 阶段验收同步生产实际顺序；入口服务端契约未修改 |
| 进度 / 计划 / 工作项 | 已同步为生产候选生效；目标 Mac 生产复测与正式 Caddy/Docker/VPS 重启已于同日分别通过，R4B 已收尾 |

## 最终复核

2026-09-17 生产控制器、入口账号、密封 Session、Work 兼容镜像和 r9/fill-r10 Personal 已生效；Caddy 运行配置与候选一致，旧/new Home 均保留。执行器问题已由实际生产续接验证，偏差已解决；目标 Mac 和 Caddy/Docker/VPS 重启分别由 R4B 阶段验收记录，不由本记录判定通过。
