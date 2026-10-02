# DEV-139 · 离线恢复脚本遗漏原Worker安全配置

状态：已解决（R6AU最终验收通过）。关联：[R6AU](../work-items/R6AU-2026-10-02-consistent-business-backup.md)。

首次异机真实Home副本启动时，Chromix进程未保持运行。原Worker使用固定seccomp规则允许Chromium用户命名空间沙箱；恢复脚本仅带no-new-privileges，并把各Worker统一限制为1GiB，未完整重放已归档的安全与资源设置。原始Home、镜像和配置文件校验均通过，问题在离线启动器。

处理：从归档容器配置读取原有seccomp JSON并作为私有文件交给Docker CLI，保留no-new-privileges、能力限制、内存/CPU/PID和共享内存设置。继续强制network none、零公开端口、独立Home副本和合成显示凭据；不使用no-sandbox或privileged。先正常关闭/删除失败的指定QA容器，保留其失败副本和日志，再创建新副本重试。

验证必须包含实际浏览器进程持续运行、显示认证、无路由和正常关闭；容器running不作为通过。证据位于R6AU私有运行目录。

最终验证：[R6AU验收](../../infra/sealskin/r6au-consistent-business-backup-acceptance-2026-10-02.md)通过，本文早期失败/待验段落保留其时点。完整归档恢复、数据库/授权读回、原安全配置下三份断网浏览器启动/正常关闭、生产恢复和临时清理均完成。
