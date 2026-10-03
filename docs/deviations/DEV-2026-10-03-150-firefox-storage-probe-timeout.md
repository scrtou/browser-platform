# DEV-150 · Firefox首次存储探针响应超时

状态：诊断中。关联[R6AW](../work-items/R6AW-2026-10-02-protected-builtins.md)。

v6独立机US自动Firefox任务`job-1391abd1e3698824`在A-0首次读取Cookie/localStorage/IndexedDB时，BiDi连接等待响应15秒后超时；尚无有效观察，任务正确保留failed。此前初始HTTPS页面标题和地址检查已完成，失败后浏览器正常关闭。原Home及探针/Worker日志保留，不以新任务覆盖旧报告。

这与DEV-148键盘输入和DEV-149正常退出超时的触发点不同。当前证据不能判断为IndexedDB阻塞、页面生命周期竞态或宿主延迟，不把原时点未记录的原因写成结论。镜像冷导入此时已经结束。

处理选择：先在同镜像、同冻结产物、新合成Home中记录存储阶段及响应耗时，保持原验收的15秒连接与完整存储断言；诊断不计为accepted。确定原因或明确故障边界后，新建正常完整任务，保留原失败。生产不受本诊断影响，R6AW继续未部署。

私有材料：独立机R6AW根`matrix-v6/jobs/artifacts/env-custom-1391abd1e3698824/native-qa/`及对应作业evidence；后续诊断另存独立根。
