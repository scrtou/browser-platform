# DEV-2026-09-27-071 · R6 旧受管理策略无法进入 R7C 绑定

[R7F 工作项](../work-items/R7F-2026-09-23-production-release.md) · [偏差索引](README.md)

状态：已解决（代码/QA、生产目录绑定与新代次健康）。发现日期：2026-09-27，更新日期：2026-09-30。

## 预期

R7C 应能在浏览器已停止且资源为零时，将已存在的受管理代理代次切换到 accepted 统一代理目录修订；切换必须继续经过生命周期锁、精确 Profile/Home/Application 授权和不可变策略物化。

## 实际事实

Personal 当前仍使用 R6 生成的受管理策略 ID/SHA，但旧目录记录没有显式 `network_mode` 字段。R7C 的 `managedRecord` 只接受 `direct` 或 `proxy_required`，因此管理页的“应用代理修订”请求在真正副作用前返回未分类错误；目录 revision、应用策略和 Secret Store 均未改变。运行时已 stopped 且 records/workers/resources/relays/guards/networks 全为零。

## 决定

修复实现：对旧目录记录仅在已有非空、格式有效的受管理策略 ID/SHA 同时存在时，视为可进入一次 R7C 绑定；不为旧记录热启动或放宽网络，实际写入仍由 `setNetwork` 在同一生命周期锁内完成，并将新记录持久化为显式 `proxy_required` 及统一目录引用。没有有效策略摘要的 legacy 记录继续拒绝绑定。

## 验证与收尾

- 新增旧记录兼容绑定单元测试，覆盖无策略 legacy 仍拒绝。
- 固定 Go test/vet/gofmt/race 通过后重建 Adapter 并重载服务。
- 通过管理页原有“应用代理修订”完成 Personal 绑定，复核目录 revision、应用 policy、stopped/0 resources 和新代次 `PROXY_OK`。

2026-09-29 续跑：生产 Personal 已为 revision 9、显式 `proxy_required`，绑定 `personal-tw-socks` revision 1；当前 stopped/0 resources。目录绑定完成的事实已由[本轮报告](../../infra/sealskin/r7f-production-review-acceptance-2026-09-29.md)补齐，但因后续地址漂移，当前新代次 `PROXY_OK` 条件仍未完成，本记录不提前关闭。没有旧受管理 policy 的 Work 不属于本项兼容范围。

2026-09-30 续跑：新备份/独立恢复和当前上游探针通过后，管理页已把 Personal 绑定为 revision 10、`tw` r1，原完整应用仅改变 policy，Home/镜像保留。绑定后仍 stopped/0 resources，新代次 `PROXY_OK` 待固定入口打开后核对；详见 [Personal 恢复验收](../../infra/sealskin/r7f-personal-recovery-acceptance-2026-09-30.md)。

用户随后确认打开，14:58 UTC Personal revision 12、新代次 1 Worker/5 resources，`overall=healthy`、`PROXY_OK`、浏览器/显示/新鲜度通过；Worker 经 Relay 的域名/TLS/HTTPS 和有效原始绕过拒绝通过。原完整应用仅改变 policy，Home/镜像保留，旧策略未删除。结合既有代码/QA 和实际旧目录转为显式网络模式的绑定证据，本项完成条件已达到。浏览器 GUI、登录/数据及目标客户端仍归 R7F，不因本偏差关闭而视为通过。
