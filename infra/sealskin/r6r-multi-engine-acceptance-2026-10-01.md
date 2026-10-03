# R6R 三引擎自定义生成验收 · 2026-10-01

状态：服务器实现、隔离验收、限定部署和文档收尾完成。

关联：[工作项](../../docs/work-items/R6R-2026-10-01-multi-engine-generation.md) · [组件](../environment-engines/README.md) · [前序 R6Q](r6q-engine-neutral-acceptance-2026-10-01.md)

## 范围与版本

通用指纹模板与显示模板分离保持，生成组合可选 Camoufox152.0、Chromix154.0.8037.57、Firefox155.0.1，Linux x86_64。Camoufox继承R6Q两显示完整验收，本次补运行固定镜像的artifact单测和38项主机回归；新增两引擎不借用Camoufox的指纹报告。

- Adapter由R6Q精确源码增量构建，仅六文件变化，SHA256 `7e9f7ec24483012105c9e327e86cd5b525eb30fa28273b342e7e64c96978cc02`。
- Chromix Worker：`sha256:3974c6e85206279a05ffcb72b821bb260fd3354ed8d5aab92c0f978f4f1940a2`。
- Firefox Worker：`sha256:cc10161994813b2da0f59374f76eb355af7d36bde59bb0330687e8ddf887d194`。
- 两个薄镜像由固定本机基础镜像离线构建；Firefox使用已有/usr/lib/firefox/firefox155.0.1。新标签按输入摘要复用，不重建覆盖。

## 真实组合

同一通用来源：zh-CN/en-US/en、Asia/Taipei。显示为1280×900与1600×900，窗口等于屏幕、DPR1。

| 引擎 | 屏幕 | 作业 | 结果 |
| --- | --- | --- | --- |
| firefox | 1600×900 | `job-ab5a727c84442023` | PASS |
| chromix | 1600×900 | `job-aeacaba0792cb43e` | PASS |
| chromix | 1280×900 | `job-b13288c9fe37932e` | PASS |
| firefox | 1280×900 | `job-d61c5b98d090cd02` | PASS |

每组合两独立Home各初次启动＋十次重建，记录22份完整观察；另外离线复制A并恢复一次。四组合共88份稳定观察、4次离线恢复；每次检查Cookie/localStorage/IndexedDB、实际HTTPS经隔离Relay、IPv4/IPv6直接socket阻断和正常X11关闭。A/B初次桌面还验证显示认证、三点鼠标点击、键盘输入及截图。

真实观测逐项匹配完整语言列表、时区、platform、UA major、screen、window和DPR；canvas/audio/fonts/voices/WebGL等非显示API每次精确相等。Chromix语音列表为空、WebGL为null，Firefox保留原生设备特征。Firefox无跨OS/随机身份伪装承诺；ChromixWebRTC是proxy-only而非disabled。Chromix继承现有host-resolver-rules提示条，观察包含其稳定viewport；不删除网络限制来隐藏提示。

同 Home 显示切换另通过两引擎 A→B→A，三类存储持续可读；44份/引擎非显示观察跨两个显示精确相同，Chromix来源种子保持。真实画面截图人工复核无裁切。

## 自动与恢复检查

- 最小Adapter全部 `go test ./...`、`go vet ./...`通过；四个真实accepted环境目录与兼容绑定解析通过，原生Firefox双向跨引擎Home保护、版本/UA与不支持窗口拒绝覆盖。
- 主机Camoufox作业/模板/准备/窗口38项、Chromix11项、新原生引擎7项通过；冻结runner相关35项通过。固定Camoufox镜像的artifact单测通过。
- 六组有数据模板页面（1280/768/390，两页面）通过三引擎选项、字段分离、标签、键盘和无横向溢出检查。
- 两原生引擎各7项真实安装入口拒绝（摘要、时区、版本、额外参数、窗口越界、镜像、缺失产物），共14项通过。
- 两引擎各两项发布恢复（中断/写入失败），共4项通过；保留产物/报告及已写目录字节，恢复只补兼容条目。
- 两引擎各5项runner拒绝（失败报告、来源漂移、目标修订、缓存镜像、目录ID冲突），共10项通过，原目录/产物/报告保持。

## 偏差与历史失败

[DEV-101](../../docs/deviations/DEV-2026-10-01-101-chromix-custom-languages.md)以受管理语言Preferences修复多语言；[DEV-102](../../docs/deviations/DEV-2026-10-01-102-native-firefox-window-placement.md)修复Firefox位置/语音提示条引起的viewport漂移；[DEV-103](../../docs/deviations/DEV-2026-10-01-103-generator-image-tag-reuse.md)按固定输入复用镜像；[DEV-104](../../docs/deviations/DEV-2026-10-01-104-native-window-capability.md)入队前拒绝不等窗口；[DEV-105](../../docs/deviations/DEV-2026-10-01-105-empty-template-catalog.md)处理空目录null及发布JobError。

早期失败诊断输入、Home、日志和报告均保留；两个早期诊断旧image ID因旧构建器重复标签不可再inspect，未借用这些报告发布。首次Chromix完整PASS后空目录发布失败，保留失败状态快照并以相同artifact/report恢复accepted。UI检查的Python/浏览器缓存调用错误、误在主机运行镜像测试、冻结runner不包含非运行用途的迁移工具、显示切换驱动模块名冲突均保留原错误；修正执行环境/入口后使用对应检查，不修改通过条件。

## 部署与边界

限定工具为[deploy.py](../environment-engines/deploy.py)，准备核对已有二进制、受保护配置/账号/目录/作业及源清单，最终只更新Adapter/空闲runner并追加Firefox目标；旧catalog条目和生产Home不替换。已部署，Adapter SHA 与上述一致。执行器绑定最终源码清单及native registry；旧容器ID/启动时间/状态、Profile/账号、既有目录条目和旧作业文件校验全部保持。正式runner参数与运行Adapter二进制在发布后再次核对。

新组合仅在隔离QA创建，本次不会自动创建生产Firefox浏览器或给现有浏览器换模板。实际新增原生组合的生产首次启动、目标Mac/Trilium新表单、跨OS模拟、R6O缩放百分比统一保存均不是本报告的通过项；前两项分别由用户首次使用反馈和原客户端验证计划跟踪。

私有证据根：`infra/sealskin/runtime/r6r-multi-engine-20261001/`。包含build-final-7、integration-accepted、publication-recovery、runner-rejections、negative-*、ui-release、最终源码清单、二进制和部署备份；报告不公开SessionURL/凭据。

QA清理已完成：无native-generation容器、无本次envjob网络、无native-display临时认证目录；离线Home和所有失败/通过证据保留。

发布前后健康：Work与既有Chromix均healthy，测试实例保持PROFILE_STOPPED；Personal的入口/会话/浏览器/显示通过，但上游探测均为PROXY_UPSTREAM_UNKNOWN，overall=unknown。该观测在发布前已存在，本项保留网络配置/容器，没有把它写成healthy；后续归既有代理出口运维排查，不属于三引擎生成验收缺口。初次并行探测Work命令失败，独立复测及发布前后均healthy；已保留所有结果。
