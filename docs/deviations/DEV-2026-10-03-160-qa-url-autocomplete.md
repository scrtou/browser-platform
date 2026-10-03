# DEV-160 · 恢复QA的URL前缀触发浏览器自动补全

状态：QA修正待验证。关联 [R6AX](../work-items/R6AX-2026-10-03-v1-release.md)。

services attempt2已恢复Firefox显示，但正常关闭后的预期URL不存在。输入截图明确显示`firefox-services`被地址栏补全为旧`firefox-services-warm`，`-warm`处于自动补全选中状态；按Enter接受旧地址。SQLite中原initial/warm数据完好，故此失败不证明恢复丢失数据，也不能据此忽略最终输入门槛。

修订QA：初始基准URL保持，后续每次写入使用带随机后缀的独立标记，运行中重启前的标记写入私有记录，重启后必须核对当次具体标记而非复用旧warm文本。不修改浏览器偏好/生产输入实现，不删除原历史。重新执行有活动Firefox的服务重启，再验证三Home的新增和历史数据；原services1/2截图、日志及失败保留。
