# DEV-2026-09-14-008 · 恢复后未读到 QA localStorage 标记

状态：已解决（代码/隔离 QA，未部署）。发现与解决日期：2026-09-14。关联工作项：[R5A](../work-items/R5A-2026-09-14-proxy-protocols.md)。

## 预期与实测

R5A 的 HTTPS Basic 原代次恢复检查要求已写入的 QA Home 标记可恢复，沿用 [R2](../work-items/R2-2026-09-13-boot-recovery.md) 与 [规格 E03](../specs/proxy-environment/specification.md#467-环境验收) 的持久化边界。

`runtime/r5a-proxy-protocols-2026-09-14/matrix-v4/https-basic/resume-api.json` 记录：离线上游时 resume 返回 503 且 Worker 保持退出，恢复上游后原 Worker/Guard/Relay 按序恢复。随后 `localStorage.getItem('proxy-resume')` 未匹配写入值；独立页面观测为 `https://entry.leak.qa.test/test`、标记不存在、存储键为空，原 Home 挂载仍在。记录位于同目录 `post-failure-browser.json`。写入时的页面 origin 和磁盘提交状态尚未留证，不能提前断言是哪一层丢失了数据。

## 影响与处理决定

独立诊断 `storage-stop-probe.json` 已确认：在明确的 HTTPS origin 写入新标记并立即读回，随后只停止 QA Worker（30 秒上限，实际 3.49 秒，容器退出码 0），旧标记恢复、新标记缺失。停止后的真实 LSNG 数据库 `storage/default/https+++entry.leak.qa.test/ls/data.sqlite` 也只有旧标记。先前对旧 `webappsstore.sqlite` 的采样不适用于此浏览器；运行中 LSNG 的独占锁也不能解释为数据不存在。

固定基础镜像的 `svc-de/finish` 同时向桌面的全部后代进程发送 TERM，包括浏览器父进程和内容/存储子进程；现有停止路径没有先等待浏览器完成正常退出。`storage-parent-term-probe-v2.json` 进一步确认仅向浏览器父进程发 TERM 仍丢失最近一次写入；`storage-window-close-probe.json` 使用应用正常退出后立即停止容器，新旧标记均恢复。因此处理选择为修复正常退出路径，不增加写入后的任意等待。

在 R5A 内加入版本化 Worker 退出层：在桌面和 X11 仍运行时向已核对的浏览器窗口发送关闭请求，等待浏览器退出；SealSkin 显式 stop 在退出无法确认时保留容器/占用并返回失败。容器本身的停止钩子在桌面清理前执行相同动作。新 Worker 使用新内容镜像和匹配的 Camoufox 产物/验收，不修改旧镜像、冻结产物或生产实例。崩溃、强制终止和宿主机断电不能被宣称具有正常退出保证。

持久化断言保持不变；已有 R4A 较长运行后的数据恢复证据不扩大为本场景通过。

首版退出层的直接关闭对照通过，但 `matrix-v6` 的容器停止仍丢失新标记，即使钩子输出 `BROWSER_SHUTDOWN_CONFIRMED`。原实现放在 longrun 的 `finish`，它不能作为桌面依赖停止前的屏障。继续修复为依赖桌面和 D-Bus 的 s6-rc oneshot `down` 动作，在服务图中先完成浏览器关闭，再允许桌面/X11 退出；保留 r5 候选及失败证据，使用新镜像/产物修订继续验证。不把进程消失或钩子返回成功当作数据已保存的充分证据。

上述失败当时阻断 R5A 恢复项与收尾；后续以 r6 完成下列复核。全过程只使用独立 QA Home，生产浏览器和真实数据未操作。

## 最终复核

最终 Worker 为 `browser-platform/camoufox:0.5.6-beta.30-r6-c73fa18044baad73`，控制 payload 为 `0.3.2-proxy-v1-f921ceefcf1e0250`。s6-rc oneshot 依赖 `svc-de` 和 `svc-dbus`，其 down 动作先完成浏览器关闭，再允许桌面依赖退出；原 `svc-de/finish` 保持不变。

- `matrix-v7/https-basic/resume.json`：即时写入并读回 localStorage 后执行真实 `docker stop -t 30`；上游离线时恢复返回 503、Worker 保持停止；上游恢复后同一 Worker/Guard/Relay 按序恢复，新标记仍在，PASS。
- `browser-shutdown-v2/shutdown-results.json`：网页阻止关闭时返回 503 且保留 Worker/Guard/Relay/占用；取消对话框后重试；即时 Cookie/localStorage/IndexedDB 经 API stop 和同 Home 新 Worker 全部恢复，最后资源清空，PASS。
- `infra/camoufox/evidence/acceptance-r6-2026-09-14.json`：17 项产物测试、11 类启动拒绝、两个独立 QA Home 各 10 次删除重建及同版本离线恢复通过。r6 只增加退出层，原 r4 浏览器、冻结配置与 seeds 未变。

证据路径除完整 Camoufox 报告外均相对私有 `infra/sealskin/runtime/r5a-proxy-protocols-2026-09-14/`。失败的 TERM、r5 finish 与 matrix-v4/v6 记录继续保留。设计、规格 50.3、退出层/生命周期说明及 [R5A 验收](../../infra/sealskin/proxy-protocols-acceptance-2026-09-14.md) 同步最终契约；未扩大为旧 Worker、强制终止或正式主机停止窗口的保证。
