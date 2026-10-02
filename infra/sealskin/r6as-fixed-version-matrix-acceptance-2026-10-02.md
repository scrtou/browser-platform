# R6AS · 固定版本网络与升级恢复矩阵

状态：进行中，尚未完成全矩阵和清理。工作项：[R6AS](../../docs/work-items/R6AS-2026-10-02-fixed-version-matrix.md)；[复现方法](checks/fixed-version-matrix.md)。

用户授权的独立Debian12/amd64机器，4CPU/16GiB；真实恢复身份保持离线。每个引擎使用独立合成Home、已验收冻结产物、固定镜像及真实控制器/Guard/Relay。现行生产为R7G1控制器与R6AR Adapter；测试不变更生产浏览器/会话/数据。

| 固定目标 | SOCKS5 none / password | HTTP none / basic | HTTPS none / basic | DIRECT双Home | 程序升级/回退 |
| --- | --- | --- | --- | --- | --- |
| Camoufox152.0 | PASS / PASS | PASS / PASS | PASS / PASS | PASS，9阶段 | PASS，3阶段 |
| Chromix154.0.8037.57 | 待验收 | 待验收 | 待验收 | 待验收 | 待验收 |
| Firefox155.0.1 | 待验收 | 待验收 | 待验收 | 待验收 | 待验收 |

固定镜像：

- Camoufox：`sha256:f37c2f809411c5dfc04183dbf9ce1c109d43864036cd4b695a2a59748d83e31d`，1280×900/DPR1。
- Chromix：`sha256:b8ea10d04b00484f6376e7ecb5e80ff0fbf1d3af22c4300c18cbc3c3ad0a5f43`，1920×1080/DPR1。
- Firefox：`sha256:ae7a4e612f1655e87b50dcd24530e159a006a82a5a606254f6a3e915f95b932e`，1280×900/DPR1。

六协议每引擎要求70项实际网络检查（4×11 + 2×13），另有HTTP/HTTPS/WS/WSS、正常关闭/同代次恢复和最近写入读回。涵盖远端DNS、协议/认证、上游断开、Relay停止、HTTPS错误名称/非信任CA、Worker/Relay旁路、包方向、环境保持。Chromix保留WebRTC API、禁止未代理UDP；实际ICE尝试和包观测必须验证此契约，不能沿用Firefox系列的API禁用断言。

程序矩阵固定浏览器版本，旧程序为`.2`（R6AM Adapter/R6W控制器/静态Relay），新程序为R6AR/R7G1。实际Adapter入口启动、Cookie/localStorage/IndexedDB写入后在线升级，验证Worker身份/启动时间/环境/数据保持；正常关闭并换用新Relay代次，再回退旧程序，均须读回原数据。执行后恢复QA当前程序，不恢复旧业务目录覆盖新状态。非零UI Scaling的真实降级前置仍按R6AR执行。

原生Firefox补充异机恢复已通过：源机合成Home正常关闭并加密传输，独立机恢复/重开/第二检查点回退均匹配源指纹及三类存储，并通过认证显示/输入、HTTPS和原始旁路拒绝。Camoufox、Chromix及旧Work的对应异机证据引用[R6AP](r6ap-remote-recovery-acceptance-2026-10-02.md)。真实历史Home归档与当前元数据只作离线依赖核对，不是业务时点一致的整机备份。

[R6Z1](r6z1-chromix-window-acceptance-2026-10-01.md)同浏览器版本修订已复核：同种子缓存追加、新镜像22份观察/离线恢复，以及发布中断/写入失败重试和失败报告拒绝。原来源/种子/失败记录保持。该证据不表示任意旧Home跨浏览器大版本迁移；没有已验收目标的大版本仍不支持自动替换。

详细证据在被忽略的 `infra/sealskin/runtime/r6as-fixed-matrix-20261002/`。Camoufox前五组完整成功位于 `protocols-1790947206/`，HTTPS basic最终成功位于 `protocols-1790948379/`；原恢复就绪时序失败保留。只增加调试端口的只读等待，未重发可能已经执行的操作。商业供应方自然DNS漂移仍NOT_TESTED，不用私有夹具冒充真实供应方。

Camoufox DIRECT原恢复轮次因QA重建工具遗漏显示tmpfs挂载失败，见[DEV-131](../../docs/deviations/DEV-2026-10-02-131-native-qa-controller-recreation.md)。保留原失败，修正后重测恢复/清理：控制器重建保持浏览器进程与显示连接、同代次恢复读取三类存储、两个失败预检不启动Worker、清理中断保留占用且重试成功。
