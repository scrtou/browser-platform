# R6Z1 · Chromix 同屏尺寸固定窗口修复

状态：PASS，已收尾并部署；原来源新组合已验收并发布。工作项：[R6Z1](../../docs/work-items/R6Z1-2026-10-01-chromix-window-geometry.md)，偏差：[DEV-119](../../docs/deviations/DEV-2026-10-01-119-chromix-fullscreen-sized-window.md)。

## 原因与改动

原任务 `job-956e4202f308337c` 要求 screen/window=1920×1080、DPR1。旧镜像在独立 QA 再次复现 outer=1919×1079：Chromix/Openbox 非最大化策略无法给出同屏尺寸窗口，屏幕本身仍为1920×1080。修正同屏尺寸窗口的策略为最大化后，实际 outer 精确达到1920×1080；较小窗口继续非最大化，auto保持最大化。没有改动探针断言或原失败报告。

镜像仍使用同一 Chromix154.0.8037.57 二进制、字体和基础桌面，仅修订启动器窗口策略。新镜像 `sha256:b8ea10d04b00484f6376e7ecb5e80ff0fbf1d3af22c4300c18cbc3c3ad0a5f43`；旧镜像 `sha256:90f757b138d096d8182b89fbacd5aa36b3a23bc17be35a677460f9878971426a` 保留。

原来源缓存精确绑定旧镜像，直接换镜像会触发 NATIVE_CACHE_CHANGED。维护工具只读原来源/缓存，显式准备 `runtimes/<新镜像SHA256>/device.json`；发布追加一份同种子修订。runner验证除image外每个字段均与原缓存相同，原缓存/种子不改，未登记镜像和篡改字段继续拒绝。每个新组合仍须完整验收，不能复用旧镜像报告。

## 已完成验证

| 场景 | 结果与范围 |
| --- | --- |
| 旧镜像原规格隔离复现 | FAIL，1919×1079；正常关闭且回收容器，保留诊断 |
| 新镜像原规格 | PASS，两独立Home各初次+10次重建，22份一致观察，另一次离线恢复；screen/window1920×1080、DPR1、语言/时区、输入、显示认证、存储和隔离网络检查通过 |
| 同Home显示切换 | PASS，1920×1080 → 1000×800 → 1920×800 → 1000×1080 → auto → 1920×1080；六次实际输入、存储和非显示特征保持 |
| auto真实客户端回归 | PASS，系统DPR、100/150/200%与复位、动态尺寸/上限/重连和输入；此报告仅0次重建，不能用于发布auto组合 |
| 1920×800独立诊断 | PASS，两Home及恢复；仅0次重建，不用于发布 |
| 发布恢复/失败保留 | PASS，新镜像同种子缓存驱动冻结runner；发布中断及写入失败后幂等恢复，原缓存/产物/报告不变；failed报告拒绝发布且不覆盖 |
| 真实Worker入口拒绝 | PASS，9项不合法摘要/时区/版本/参数/窗口/镜像/缺失产物/显示模式/尺寸配置 |
| 主机回归 | PASS，environment-engines 11、Chromix 11、冻结runner 11、作业17、模板9，共59次测试执行 |
| 限定发布 | PASS，54文件冻结runner仅4路径差异（2实现、测试、README），更新空闲执行器/Chromix目标并追加1份缓存；Adapter、控制器、生产Worker/Session、旧目录与spool均保护核对一致 |

## 原用户组合与发布范围

新任务 `job-ab3a8747c0384642` / `env-custom-ab3a8747c0384642` 复用 `fp-5abe75df16ead7dd` 与 `display-f7f83905b6bbaa1d`，只更换任务身份/时间，要求和种子保持。线上执行器于2026-10-01 17:53:07 UTC完成accepted/done：两Home各十次重建、22份观察、离线恢复及原输入/认证/存储/网络门槛全部通过，种子与原失败产物一致。环境目录、显示目录及兼容关系各追加1条；全部原条目/旧spool文件摘要及生产保护快照核对通过。旧失败任务保持failed且未发布。

没有修改已有浏览器模板绑定、Home或显示偏好。现有已验收旧组合继续引用其原镜像；本次修复影响后续Chromix生成。未新建生产浏览器，用户客户端使用新组合的反馈单列，不扩大为项目整体完成。

## 证据与恢复

私有证据根 `infra/sealskin/runtime/r6z1-chromix-window-20261001/`：baseline、build、fullscreen、auto、wide、window-modes、publication、negative、各测试日志、runner清单、cache-upgrade、deployment-inputs/after/deployment、replacement-request及final-check/final-snapshot。最终QA容器清零，磁盘约2.59GiB。真实来源/失败记录不覆盖；公开报告不含凭据或Session授权链接。

复现工具：[check-window-geometry.py](../environment-engines/check-window-geometry.py)、[check-chromix-window-modes.py](../environment-engines/check-chromix-window-modes.py)、[check-chromix-runtime-upgrade.py](../environment-engines/check-chromix-runtime-upgrade.py)。发布工具：[deploy-chromix-window.py](../environment-engines/deploy-chromix-window.py)，缓存准备：[stage-chromix-runtime.py](../environment-engines/stage-chromix-runtime.py)。

回退执行器前先取得spool锁并确认无运行任务，恢复保存的 `environment-job-before.service`，daemon-reload后启动。新旧冻结源/镜像和已验收产物保留；不删除后续用户记录、不覆盖整个目录、不停止真实浏览器。旧执行器仍不能处理原尺寸故障，回退仅用于执行器运行问题。
