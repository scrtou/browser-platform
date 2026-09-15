# DEV-033 · Worker 显示凭据进入 Docker 环境变量

状态：已解决（代码与隔离 QA，未部署生产）。工作项：[R5D](../work-items/R5D-2026-09-14-entry-authentication.md)。

预期：S01/S02 要求普通配置、Docker 环境与 argv 不含密码或 Session 能力。Worker 只获得自身显示认证所需的材料；上游代理凭据仍只交给专属 Relay。

源码事实：`launch.session_base_env()` 把 `CUSTOM_USER`、`PASSWORD` 和协作模式的 `SELKIES_MASTER_TOKEN` 放入环境，`DockerProvider.launch()` 将其直接传给 Docker。就绪探测也从这份内存字典构造 Basic Auth。已实现的 Session 快照 AES-GCM 仅处理持久化数据库，不覆盖 Docker inspect、Worker 进程环境及其初始化脚本产生的副本。

处理选择：修复实现，保留显示认证。先核对固定 Worker 的初始化与认证文件行为，再采用受限的专属秘密文件传递；运行材料必须有明确的创建、恢复、失败保留和清理路径。不得只把变量改名、移入 argv，或取消认证来满足扫描。S02 中“只有 Relay”指上游凭据；Worker 自身的显示认证材料必须单独隔离并验收，不能因此开放上游凭据访问。

须验证：最终 Docker 请求/inspect、进程 argv、普通 Home/日志无明文凭据；正确与错误显示认证；控制器/Worker 恢复；材料缺失、权限/链接/跨 Session 异常及正常停止清理。旧生产 Worker 保持，候选 1 和修复前证据保留于本项私有运行目录。

实现：候选 3 控制器已接入专属 tmpfs 的创建、恢复、挂载校验与删除；[Worker 显示认证层](../../infra/browser-access/README.md) 生成 r7。随机密码改为带盐校验文件，协作 token 经专属只读文件进入 Selkies 内存，TLS 私钥移出 Home。早期 124 项定向检查及 r7 产物重放证据保留。

2026-09-15 最终验证：真实默认 `/init`、二进制画面、正确 Basic Auth 两次 200 和缺失/错误六次 401 通过；`worker-auth-negative-2/` 五类材料错误均拒绝且未开放显示监听。`client-qa-13/` 的控制器 restart、Worker 材料重建/resume 保持原身份及三类存储；`runtime-security-3/` 的 407 面扫描覆盖实际 UID 0/1000/33，无已知秘密命中且未遗漏存活进程。`cleanup-1/` 确认专属材料及 QA 资源清理。S02 已明确上游凭据只给 Relay、显示材料另行隔离；实际协作房间未测，详见 [最终验收](../../infra/sealskin/entry-authentication-acceptance-2026-09-15.md)。
