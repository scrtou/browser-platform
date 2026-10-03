# R6L · Chromix 接入验收 · 2026-10-01

状态：隔离接入验收及服务器部署通过。真实用户客户端和生产新 Home 尚未验证。

## 固定版本

- Chromix 154.0.8037.57 Linux x64，源码 `3b338c8bfda663d597d383d24f8fc20870d219e4`；包 SHA-256 `9b769a5b151b0778a42e6883dd12454817fcd0bef0268b1a93008b25052e0669`。
- 最终 Worker：`sha256:cd521d91037af114833f9df994e3242c4d6078859212909c586b412da660a3ae`。基础层来自当前固定桌面镜像，继承 Session 认证并替换入口/启动/退出实现。
- 控制器保持 R6J1：`sha256:ad21dd6de070fce88e59a6c32fd213c017fcb587dffd3cac907693cb7b3b6525`。
- 已部署 Adapter：`fbaad2a9a383ace004b4f5253444eeb85dc2bbc9c70c960c1e919c482ce2f6d0`。从现行生产源码快照仅修改 template_catalog.go 并增加 Chromix 测试，不包含未部署的 R7G/R6I。

## 结果

| 场景 | 结果与边界 |
| --- | --- |
| 发布物 | 固定归档和执行文件摘要通过；上游未完成 runtime/fingerprint 的事实保留 |
| 沙箱 | 非 root、no-new-privileges、自定义受限 seccomp 下实际运行；不关闭 Chromium 沙箱 |
| 完整 Worker | /init、X11、正确/错误显示认证、正常关闭通过 |
| 固定环境 | 实测 Linux、en-US、UTC、1280×720、DPR 1；默认简化 UA 与实际版本分开记录 |
| DIRECT | 经独立受管理网关访问公有 HTTPS；四类绕过拒绝，网关故障后仍拒绝 |
| 认证代理 | 独立认证 SOCKS5 和私有 HTTPS 通过；仅 QA 用精确叶证书 SPKI；上游故障无直连 |
| 持久化 | 两条网络路径分别正常停止/新代次，Cookie/localStorage/IndexedDB 与种子保持 |
| 入口 | 未登录拒绝、管理员登录/近期确认、启动计划、Session 主机显示交接、新鲜 healthy 和正常停止通过 |
| 管理创建 | 实际模板 JSON/管理表单创建独立 Home；正式应用无 CDP 调试参数，Session/健康/正常停止通过 |
| 关闭拒绝 | beforeunload 场景停止超时，原 Worker/Home/资源保持；取消并清除测试处理器后正常重试通过 |
| 加密恢复 | 停止清零后 age 归档、独立解密/内容比对；文件权限由密文 tar 元数据恢复。原 Home 移走后激活副本，新 Worker 读回三类数据及种子一致 |
| 回归 | 7 项 Python 测试；当前仓库完整 Go 测试/vet及最终 Profile 回归；最小生产候选完整 Go 测试/vet通过 |
| 清理与保持 | QA 容器/网络/进程/临时显示目录已清理；部署前生产容器、配置和 Adapter 摘要与原基线一致 |

早期候选的继承入口和目录权限失败分别见 [DEV-089](../../docs/deviations/DEV-2026-10-01-089-chromix-inherited-entrypoint.md)、[DEV-090](../../docs/deviations/DEV-2026-10-01-090-chromix-package-directory-mode.md)。QA 初次未创建 Home、目录权限、账号授权变更后的重登录、启动观察时序和测试扫描器误判等失败保留于私有日志；不是生产故障。

## 证据及未测范围

被忽略的 `runtime/r6l-chromix-20261001/` 保留发布 provenance、包/镜像清单、原始失败日志、worker-qa-3、integration 下 DIRECT/proxy/entry/management/recovery 结果、加密 Home 与清理回执、最小 Adapter 源码及部署前快照。密码、Cookie、私钥和授权 URL 不进入公开记录。

本次只验收首个固定 Linux 模板及选定 QA Home。完整 GPU/Canvas/音频/字体跨接口一致性、跨 OS 设备模拟、其他 locale/timezone/display 组合、Chromix 自定义产物作业、全部 HTTP/HTTPS 上游组合、异机/整机恢复和目标 Mac 客户端未测。该结果不代表网站风控保证，也不替代 R6K 异机灾备。

[操作说明](../chromix/README.md) · [工作项](../../docs/work-items/R6L-2026-10-01-chromix.md)

## 生产部署复核

`deployment-result.json` 与 `postdeployment-result.json` 均 PASS：最小 Adapter 已安装，两个原目录追加 Chromix 条目，控制器保持 R6J1。Personal/Work 新鲜 healthy；“测试”保持用户主动关闭后的 BROWSER_EXITED。原 Worker/Relay/Guard ID 和启动时间、Session/operation 绑定保持，监控定时器 active。公网管理入口返回预期登录重定向。

首次检查的 localhost Host 被正确拒绝为 421，已自动恢复原二进制/目录；修正脚本从 public_base_url 派生 Host 后重试成功，见 [DEV-091](../../docs/deviations/DEV-2026-10-01-091-deployment-readiness-host.md)。原失败回执 `deployment-rolled-back.json` 和精确回退材料保留。

全部 QA 容器/网络/进程/显示 tmpfs 清理，安装包 tmpfs 已移除，最终可用磁盘 8,153,370,624 bytes（约 7.6 GiB）。没有创建生产 Chromix Home，也没有重建任何原生产浏览器。最终私有 `final-manifest.json` 记录代码、文档及证据的文件摘要；它不是包含镜像层与独立密钥的异机恢复包。

## 首个生产实例用户反馈

用户选择配套 Chromix 浏览器/指纹/显示与受管理 DIRECT；初次收到通用错误，随后自行重新提交并确认“创建好了，并且打开成功”。首次生产创建/打开有用户证据，不能扩大为目标客户端全部交互或数据恢复通过。原错误类型日志不足以确定失败原因；表单改进 DEV-092 待后续，本轮未部署补丁或重启服务。后续私有证据在 `runtime/r6l1-create-20261001/`。

只读强制探测：首个 Chromix、Personal、Work 均为新鲜 healthy，Adapter 摘要仍为 R6L 原部署值；见私有 `verification.json`。本轮没有维护现有浏览器。
