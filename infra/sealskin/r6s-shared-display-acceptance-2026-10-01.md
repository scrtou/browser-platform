# R6S 三引擎共用显示模板验收 · 2026-10-01

状态：服务器交付已通过并限定部署，已收尾。关联 [工作项](../../docs/work-items/R6S-2026-10-01-shared-display-templates.md) · [组件](../environment-engines/README.md)。

## 交付范围与版本

自定义 fixed/DPR1 显示与系统内置 auto/system 显示供三个引擎共用；固定模式支持独立小窗口，自动模式的 DPR 随系统 UI Scaling 变化，物理画面上限3840×2160。语言/时区/设备来源不随显示重新生成。空指纹页提供独立引擎入口；六个实际 accepted 默认组合已发布，新增浏览器可选三个引擎及对应两种显示。现有浏览器不自动切换模板。

运行中 Adapter SHA-256：`b4dc0eb6c144d5b11f06bb7430d89d5b09cf5ada1ce8ab9d1266d4207eb618b3`。最终冻结源码完整 Go test/vet 通过，重新构建与候选字节一致；发布后读取运行进程二进制再次核对。相对 R6R 最小 Adapter 改动9个路径，runner改动33个路径，未带入R6I/R7G。

| 引擎 | 最终镜像 | 固定 / 自动验收作业 |
| --- | --- | --- |
| Camoufox 152 | `sha256:f37c2f809411c5dfc04183dbf9ce1c109d43864036cd4b695a2a59748d83e31d` | `job-548653cd5d5d204e` / `job-6b606b8041851493` |
| Chromix 154.0.8037.57 | `sha256:90f757b138d096d8182b89fbacd5aa36b3a23bc17be35a677460f9878971426a` | `job-e9e269decc414122` / `job-3d79057e980a0aac` |
| Firefox 155.0.1 | `sha256:ae7a4e612f1655e87b50dcd24530e159a006a82a5a606254f6a3e915f95b932e` | `job-64f65f215359a85b` / `job-edee032e99019517` |

## 最终验收

每个组合两个独立 Home，每 Home 初次启动及十次重建，共22份观察；六组合合计132份，均为完整 phase=all 通过，三类存储、离线恢复、代理与直连拒绝、显示认证和真实输入通过。Camoufox固定报告使用原 results.homeReplay 结构，其余使用原生报告结构。固定屏幕1280×900、独立窗口1000×800、DPR1实测通过；自动模式以真实Selkies客户端覆盖尺寸变化、100/150/200%及复位、DPR1/2重连、上限和实际点击输入。同DPR比较画布，其他非显示字段保持对应契约。

| 门槛 | 结果与证据 |
| --- | --- |
| 三引擎同 Home fixed→auto→fixed | 3组通过，实际输入、存储和非显示指纹保持；display-switch/result.json |
| 发布中断及目录写入失败恢复 | 6组通过；publication-recovery/result.json |
| runner 拒绝 | 15组通过；runner-rejections/result.json |
| 实际安装入口拒绝 | Camoufox10、Chromix9、Firefox9，共28组；negative-*/result.json |
| 空/有数据模板页面 | Linux Chromium151真实渲染，各6组，覆盖三种宽度及键盘/字段；ui-empty、ui-populated；HTTP/认证表单另由Go测试覆盖 |
| 六默认组合的新建选项 | 三引擎、两类显示、三种宽度通过；ui-create/result.json |
| 主机回归 | 53项：作业17、模板来源9、应用定义3、窗口工具3、Chromix兼容11、新引擎及显示/截图10；host-final-tests.json |
| 源码及候选核对 | 完整Go test/vet、字节一致复建、六份完整报告核对；verification.json |
| 发布与运行 | deployment.json及post-release-verification.json通过；Adapter/runner active，运行摘要匹配 |

窗口工具与 Chromix 准备工具不在最小冻结 runner 内，相关测试从仓库运行；Chromix launcher 与冻结源字节一致。最初在冻结目录运行窗口测试缺文件、Chromix测试模式未匹配产生零测试，均保留原日志；修正执行上下文后才计入通过数。

## 偏差与保留失败

[DEV-106](../../docs/deviations/DEV-2026-10-01-106-template-empty-state-and-defaults.md)～[DEV-113](../../docs/deviations/DEV-2026-10-01-113-firefox-fixed-input-probe.md)均按原门槛修复并完成验收。包括空页面与默认组合、动态输入几何、设备生成参考尺寸、冻结客户端缓存、探针就绪、Chromix字体子像素定位及真实 Chromium-browser 窗口类、Firefox异步点击等待和24/32位 XWD 行跨度解码。零次重建诊断只用于定位，没有代替发布验收。

早期 integration-2 无窗口 QA 浏览器正常关闭超时。保存容器/进程状态、日志和认证输入后仅回收隔离运行资源，原 Home/失败报告保持；该操作没有记为正常关闭通过。新作业完整重建、关闭及恢复另有通过证据，生产浏览器未参与故障实验。

Chromix 新镜像使用新来源/缓存，旧缓存不改写。旧通过组合仅从本轮当前 QA catalog 选择中移出，旧 catalog 快照、作业、产物、Home 和报告全部保留。补充验收工具按当前 catalog 引用选择。

## 发布、清理与边界

限定发布只更新最小 Adapter、空闲 runner，追加六默认组合及其引用的2份指纹来源、2份显示来源（内置自动及自定义固定）与对应设备缓存；内置自动显示由服务提供只读语义。正式应用定义使用生产用户、入口和剪贴板依赖，产物/报告复制到default-combinations，不依赖QA Home。失败及被替代的来源没有发布。

发布前后生产容器ID/启动时间/状态，Profile、账号、网络目录、旧目录条目和旧作业保持；既有浏览器Home与绑定没有迁移。13:36 UTC 新鲜健康：Work/Chromix healthy，测试实例offline，Personal仍为发布前已有的上游unknown。此项不宣称Personal出口已修复，也没有变更其代理配置。非ready历史浏览器记录未作为健康通过样本。

隔离QA容器已清零，四份无挂载的临时认证目录先归档再回收；Home、失败证据与报告保留。qa-cleanup.json通过。发布后磁盘可用约5.10 GiB，属当时共享主机观测。回退材料保存在deployment-backup，工具仅在受保护输入/作业未变化时回退；有新操作须保留并对账，不能删除新Home/作业降级。

私有证据根：infra/sealskin/runtime/r6s-shared-display-20261001/。Mac/Trilium新表单实机、原生新组合生产首次使用、R6O百分比持久化、异机恢复和其他未完成计划仍按各自范围跟踪，不由本报告提前宣称通过。
