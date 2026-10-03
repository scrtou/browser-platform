# DEV-107 · 动态DPI与窗口变化后的输入几何核对

状态：已解决，R6S服务器验收并部署。关联[R6S](../work-items/R6S-2026-10-01-shared-display-templates.md)。

原生Firefox隔离客户端的100/150/200%缩放与重连均通过，但150%同时改成1600×900时输入焦点检查失败。初步脚本只等待screen.width与DPR，后续仍使用此前outer/inner尺寸计算坐标；不能把这个结果归结为已支持输入，也不能删掉场景。

处理：保留失败Home/日志，增加完整screen/outer/inner的连续稳定采样和点击前截图/坐标记录，再核对是采样时序还是运行端问题。要求相同缩放、尺寸变化与复位场景全部通过，失败继续诊断，不降低验收。

最终验证（2026-10-01）：稳定采样完整screen/outer/inner几何后核对点击坐标，三引擎动态尺寸、150%联动、复位和输入原场景均通过，六组合完整重建与恢复通过。 证据根为 `infra/sealskin/runtime/r6s-shared-display-20261001/`，见[R6S最终验收](../../infra/sealskin/r6s-shared-display-acceptance-2026-10-01.md)。
