# 固定版本原生引擎网络矩阵

[R6AS 工作项](../../../docs/work-items/R6AS-2026-10-02-fixed-version-matrix.md)记录当前验收进度。本运行器使用专属测试机、合成 Home、真实控制器/Guard/Relay和私有DNS/网站/代理观察器。它不启动真实恢复身份，也不修改正式Worker镜像。

准备一个被忽略的 `runtime/r6as-*` 目录，由 UID/GID 1000 的QA用户持有。按R6AP恢复说明导入精确镜像和固定QA依赖，准备 `inputs/bin/` 及每引擎的 `inputs/<engine>/entry.json`、accepted产物/验收报告。entry里的文件路径必须指向独立机上的私有副本。当前/基线Adapter二进制、控制器和Relay摘要由运行器固定检查，不使用浮动标签。

同一时间只运行一个引擎。三个引擎共用有标签的隔离控制器/观察器名称、loopback端口和受限Docker socket；上一引擎完成并清理后才准备下一引擎。每引擎按以下顺序执行（`<root>` 为绝对路径）：

```bash
python3 infra/sealskin/checks/run-fixed-version-matrix.py prepare --root <root> --engine camoufox
python3 infra/sealskin/checks/run-fixed-version-matrix.py matrix --root <root> --engine camoufox
python3 infra/sealskin/checks/run-fixed-version-matrix.py upgrade --root <root> --engine camoufox
python3 infra/sealskin/checks/run-fixed-version-matrix.py direct --root <root> --engine camoufox
python3 infra/sealskin/checks/run-fixed-version-matrix.py retire --root <root> --engine camoufox
```

另两个引擎值为 `chromix`、`firefox`。六协议为SOCKS5 none/username_password、HTTP CONNECT none/basic、HTTPS CONNECT none/basic；`matrix --cases https-basic`可只重测失败组合，新建证据目录，保留旧失败。DIRECT支持原检查器的九个阶段，失败后先查明状态和原因，再用其 `--stages` 继续；不能跳过失败断言。运行器或阶段退出不等同资源清理成功，须核验最终代次、测试容器、网络、socket和显示tmpfs。

`native-network-client.py`通过QA挂载的调试入口连接实际浏览器。就绪等待只观察端口，操作一旦可能发出便不自动重试。测试CA仅安装到合成Home的NSS库；正式launcher不含调试或证书绕过参数。Chromix按已验收的proxy-only WebRTC策略执行实际ICE尝试，并结合包观测检查旁路；Camoufox/Firefox断言WebRTC API禁用。

程序升级分三步验证：`.2`基线在线升级到R7G1/R6AR保持原Worker和数据；正常停止后以新Relay换代仍读取三类存储和固定环境；正常停止后回退旧程序仍可读取。测试固定浏览器版本，不覆盖任意跨大版本迁移。R6AR真实回退若已有非零UI Scaling偏好，还须按其发布说明先通过当前授权API复位，不能覆盖在线目录。

DIRECT使用只加入QA命名空间的公网地址夹具，另有真实互联网TLS探针；保留完整地址拒绝、DNS错误/变化、网关停止、地址证据失效、恢复、清理中断等断言。所有含账号、CA、Session或具体数据的日志保存在私有runtime；公开报告仅记录摘要与范围。

R6AS最终结果见[验收报告](../r6as-fixed-version-matrix-acceptance-2026-10-02.md)。升级工具固定的R6AR目标保留原验证版本；随后R6AS启动预算增量另由[慢启动检查器](check-slow-native-launch.py)验证：接管本项保留的Firefox unknown现场，经正常安全关闭恢复后，对两个实际启动响应各延迟50秒，验证成功、单次launch、三类存储和正常通信路径恢复，再完成余下DIRECT阶段。该工具只接受本项UID1000专属QA根，不用于真实Home。
