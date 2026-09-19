# R6E 自定义指纹生成与验收作业验收

日期：2026-09-18–19（UTC）

本报告覆盖 R6 管理面的第 5 步候选代码。生产 Adapter 仍为 candidate-4，控制器未变；未替换二进制、账号表、真实 Home、Session 或生产环境目录。详细脱敏结果保存在被忽略的 [R6E 私有结果](runtime/r6e-custom-fingerprint-2026-09-18/result.json)。

## 实现范围

- Adapter：`environment_job_spool` 配置；管理员经 `POST /manage/environment-jobs` 只提交 locale、languages、timezone、screen、DPR（当前只接受 1）与可选窗口；服务端按规格 46.2 校验（BCP 47、首语言等于 locale、IANA 时区、640×480–3840×2160、窗口不超过屏幕）后派生固定规格（Linux、WebRTC/定位关闭、8 项能力），以 0600/O_EXCL/fsync 写入 `queue/<job>.json`；最多 4 个排队/运行中作业；列表只读取 `status/<job>.json`（版本、job_id 与状态枚举校验，未知字段拒绝），只显示高层字段、稳定代码与摘要。
- 主机执行器 [environment-job.py](../camoufox/environment-job.py)：持 spool 文件锁一次处理一个最早的作业；内存不足写 `HOST_MEMORY_LOW` 并保持排队；在固定镜像中以只读根、无网络、drop ALL、1.5 CPU/1536 MiB 生成，`ENVIRONMENT_SPEC_MISMATCH` 最多重试 3 次；创建一次性 internal/egress 网络与 `profile-relay` QA 夹具后执行 `acceptance.py --phase all --recreations 10`；通过后由镜像 `verify` 核对产物与报告，原子追加 `source=custom` 目录条目（同 ID 拒绝）；任何失败保留 spool 内产物、报告与日志并写入稳定失败码。`register` 子命令可把已验收的固化产物登记为 `source=frozen` 条目。
- 目录条目新增 locale/languages/timezone/screen/accepted_at/job_id 描述字段，面板新增浏览器时改为下拉选择目录条目；差异登记为 [DEV-051](../../docs/deviations/DEV-2026-09-18-051-environment-job-runner.md)。

## 隔离验证

Adapter（主机 Go 1.27.1；race 在无网络的 checks 镜像内以 gcc、`CGO_ENABLED=1`、`-p 1` 串行执行）：

```text
go test -count=1 ./...                 9 packages; 249 passed, 0 failed, 0 skipped
go vet ./...                           PASS
gofmt -l .                             no output
go test -race -p 1 -count=1 ./...      PASS (9 packages)
```

新增 Go 测试覆盖：14 类无效高层字段拒绝、派生规格的固定字段、请求文件权限与内容、状态文件读回（running/failed）、未知字段/异属 job_id/错误版本拒绝、遍历 ID 拒绝、排队上限与完成后释放、spool 组可读或未配置拒绝、目录 `custom` 条目可创建浏览器而未验证来源拒绝、执行器写出的目录条目可被文件目录读取、面板表单解析/通知/JSON 列表/未登录与未启用边界。

主机 Python（3.11）：`tests/test_environment_job.py` 8 项与既有准备器 13 项共 21 项通过，覆盖接受作业的完整目录条目（挂载、环境、标签、能力）、无效请求在生成前失败、内存不足排队提示、有界重试只针对规格不符、失败验收保留证据不发布、夹具不可用失败、目录 ID 不覆盖与版本校验、锁与最早优先、组可读请求拒绝。

真实隔离作业（固定 r9 镜像 `sha256:10f6420a…`，独立 spool 与目录，不接触生产）：

```text
job-aeba527a5ec71f1f  en-US / America/New_York / 1920x1080@1 / 窗口 1920x1080
generate               attempt 1 → env-custom-aeba527a5ec71f1f-artifact-1（resolvedConfig 语言/时区/屏幕/窗口与规格一致）
acceptance             artifactTests pass；11 项启动拒绝；两个 QA Home 各 10 次重建 + 离线恢复，23 次观测稳定、存储恢复
catalog                source=custom, status=accepted；产物与报告 SHA-256 与文件一致；模板含 14 项环境变量、两项只读挂载、无策略引用
cleanup                夹具容器与两个网络已删除（docker ps -a / network ls 中无 envjob 资源）
duration               01:29:29–01:32:44 UTC
```

## 未覆盖与后续

执行器未安装为 systemd 服务/定时器，也未与生产 Adapter 配置或生产目录连接；真实浏览器/Trilium 使用自定义产物、DIRECT 生产前置、R6F 组合 QA 与回退未测。`osFamily` 只支持 Linux、DPR 只支持 1、定位固定关闭，与当前已验证的适配器能力一致。生成器对屏幕约束的偶发不匹配由有界重试处理，不修改产物。

R6E 可收尾为未部署候选；下一计划项为 R6F。任何生产部署仍须等待 R6F 组合 QA 与明确维护授权。
