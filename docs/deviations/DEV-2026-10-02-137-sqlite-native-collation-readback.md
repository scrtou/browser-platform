# DEV-137 · 浏览器数据库的原生排序规则读回边界

状态：已解决（R6AU最终验收通过）。关联：[R6AU](../work-items/R6AU-2026-10-02-consistent-business-backup.md)。

真实恢复文件逐文件一致；通用Python SQLite对Firefox的suggest.sqlite执行quick_check时报告缺少geonames_collate。该规则由Firefox原生组件提供，不能安装虚假的比较函数后声称索引完整性通过。此前未转义SQLite URI也会令带特殊字符的文件无法打开，读回器已使用Path.as_uri。

早期诊断尝试（未采用）：曾尝试以NOT INDEXED扫描并记录NATIVE_COLLATION_REQUIRED；WITHOUT ROWID表仍需要声明规则，且此方式不能维持原quick_check门槛。失败记录保留，最终采用下文严格方案。原Home未修改，恢复副本的浏览器启动另外验证。

这一界定用于区分完整备份/数据可读性与通用SQLite无法提供的Firefox原生索引校验，不降低密文认证、源前后静止、完整文件及一般数据库错误的验证门槛。最终验收必须公开列出数量与限制。

补充：Debian12系统SQLite 3.40不支持Firefox数据库的FTS5 contentless_delete选项；实际Controller内SQLite为3.53.4。读回器须在处理前明确检查SQLite≥3.43；独立机使用独立目录中固定SHA的pysqlite3-binary 0.5.4.post2，不修改系统SQLite。此版本差异与缺少原生排序规则分别记录。

最终采用的严格读回方式：Mozilla Suggest注册geonames_collate和i18n_collate，WITHOUT ROWID主键表仅准备查询也需要名字存在。恢复器为这两个名字登记“调用即失败”的处理器，绝不返回虚构比较结果；quick_check和逐表扫描都必须实际成功且调用计数严格为0。实测该数据库quick_check=ok、28表/204,668行读取、比较调用0。此前降为NATIVE_COLLATION_REQUIRED的纯扫描尝试未采用；普通数据库和原生声明数据库都保留quick_check=ok的原门槛。quick_check本身不等于原生索引排序语义的完整验收，任何需要真实比较的检查继续拒绝。

最终验证：[R6AU验收](../../infra/sealskin/r6au-consistent-business-backup-acceptance-2026-10-02.md)通过，本文早期失败/待验段落保留其时点。完整归档恢复、数据库/授权读回、原安全配置下三份断网浏览器启动/正常关闭、生产恢复和临时清理均完成。
