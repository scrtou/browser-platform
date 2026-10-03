# R6J · 动态容器日志限额验收

日期：2026-10-01 UTC。结论：新增日志策略通过 562 项完整控制器测试及真实四类容器创建检查，候选离线构建、安装清单和 overlay 核对通过；全部 QA 清理，生产保持。生产应用日志限额尚未部署。

- 候选 release：`0.3.2-entry-auth-v1-9bdcd6fddc6dc698`。
- 镜像：`sha256:fa9349bbe19128a3d52fd38be60e0977a08ceabc932a781c51c5f30c7389397f`。
- `bounded-logs.patch` 是准备器第四层补丁，新增 `bounded_logs.py`，安装清单共 36 文件，实际字节全部匹配。
- 新容器固定 json-file、max-size=10m、max-file=3、compress=true。Worker 在应用 overrides 之后设置，不能通过 none 或 max-size=0 取消；Relay/Guard/启动探测各创建入口均显式设置。

| 验证 | 结果 |
| --- | --- |
| 固定上游离线准备、镜像构建 | 成功；被测树全部产品文件与 payload 相同 |
| 新增专项 | 5 项通过：独立配置对象、三种 Worker override、真实创建调用链覆盖 Relay/Guard/探测 |
| 完整控制器 | 562 passed，2 个既有依赖弃用提示；约 169 秒 |
| 实际 Docker 创建事件 | 按独立 QA scope 收集，Worker/Relay/Guard/探测四类实际 HostConfig 全部精确匹配策略 |
| 网络/生命周期保持 | 认证 HTTPS 成功，四类 Worker 绕过拒绝，正常停止清空全部代次/夹具 |
| 真实轮换 | 前一阶段独立容器用同一 json-file/压缩方式及缩小阈值实际轮换，文件数/大小检查通过；见[阶段验收](r6j-observability-acceptance-2026-10-01.md) |
| overlay 与生产保持 | 当前生产 96 个应用文件保留；候选四个文件修改、两个新增均属 R7G/日志预期。生产 Profile、配置和容器身份/镜像/启动时间前后一致 |

首轮专项运行因 cap-drop ALL 后 root 无权读取属主私有目录而失败，改为属主 UID 执行后通过，未放宽目录权限。首轮实机事件采集未返回记录，严格记 FAIL 并正常清理；采集器改用 Actor.ID、保留私有 stderr、检查流退出状态后完整重跑通过，使用无缓冲字节读取防止事件预读与 select 不一致。两轮失败证据保留，未降低验收条件。

私有根 `runtime/r6j-log-policy-20261001/` 保存固定构建输入、源码、专项/完整测试、36 文件安装核对、四类创建记录、生产日志只读清单及 `final-status.json`。临时显示目录、QA 容器/网络/代次均清零。只读监控 timer 作为既有交付继续运行。

候选包含尚未批准部署的 R7G，不能以日志修复为由直接部署。现有 Docker 容器不会因新默认值自动变化；共享 journald 策略也未改。精确对象、影响、依赖、迁移、回退和禁止覆盖的数据列在[生产维护材料](../monitoring/production-log-maintenance.md)。R6J 的监控上线和日志隔离候选范围完成，应用日志生产落地与主机共享日志预算归统一发布/最终审计，仍明确未完成。
