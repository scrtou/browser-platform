# DEV-105 · 空模板目录发布失败

状态：已解决并部署。关联 [R6R](../work-items/R6R-2026-10-01-multi-engine-generation.md)。

完整 Chromix 重放已通过，但首次发布到 Go 序列化的空目录失败：display_templates/compatibility 为 null，Python 直接迭代而报错。environment 条目已写入，accepted 报告未损坏。

处理：发布时将这两个合法空列表的 null 规范为 []，其他非列表类型仍拒绝。保留失败状态快照和验收字节，通过显式 retry 恢复发布；不得覆盖报告或重抽指纹。补真实发布恢复验收。

复核同时补齐 native 分派捕获既有 JobError：目录 ID 冲突等稳定错误写入 failed 状态，不让 runner 退出并留下 running。真实冲突检查要求原目录和产物/报告字节全部保留。

结果：R6R最终固定镜像/源码的相关完整验收与拒绝/恢复检查通过，限定部署完成；详见[R6R验收](../../infra/sealskin/r6r-multi-engine-acceptance-2026-10-01.md)。原失败证据保留，能力边界未降低。
