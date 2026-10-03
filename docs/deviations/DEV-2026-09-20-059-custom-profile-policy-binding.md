# DEV-059 · 自定义 Profile 复用 Personal 网络策略被控制器拒绝

状态：已解决（R6F，独立策略验收与清理完成）

## 现象

2026-09-20，按 R6F 真实 Mac/Trilium 自定义 artifact 验收步骤创建临时 Profile `browser-1045329764f7`，绑定已验收的 `env-custom-804399c31829bb18`，并错误复用了 Personal 的网络策略 `personal-camoufox-r9-socks5-r1`。Profile 创建和应用安装成功，但从固定入口启动时返回 502；Adapter 记录 `SealSkin API returned HTTP 422`，最终无 record、Worker、网络或其他残留资源。

## 原因与范围

当前控制器网络策略按 Profile/Application/Home 绑定，Personal 策略不能直接附加到新建 Profile。此前 R6F 隔离自定义 Profile 使用的是为该 Profile 单独追加的策略；本次客户端验收说明遗漏了这一前置，属于验收步骤/运维说明偏差，不是 artifact 本身验收失败。自定义 artifact 的目录摘要、镜像和 acceptance 证据仍匹配；Personal/Work 未受影响。

## 处理决定

保留失败 Profile 及其 Adapter/控制器日志作为私有证据；不重试同一网络策略。随后已为该临时 Profile 创建独立、不可变的受管理代理策略并成功启动，服务器健康检查和目标 Mac/Trilium 视觉交互验收通过（Google 第三方反自动化验证页作为外部站点现象单独记录）。策略凭据只通过管理面输入，不写入公开记录。验收结束后已按 Stop/资源归零/归档删除完成清理：Profile 保留 `deleted` 审计记录，应用、账号授权和代理 secret 均已移除或撤销，Home 已归档，Personal/Work 未受影响。

## 证据

- 私有 Adapter 状态与启动时间窗：`infra/sealskin/adapter-state.json`、用户 Adapter journal。
- Profile 绑定：被 Git 忽略的 R6F 运行目录 `production-management-1/` 下对应状态与应用记录。
- 服务器端只读核对：失败时 `records=0`、`workers=0`、`resources=0`、`networks=0`。

公开记录不包含 Cookie、密码、私钥或带授权参数的 Session URL。
