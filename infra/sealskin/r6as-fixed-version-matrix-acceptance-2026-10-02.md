# R6AS · 固定版本网络与升级恢复矩阵

状态：PASS，已收尾；启动请求预算修正已部署。工作项：[R6AS](../../docs/work-items/R6AS-2026-10-02-fixed-version-matrix.md)，[复现方法](checks/fixed-version-matrix.md)。

独立Debian12/amd64机器、4CPU/16GiB，使用合成Home、accepted冻结产物与真实控制器/Guard/Relay。全部18协议组合、210项代理网络检查、66项DIRECT检查、9阶段服务器升级/回退及隔离清理通过。真实身份始终离线；独立机最终仅保留原有停止的`arm64-debian11`容器，本机生产保护快照一致。

| 固定目标 | SOCKS5 none / password | HTTP none / basic | HTTPS none / basic | DIRECT双Home | 程序升级/回退 |
| --- | --- | --- | --- | --- | --- |
| Camoufox152.0 | PASS / PASS | PASS / PASS | PASS / PASS | PASS，9阶段22项 | PASS，3阶段 |
| Chromix154.0.8037.57 | PASS / PASS | PASS / PASS | PASS / PASS | PASS，9阶段22项 | PASS，3阶段 |
| Firefox155.0.1 | PASS / PASS | PASS / PASS | PASS / PASS | PASS，9阶段22项 | PASS，3阶段 |

固定镜像：

- Camoufox：`sha256:f37c2f809411c5dfc04183dbf9ce1c109d43864036cd4b695a2a59748d83e31d`，1280×900/DPR1。
- Chromix：`sha256:b8ea10d04b00484f6376e7ecb5e80ff0fbf1d3af22c4300c18cbc3c3ad0a5f43`，1920×1080/DPR1。
- Firefox：`sha256:ae7a4e612f1655e87b50dcd24530e159a006a82a5a606254f6a3e915f95b932e`，1280×900/DPR1。

每引擎六协议70项检查（4×11 + 2×13），另有HTTP/HTTPS/WS/WSS与正常关闭/同代次恢复读回。覆盖远端DNS、认证、上游断开、Relay停止、HTTPS错误名称/非信任CA、原始旁路、包方向和环境保持。Chromix按已验收的proxy-only策略保留WebRTC API，实际ICE无未代理候选，包观测无UDP旁路；Firefox系列保持API禁用。

DIRECT九阶段覆盖真实公网TLS预检、四传输、双Home隔离、完整地址拒绝、DNS变化/错误/超时、DoH/HTTP3/WebRTC、实际固定入口复用、健康、网关/地址证据故障、控制器重建、正常关闭/同代次恢复及清理中断重试。公网地址夹具只路由到QA命名空间；没有更改宿主机路由。恢复逐次读取Cookie/localStorage/IndexedDB；失败预检不启动Worker，清理失败保留Home占用，重试后资源归零且数据保留。

## 程序与异机恢复的证据范围

三引擎程序矩阵固定浏览器版本：`.2`（R6AM/R6W/静态Relay）在线升级到R6AR/R7G1，原Worker身份、启动时间、环境及三类存储保持；正常停止后换用新Relay代次，再回退旧程序，数据/环境均保持。该9阶段证据的Adapter目标为`8fb90eb2…`；随后发现的启动预算增量按下节另行验证，不能把旧证据改写成所有新二进制场景都重跑。

原生Firefox补充异机加密检查点恢复、重开、第二检查点回退均匹配源指纹/三类存储，并通过认证显示/输入、HTTPS和原始旁路拒绝。Camoufox、Chromix、旧Work对应证据见[R6AP](r6ap-remote-recovery-acceptance-2026-10-02.md)。真实历史Home归档与当前元数据仅离线核对，不是业务时点一致的整机备份。

[R6Z1](r6z1-chromix-window-acceptance-2026-10-01.md)同浏览器版本Worker修订的同种子缓存追加、新镜像22份观察/离线恢复、发布中断/写入失败恢复及失败报告拒绝已复核。没有已验收目标的任意浏览器大版本迁移保持未验证，不能用同版本重建替代。

## 偏差修复与最终部署

[DEV-131](../../docs/deviations/DEV-2026-10-02-131-native-qa-controller-recreation.md)：QA控制器重建遗漏显示tmpfs挂载，及Chromix进程标题/renderer识别不适配。修正后保留唯一主进程PID/启动时间、显示原地址和全部恢复断言，三引擎通过。原失败保留。

[DEV-132](../../docs/deviations/DEV-2026-10-02-132-native-launch-request-budget.md)：Firefox真实启动超过普通45秒请求预算，控制器已running而Adapter正确保留unknown。将LaunchURL纳入现有180秒长操作上限；幂等键、取消、真正超时后的歧义保护和禁止盲目重发保持。旧实现被新增真实HTTP延迟测试稳定检出；候选/工作树完整Go test/vet通过。两次实际Firefox启动响应各额外延迟50秒仍成功，固定入口复用/存储、正常入口恢复及后续DIRECT健康/故障/恢复/清理全部通过。原unknown使用正常安全关闭恢复，未清空状态或删除Home。

最终Adapter为`63d88d1e152285983cc8c55ab41f1f6b2d849df51da5505139eb137041742aa0`。R6AR精确源码上仅client与新增测试两路径差异，121文件补丁重放一致；[源码增量](adapter-patches/r6as-launch-budget.patch)避免混入用户原工作树改动。部署核对运行exe、入口就绪、前后保护快照通过；控制器仍R7G1，runner仍R6Z1。回退到R6AR可只恢复程序；降到`.2`还须遵守R7G动态代次退役和R6AR非零缩放复位条件，禁止恢复旧在线目录覆盖新状态。

## 证据与边界

私有根`infra/sealskin/runtime/r6as-fixed-matrix-20261002/`保存全部成功/失败、精确输入、源码/二进制、Go日志和部署记录。Camoufox前五组合`protocols-1790947206/`、HTTPS basic`protocols-1790948379/`；Chromix完整`protocols-1790951978/`；Firefox完整`protocols-1790954495/`。DIRECT恢复/入口的失败轮次及成功重测并存。三引擎181/182/173份证据及20份Firefox异机证据回传校验；汇总器逐格验证协议、传输、恢复、22项DIRECT、3阶段程序矩阵和清理，输出`matrix-audit.json`。

商业供应方自然DNS漂移仍NOT_TESTED。当前用户客户端确认沿用既有记录，不补造历史版本或尺寸；本项是固定服务器版本的网络/升级矩阵。统一发布源码与异机程序封存由下一工作项完成。
