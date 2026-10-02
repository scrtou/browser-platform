# DEV-141 · 旧浏览器缺少环境目录字段，正常归档被拒绝

状态：已解决（R6AV部署与最终验收通过）。关联：[R6AV](../work-items/R6AV-2026-10-02-test-data-cleanup.md)。

两个新测试浏览器已正常归档删除。Personal已正常停止并进入deleting，但客户端在提交Home归档前拒绝空environment_artifact_id；旧Work也未记录此字段。旧浏览器定义本来允许缺少环境目录绑定，删除实现却无条件要求已记录的环境ID，此前仅测试了新建浏览器归档。

选择修复实现并明确旧数据表示：归档v1请求/manifest保持非空字符串契约；仅对原定义完全未记录环境/浏览器/显示模板ID的旧浏览器，用保留值`legacy-unrecorded`明确表示“未记录环境产物”，它不是accepted产物或可恢复模板。原Home、应用、Profile修订与actor仍是实际绑定，不补造验收、改写原目录或更换Home。正常已记录产物的归档保留原ID。

补齐旧定义的失败保留、同名幂等重试和正常已记录ID不变测试；修正正常删除实现后重新构建部署，并沿Personal既有deleting记录继续。Controller归档锁、零资源、目录边界、精确manifest重试和原子移动均保持，不能通过直接移动Home绕过。

私有证据：R6AV的cleanup-apply.log、cleanup-retry-private-error.txt和当前目录；原失败保留，完整清理尚未完成。

最终结果：[R6AV验收](../../infra/sealskin/r6av-test-cleanup-acceptance-2026-10-02.md)通过；代码回归、部署、实际数据清理及独立程序留存均完成。以上早期未完成状态保留过程时点，原失败日志未改写。
