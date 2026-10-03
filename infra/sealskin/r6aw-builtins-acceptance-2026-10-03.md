# R6AW · 内置模板与24组合验收

状态：已通过并部署（2026-10-03）。[R6AW工作项](../../docs/work-items/R6AW-2026-10-02-protected-builtins.md)已达到本项范围；1.0统一整理、全新部署及定版仍是下一项，不由本记录提前宣告完成。

## 最终交付

可见指纹仅通用US/TW/JP/CN四个，显示仅自动分辨率/DPR随缩放变化与固定1920×1080/DPR1两个，三引擎共24个受保护accepted组合。内置来源和安装组合不可经UI/API删除；后续普通自定义来源/组合保持原能力，不自动成为内置。

| 组件 | 固定身份 |
| --- | --- |
| Adapter | `f0526e3a6950b28528055aea5d9e24bd36d049709c773009c26269883f5d232d` |
| Camoufox 152.0 | `sha256:be475a9fbe6cfc9c1768c95ebd8f8d83da22b05297498abb7c82f70e6ceea2c1` |
| Chromix 154.0.8037.57 | `sha256:cf0e51426b6f59769af7486f9e09340387ed69b3ccc33d5a47c792280bdcc730` |
| Firefox 155.0.1 | `sha256:d9c8c8737dc19f110eac9b7b3676faf01eac2a6925ae3c5aa27f696ad83fca2e` |
| v6源码审阅提交 | `6bffe240452d8b0e1016ee7844d016cb702bdc92`（195文件固定候选） |
| 内置包manifest SHA256 | `181250e4bf8dd621fd5a8bed500e324b8485be5825decec0129dd53d4b6e39ed` |

最终打包/目录关联工具另有提交`0934fb6`，不改变上述受测镜像或执行器。控制器保持R7G1；生产生成服务改用R6AW固定源码、目标表与上述镜像。

## 实际验收

- 24项全部按两个独立Home、每Home十次重建、完整指纹/存储/网络观察及离线恢复通过，共528份观察。自动显示还包括真实Selkies客户端的尺寸变化、DPR1/2重连、3840×2160上限、100/150/200%缩放与复位、截图、点击和精确键盘输入。
- 固定Camoufox另有四份同产物正常桌面完整报告，共88份观察及四次离线恢复；原无头报告同时保留。内置包缺少任一桌面补证即拒绝。
- 本机完成固定12项、JP/CN自动六项及US/TW自动Firefox两项；独立Debian12机器完成US/TW自动Camoufox/Chromix四项。五份分片使用相同12份来源/引擎设备缓存（16文件）及精确镜像；528份原报告字节汇总不改。QA Worker保持1.5CPU/1536MiB；合成客户端独立2CPU/3GiB、1GiB临时目录。
- 前置Go test/vet、内置/删除/初始化并发race、11项Python来源、17项作业及4项初始文档就绪检查通过；键盘进程六项检查、实际固定上游方法对照和真实延迟注入通过。尺寸换算旧JS复现回归，新JS原尺寸/DPR场景通过。
- 真实包78个清单文件（含manifest共79文件）通过来源、显示、目标、缓存设备、产物、报告及兼容关系校验；13项篡改、路径、混配、缩短报告、缺少桌面补证、重复目录和已有冲突检查全部正确拒绝。安装候选76文件，保留旧删除标记的目录验证确认24个可新建受保护选择，实际服务层创建路径与删除拒绝通过。
- 完整三镜像归档2,145,259,644字节，SHA256 `2a642259a16f0a4c1282b1a28ae88d1a102427e9d4a214f9859ea386bb1f9de5`；102文件、99个OCI引用、83层逐项核对后在空独立Docker存储冷导入，镜像内部补丁及原异机容器保持检查通过。

## 部署与保护

完整包/安装验证通过后已执行受控激活；空闲生成服务与Adapter短暂停止，持spool锁追加来源/缓存并替换目录、程序和服务引用。部署后实际进程摘要正确，readyz与待初始化登录页均200，四个指纹/两个显示/24组合与已验证安装目录一致。账号0、可见浏览器0；10条已删除浏览器历史、原审计/会话记录保留，未恢复owner或虚构默认凭据。管理员按[1.0计划](../../docs/v1.0-delivery-plan.md)使用CLI指定名称、从stdin设置密码。

部署前425个保护文件核对未变；激活仅修改登记的程序、服务、目录和新增来源/缓存，其余保护状态及生产容器保持。两机本轮QA Worker已释放，独立机原停止的arm64-debian11保持。仅清理已通过、摘要绑定且无任何容器挂载的合成Home，失败Home、日志和R6AU真实离线恢复根不清理。

新增244文件部署留存包已在独立机解包、逐文件及二进制核对：9,639,360字节，SHA256 `8d27723723a9f07b7f68a30bb9d5cb16bba3be9308f529674b13a866bf33f64c`。该包是R6AW部署材料，不是1.0发行包。

自动回退仅在保护状态无独立变更时恢复备份并删除本次精确新增文件；发现新状态则保留并对账。入口脚本为`infra/environment-engines/deploy-builtins.py`，本次成功部署没有为证明回退再中断服务。私有`deployment-backup/`及输入清单保留。

## 失败与证据边界

早期v1–v5的失败和成功报告均保留原范围，不能计入v6。DEV-142身份、DEV-143客户端资源隔离、DEV-144初始文档就绪、DEV-145尺寸/DPR、DEV-146包关联、DEV-147桌面补证、DEV-148键盘顺序及DEV-151目录关联按原要求处理并完成最终验证。

[DEV-149](../../docs/deviations/DEV-2026-10-03-149-qa-shutdown-io-contention.md)的US Chromix退出超时原failed保留；停止镜像I/O与浏览器QA重叠后，新完整任务按原12秒门槛accepted。不能承诺任意I/O压力下都能在12秒关闭。

[DEV-150](../../docs/deviations/DEV-2026-10-03-150-firefox-storage-probe-timeout.md)的独立机US Firefox首次IndexedDB建库15秒超时已复现；诊断观察到约20–23秒首次建库及高fsync时延。延长连接的零重建诊断不计accepted。US/TW两项由本机按原15秒门槛完整通过，独立机旧失败及慢盘限制仍保留，不宣称该机该场景已通过或运行时已修复。

供应商自然动态漂移仍未测，静态代理恢复和受控QA不能替代供应商实测。普通自定义固定Camoufox仍沿历史生成门槛，本项额外桌面证据只覆盖规定四个内置固定组合；后续统一门槛须另立工作项，不作为已实现能力。

私有证据根：本机`infra/sealskin/runtime/r6aw-protected-builtins-20261002/`，独立机`/srv/r6aw-protected-builtins-20261002/`。主要回执为`live-matrix-v6.json`、`final-report-counts.json`、`package-validation.json`、`installation-validation.json`、`deployment.json`、`post-deployment-validation.json`及`remote-deployed-v6-retention.json`；完整失败细节见[偏差索引](../../docs/deviations/README.md)。
