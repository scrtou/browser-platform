# DEV-138 · 恢复依赖检查误把内核视图当作持久文件

状态：已解决（R6AU最终验收通过）。关联：[R6AU](../work-items/R6AU-2026-10-02-consistent-business-backup.md)。

异机完成文件/SQLite读回后，挂载闭包检查拒绝DIRECT Relay的`/proc/1/net/fib_trie`。生命周期实现明确要求只读挂载当前宿主机内核地址视图；它不是应封存的业务文件，也不能用旧主机的普通文件替代。备份数据未丢失，此次错误来自读回器把所有挂载都当作持久输入。

处理：仅识别Relay上精确源`/proc/1/net/fib_trie`、精确目标`/run/browser-platform-host/ipv4-fib-trie`且只读的bind挂载，记录为新主机必须重新提供的内核依赖；其他未闭合依赖仍拒绝。旧代次租约/显示秘密由正常生命周期重新生成，不恢复旧Session。离线真实Home启动不启动Relay或赋予任何外网。

证据保存在R6AU私有运行目录；完整读回、凭据授权及离线Worker验证通过后再收尾。

最终验证：[R6AU验收](../../infra/sealskin/r6au-consistent-business-backup-acceptance-2026-10-02.md)通过，本文早期失败/待验段落保留其时点。完整归档恢复、数据库/授权读回、原安全配置下三份断网浏览器启动/正常关闭、生产恢复和临时清理均完成。
