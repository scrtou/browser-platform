# DEV-2026-09-20-058 · R4B 只读生产检查器与 R6F 控制器 overlay 漂移

状态：已解决（保留历史检查器严格绑定，以当前 overlay 明确手工证据验收）。关联工作项：[R6F](../work-items/R6F-2026-09-19-release-combination.md)。

## 预期

`check-r4b-production-live.py` 用于 R4B `release-ready-2` 基线的只读生产复核，应核对当时冻结的 SealSkin 控制器镜像、两 Profile 的运行数量、入口边界和文件权限；检查通过时才生成脱敏 `result.json`。

## 实际事实

- R6F 已在现有生产 Compose 上安装 `r6f-existing-overlay-recheck`，当前 `sealskin` 容器仍运行且服务健康，但镜像为该 R6F overlay。
- 2026-09-20 只读运行 R4B 检查器时，在服务、Adapter、Profile 和入口检查之前于控制器镜像比对处拒绝，输出 `production controller drift`；未写出结果文件，也未改变生产资源。
- 检查器期望的 R4B 镜像与当前 R6F overlay 不同，因此该拒绝表示检查器绑定的是历史 R4B 基线，不表示当前控制器已经故障。

## 影响

R4B 检查器不能作为 R6F overlay 部署后的完整生产 PASS 证据。此前 R4B 的 `live-check-1` 历史结论仍保持其原版本范围；当前 R6F 仅能依据已记录的 overlay 安装、health/ready、Profile inspect/health、Home 备份与用户客户端确认，不能把旧检查器拒绝扩大为当前服务失败，也不能把手工核对写成自动化检查通过。

## 处理与后续

- 保留 R4B 检查器的严格历史镜像绑定，不放宽为接受任意当前镜像。
- 运维说明明确该检查器只适用于 R4B 基线；R6F 需要单独的版本/overlay 感知只读检查器，或在后续工作项中重新绑定当前候选后再验收。
- R6F 后续已在明确授权下完成当前 overlay 的 health/ready、Profile inspect/health、Personal/Work 完整停启矩阵、实际可逆回退、真实 Mac 自定义 artifact 和清理证据；因此本偏差按“保留历史检查器、采用当前版本明确手工证据”解决。未改写或放宽 R4B 检查器，也不宣称其对 R6F overlay 通过。
