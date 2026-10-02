# DEV-135 · 异常恢复未等待Controller就绪

状态：已解决（R6AU最终验收通过）。关联：[R6AU](../work-items/R6AU-2026-10-02-consistent-business-backup.md)。

首次整体备份失败后，维护脚本执行docker start即顺序调用三个Profile的离线启动；控制器尚未完成初始化，操作器全部拒绝。服务恢复不等于浏览器恢复，三个Home均保留，journal仍为stopped。

处理：先通过受认证控制API核对Controller就绪和当前运行范围，再重开原活动Profile；维护正常与异常恢复都使用同一就绪门槛。记录每项失败，并验证新鲜完整健康后才声明生产恢复。原始日志与检查点保留在R6AU私有目录，不覆盖journal。

二次观测：Controller客户端建立期间TLS尚未就绪，同样可能抛错；已将建立客户端和请求均放进有界重试。对实际函数验证初始化短暂失败、API短暂失败和持续失败三种场景；两次故障后的手动恢复均经认证就绪检查并得到3个原活动Profile的fresh healthy。原始失败保留，不把启动容器等同于就绪。

最终验证：[R6AU验收](../../infra/sealskin/r6au-consistent-business-backup-acceptance-2026-10-02.md)通过，本文早期失败/待验段落保留其时点。完整归档恢复、数据库/授权读回、原安全配置下三份断网浏览器启动/正常关闭、生产恢复和临时清理均完成。
