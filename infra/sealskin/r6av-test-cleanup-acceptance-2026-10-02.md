# R6AV · 测试数据清理与管理员初始化验收

状态：PASS，已收尾。工作项：[R6AV](../../docs/work-items/R6AV-2026-10-02-test-data-cleanup.md)。恢复点为已通过完整异机验证的[R6AU一致性备份](r6au-consistent-business-backup-acceptance-2026-10-02.md)。

按用户指定范围完成清理：四个浏览器经正常生命周期归档删除、两个代理修订撤销并隐藏、两个指纹来源与两个自定义显示来源删除、12条可见旧验收组合删除。另2条旧组合和3个保留任务此前已有删除标记，逐条核实后保持。owner已移除，当前没有任何访问账号；保留一个原有内置自动显示来源，规定的新内置数据另由下一工作项建立。

| 验收项 | 结果 |
| --- | --- |
| 最终可见数据 | 浏览器0、代理0、指纹来源0、自定义显示0、验收组合0、任务0；内置自动显示1 |
| 生命周期与数据 | 受管理Worker/Relay/Guard为0、journal绑定为0；4个Home归档manifest与原Home/应用/Profile对应，原活动Home路径不存在；目录10条删除历史和原审计/队列证据保留 |
| 凭据与账号 | 两个代理Secret Store版本均实际返回SECRET_REVOKED；注册表为显式v3初始化状态、零账号，旧owner不存在；账号check命令通过 |
| 初始化 | Gateway验证初始化页、旧登录/密码拒绝、CLI初始化后管理登录；并发初始化仅一个成功、已有账号/替换/非法参数拒绝、普通最后管理员保护保留 |
| 失败处理 | 第一次预检发现3个任务已隐藏而中止，未删除数据；首次删除完成2个浏览器后，旧Personal缺环境ID被拒绝并保留deleting/Home，修复后沿同一记录完成，Work同样正常归档 |
| 回归 | 工作树和精确候选完整Go test/vet通过；Access/账号全套race通过；旧Home归档新测试在旧实现复现失败，修正后普通/旧归档及幂等重试、相关race通过 |
| 部署与保护 | 两次Adapter限定发布分别核对当时真实状态保持；最终初始化页面200、无登录表单，三个用户服务恢复。Controller/runner/镜像及非本项容器保持 |
| 独立留存 | 124个冻结源文件与Adapter/账号两个二进制，共126文件，在独立机完整摘要校验；没有在独立机激活当前业务服务 |

最终Adapter SHA-256：`6de8aba3400ab8e0c4dbe98db37d3dc7a9e4b625202d472756fde7a3177d91b2`。账号CLI：`3ae50c36fbe92271af664e225d802868041a2cbfc8d53c1377aa06f1521d1105`。程序增量归档：`e850d2373911fc057369e682a39721c6888f625ca46f7f4b968837745357e907`。

[DEV-140](../../docs/deviations/DEV-2026-10-02-140-account-bootstrap-state.md)通过显式初始化格式修复，旧格式空表/缺失/损坏仍拒绝。[DEV-141](../../docs/deviations/DEV-2026-10-02-141-legacy-home-archive-metadata.md)通过保留值`legacy-unrecorded`记录旧定义未登记环境产物的事实；不是accepted产物，不改写原目录或补造指纹验收。Controller原归档协议、锁、零资源和幂等语义保持。

初始化命令及回退条件见[入口账号说明](entry-auth/README.md)和[运维](../../docs/operations.md)。生产未运行初始化命令、未留下临时管理员；用户自行选择账号名和密码。旧v1/v2程序不能直接读取v3等待状态，回退须保留新读者或先以新CLI初始化，不能恢复旧owner表撤销清理。

私有证据位于`infra/sealskin/runtime/r6av-test-cleanup-20261002/`：候选manifest/差异、测试与race、部署前后保护、失败/重试日志、`cleanup-result.json`、四个归档manifest、实际撤销检查及独立机程序结果。首次race因本机未配置C编译器未执行，改用无网络独立编译容器后通过；首次程序包解包因旧Python无filter参数拒绝，已在成员类型/路径完整检查后使用兼容解包并逐文件验证，原包未变化。

本项未建立24个新内置组合、未定版1.0，也未实施指纹增强。后续按[完整计划](../../docs/v1.0-delivery-plan.md)继续。

已验证Adapter组件的124文件完整源码单独提交为`7edc66cf957bc17a880bc41fb1ed0c05126da7cc`（本地分支`review/r6av-adapter`）；SOURCE.json记录基线、完整文件摘要及两个二进制摘要。这是组件源码审核提交，不是新的完整发行版本。原混合开发分支/索引/既有改动保持，1.0定版时统一整合。
