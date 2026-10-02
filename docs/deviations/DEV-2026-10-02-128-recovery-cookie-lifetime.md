# DEV-128 · 灾备 QA Cookie 有效期不足

状态：已解决（2026-10-02，异机实测通过）。关联 [R6AP](../work-items/R6AP-2026-10-02-remote-recovery.md)。

独立机器恢复要求验证三类存储。R6K 合成 Work 检查点使用 `Max-Age=86400`，该历史 Cookie 在本轮跨机恢复时已过期。localStorage 与 IndexedDB 精确读回，Cookie 被浏览器正常过期清理；这是测试夹具不能支持跨日保存的缺口，不是备份格式丢失数据。

选择修复夹具：迁移 QA 与原生回放共用存储脚本的专用 sentinel Cookie 有效期改为一年；在源主机的全新隔离 QA 根正常启动浏览器、通过浏览器 API 写入 sentinel、正常停止并产生新加密检查点。保留原历史密文与过期失败证据，不修改归档内 Cookie 数据库、不调整系统时间、不降低三类存储断言、不触及真实网站 Cookie。

原归档内 Firefox 155 的 `moz_cookies.expiry` 单位为毫秒；按 Unix 毫秒与异机当前时间比较确认已经到期，不能误当秒值而判断仍有效。

新检查点须在独立机器再次认证、激活并完成真实读回/回退后才关闭本项。更新 Work QA 工具、恢复说明、R6AP 验收/工作项和偏差索引。

最终：R6AP 修复后的真实异机验收通过，原失败保留，见[R6AP 验收](../../infra/sealskin/r6ap-remote-recovery-acceptance-2026-10-02.md)。
