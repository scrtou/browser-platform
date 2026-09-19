# DEV-2026-09-18-051 · 自定义指纹作业的执行位置

状态：已解决（候选，未部署）。发现日期：2026-09-18。关联工作项：[R6E](../work-items/R6E-2026-09-18-custom-fingerprint-jobs.md)。

## 设计预期

[管理面规格](../specs/proxy-environment/management.md#指纹配置) 要求自定义指纹由“服务端”创建 `environment_job`，在隔离容器（默认拒绝网络、只读根、内存/CPU 上限）中执行 generate → verify → acceptance，一次只运行一个作业，主机内存不足时排队并提示；通过后产物与报告进入环境目录并标为 `accepted`，失败保留报告标为 `failed`。

## 实际事实与证据

- Adapter 是主机 systemd 用户服务，没有 Docker 组权限，也不应成为第二个容器生命周期所有者；SealSkin 只管理 Worker/Home，不提供“运行一次性生成/验收容器”的接口。
- 完整验收（`infra/camoufox/acceptance.py --phase all --recreations 10`）需要一次性内部网络与名为 `profile-relay` 的 QA SOCKS5 夹具（R4B `window-r8` 记录与 `checks/qa-artifact-proxy.py`），并访问 `example.com` 做浏览器经代理的 HTTPS 检查；这些 Docker 操作一直由主机端脚本以 Docker 组权限执行。
- 固定生成器对屏幕约束只是尽力而为：12 次抽样中 1 次返回 1600×900，`environment.py` 以 `ENVIRONMENT_SPEC_MISMATCH` 拒绝该产物。

## 影响与处理决定

- 处理方式：修订实现路径，保留契约。“服务端”拆成两部分：Adapter 只校验高层字段、把固定规格写入私有 spool（`queue/<job>.json`，0600、O_EXCL、fsync）并读取状态文件；主机端执行器 [environment-job.py](../../infra/camoufox/environment-job.py) 与 `acceptance.py` 同样持 Docker 组，持 spool 文件锁一次处理一个作业，在固定 Worker 镜像中以只读根、无网络、1.5 CPU/1536 MiB、drop ALL 生成产物（规格不符最多重试 3 次，不改产物），创建一次性 internal/egress 网络与 QA 夹具后执行完整验收，通过后经镜像自身 `verify` 核对并原子追加目录条目（同 ID 拒绝覆盖）；失败保留 spool 内产物、报告与日志，不发布。
- 主机可用内存低于阈值（默认 2048 MiB）时作业保持 `queued` 并写入 `HOST_MEMORY_LOW` 提示；Adapter 最多允许 4 个排队/运行中的作业。
- 对当前交付的影响：不新增 Docker 所有者，不改变 SealSkin 生命周期；目录条目增加描述字段（locale/languages/timezone/screen/accepted_at/job_id）供面板显示，Adapter 目录读取按字段解析。执行器未安装为服务，生产未启用作业。

## 实施、验证与文档同步

| 材料 | 更新 / 结果 |
| --- | --- |
| 实现 | `infra/camoufox/environment-job.py`（run/register）、`prepare-sealskin.py` 抽出 `build_definition`；Adapter `profile/environment_jobs.go`、面板作业表单/列表、目录 `source=custom` 放开 |
| 验收与证据 | 8 项执行器单元测试（fake 执行器：状态流转、无效请求、内存不足排队、有界重试、失败不发布、目录不覆盖、锁与顺序、权限）；一次真实作业：生成 1 次成功、完整验收 10 次重建通过、目录追加、夹具清理。见 [R6E 验收](../../infra/sealskin/custom-fingerprint-acceptance-2026-09-18.md) |
| 设计 / 规格 / 组件说明 | [管理面规格](../specs/proxy-environment/management.md#指纹配置)、[Camoufox 说明](../../infra/camoufox/README.md#自定义指纹作业)、[Adapter 说明](../../adapter/README.md) 已注明执行器与 spool 契约 |
| 进度 / 计划 / 工作项 | R6E 工作项、进度与计划已更新 |

## 最终复核

规格中的隔离生成/验收/发布流程按“Adapter 写请求 + 主机执行器执行”落实，容器限制、失败保留与不发布、一次一个作业、内存排队提示均保持；执行器作为服务安装与生产启用归 R6F。
