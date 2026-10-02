# DEV-134 · 整体备份未覆盖作业内合法符号链接

状态：已解决（R6AU最终验收通过）。关联：[R6AU](../work-items/R6AU-2026-10-02-consistent-business-backup.md)。

完整spool必须保留accepted/failed作业及其验收副本。首次真实静止盘点发现jobs/artifacts内native-qa字体缓存含相对符号链接；工具仅允许storage/assets链接，拒绝了这部分真实输入，未生成归档。不能删除作业副本或跳过它们来通过验收。

处理：允许显式jobs根下的链接以链接文本封存，继续禁止跟随、链接父节点、越界归档和覆盖目标；增加真实往返与防穿越测试，再完整盘点并重试。证据为R6AU私有backup-create.log和停止检查点。

实现与本轮验证：jobs链接保持文本且不跟随；本机/独立机各10项真实age验证通过，第二次17,539条目整体加密成功。异机实际恢复待最终核对后收尾。

最终验证：[R6AU验收](../../infra/sealskin/r6au-consistent-business-backup-acceptance-2026-10-02.md)通过，本文早期失败/待验段落保留其时点。完整归档恢复、数据库/授权读回、原安全配置下三份断网浏览器启动/正常关闭、生产恢复和临时清理均完成。
