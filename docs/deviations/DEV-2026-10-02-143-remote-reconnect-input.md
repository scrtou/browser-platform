# DEV-143 · 独立机自动显示重连输入未通过

状态：诊断中。关联[R6AW](../work-items/R6AW-2026-10-02-protected-builtins.md)。

非rootQA已正常启动Camoufox和显示端，首个US自动显示任务在真实Selkies重连后报告RECONNECT_INPUT_FAILED。浏览器已正常关闭并释放QA容器，原来源缓存、失败报告/截图和Home保留。来源/显示组合尚未accepted，不能以启动成功代替验收。

诊断证据：独立机`/srv/r6aw-protected-builtins-20261002/qa/jobs/artifacts/env-custom-a02970286f18b998/native-qa/`，以及任务evidence。原探针在已观察焦点后发送一次文本，固定等待500ms再判定值，但没有保存失败的实际文本和焦点状态；目前不能判断是输入丢失、时序还是运行端问题。

处理计划：先增加只读诊断记录（实际输入值、远端焦点、客户端几何及传输状态），用同一冻结产物的独立合成Home重现。保持原文字精确匹配、实际输入和完整24组合门槛；修复后新作业重跑，失败报告不覆盖。
