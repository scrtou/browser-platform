# 本机隔离恢复工具

R6AP 正在扩展[独立机器恢复](remote-recovery.md)：精确镜像冷导入、加密材料闭包、当前权限审查、三引擎合成检查点；以该项实际验收结果为准，本页历史本机 PASS 不扩大为异机通过。

[验收](../r6k-disaster-recovery-acceptance-2026-10-01.md) · [备份契约](../lifecycle/secret-store.md)

`check-disaster-recovery.py` 是已准备 Work QA 的分阶段运行器，不是通用生产恢复命令。`recovery-layout.py` 只暂存单 Home、已激活的 network-qa 归档；重绑所有支持的路径，缺少依赖、未打包挂载或配置作业目录时拒绝，不自动读取旧路径。

## 准备输入

保留至少 4 GiB 磁盘、1 GiB 可用内存；本次解密和恢复使用 tmpfs。每次创建新的私有 `infra/sealskin/runtime/r6k-<唯一标识>/`，目录 0700、文件 0600。源夹具在其 `source/qa`，先按 `check-work-migration.py --help` 的 prepare/run 流程建立独立 network-qa，使用审核过的当前版本材料、Work 源定义和精确二进制；生产路径不得替代 QA 路径。该前置依赖私有发布材料，干净检出不能直接一键运行。

准备 `resources.json`，字段 `recovery_target` 为 `/dev/shm/r6k-local-dr/runtime/recovered`，`restore_bundle` 为 `/dev/shm/r6k-local-dr/bundle`；先创建私有父目录 `/dev/shm/r6k-local-dr/runtime`，两个目标本身必须不存在。固定 tmpfs 路径及 QA 端口限制同一时刻只能运行一份。源凭据 tmpfs 为 `/dev/shm/r6k-source-credentials`，源主密钥在 `source/master-key/master.key`。控制器、Adapter、profile-accounts、Worker、Relay/Guard、探测镜像必须与夹具和构建证据匹配。

初次 freeze 显式提供 `--age`（age 1.2.1，旁边有 age-keygen）、`--artifact`（精确 Worker 构建证据）、`--secret-store-module`（从固定控制器导出且核对版本的 secret_store.py）。主机需 Python3/PyYAML、Docker、Caddy 及现有 QA 工具链；本工具没有打包系统依赖或镜像层。

## 阶段和审查

依次使用 `python3 infra/sealskin/checks/check-disaster-recovery.py <阶段> --root <私有根目录>`；初次 freeze 另加上述三个输入参数。

1. `freeze`：验证真实浏览器数据，正常停止，创建完整选定 Home/控制身份归档，再禁用测试账号并撤销测试凭据版本。生成独立 age 身份，保留输入/摘要；不重复覆盖已有备份或 age 身份。
2. `restore`：验证摘要、解密到不存在的新目录，验证恢复锁和缺失账号拒绝；退役源 QA 后合并当前账号/撤销，移走源路径，重绑新根并启动服务。
3. `verify`：真实认证与显示交接、三类浏览器存储、HTTPS、无绕过、新鲜健康及正常停止。失败保留证据，不自动销毁。
4. `rollback`：确认恢复端停止清零，退役恢复服务，回到保留源检查点并读回数据，再清理 QA 服务。仅验证检查点回退，不同步恢复后新增写入。

后续阶段读取 `inputs/recovery-tools.json`，验证 age 和 Secret Store 模块摘要。私有输入、备份、工具和最终源码摘要应形成独立清单；备份密文与恢复私钥在真正灾备中须分开保管。本次二者同主机保存只供隔离 QA，不能证明主机丢失后的恢复能力。

## 退出与后续

核对 QA 标签和 scope 下容器/网络、进程、端口 29443/29110/28110/28443、socket、挂载均清零后，保存恢复/激活回执和摘要，再删除本次解密 tmpfs。只清理本轮合成 Home，不删除历史或生产备份。对照前后生产配置/容器摘要并确认监控仍运行。

独立主机演练还需明确完整镜像归档、匹配系统工具、离机密钥、最新账号/撤销、全部作业/产物挂载、存储容量和恢复入口；先完成依赖核对，再做冷导入及真实运行验收。本工具不覆盖 Camoufox 全量恢复或整机恢复。
