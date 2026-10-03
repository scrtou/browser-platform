# R6S · 三引擎共用自定义与系统显示模板

状态：服务器交付已收尾并限定部署。用户明确：自定义固定尺寸/DPR1可以保留；系统内置自动分辨率与随UI Scaling变化的DPR应供Camoufox、Chromix、Firefox共同使用。同时修复空指纹页看不到生成引擎、新增浏览器缺Firefox的问题。

2026-10-01 续办：用户要求继续剩余工作，R6S1 磁盘维护已收尾；现有三引擎自动组合各22份观察及恢复通过。固定 Chromix 小窗口被基础桌面最大化，已记录 [DEV-112](../deviations/DEV-2026-10-01-112-chromix-fixed-window-rule.md)，先修复并完成所有原门槛，再限定发布；其他计划不并行实施。

续办增量：Chromix 实际 WM_CLASS 为 Chromium-browser，规则修复后的固定小窗口诊断通过；只更新 Chromix 薄镜像，新建来源并重新验收固定/自动组合。旧 Chromix accepted 组合从本轮 QA 当前选择中移出，原目录快照、作业、产物、Home 和报告全部保留；发布/显示切换工具按当前 QA catalog 选择，不从历史通过作业取第一条。Camoufox 固定组合已通过22份观察与恢复。早期无窗口 QA 的回收边界见 DEV-110，未冒充正常关闭通过。

Firefox 固定输入/截图工具偏差见 [DEV-113](../deviations/DEV-2026-10-01-113-firefox-fixed-input-probe.md)：精确诊断确认真实输入正常，修复异步等待与24位 XWD 解码后新建作业重跑。最终 Go test/vet、候选字节复建和53项主机检查通过，详见[最终验收](../../infra/sealskin/r6s-shared-display-acceptance-2026-10-01.md)。

## 范围与代码地图

TemplateSources/DisplayPreset → 管理页独立组合入口 → v3组合规格 → Camoufox/native生成、缓存及启动校验 → X11/Selkies尺寸/DPI → accepted环境/共享显示目录 → 新建/应用浏览器。R6R线上有三个browser target，但指纹源/显示源均为0；引擎选择只渲染在指纹源行内。Firefox没有accepted兼容环境，新增浏览器由兼容三元组过滤后不显示。见[DEV-106](../deviations/DEV-2026-10-01-106-template-empty-state-and-defaults.md)。

用户确认的契约：显示模板不绑定引擎；自定义fixed/DPR1，包括合法独立窗口尺寸；系统内置auto/system，物理画面上限3840×2160。UI Scaling与网页缩放不同。语言/时区/设备种子不随显示模式改变，运行时screen/window/DPR允许按显示策略变化。原Firefox设备特征能力保持，不将本项扩大为随机设备伪装。

## 完成条件

1. 空指纹页也可发现组合引擎入口及下一步；系统显示模板始终可见。默认三个引擎均有实际accepted可新建组合，不能仅追加空target。
2. 三个引擎均支持自定义fixed/DPR1和同一内置auto/system；同来源/目标复用设备配置，旧产物/作业/来源及旧Chromix自动缩放继续可读。
3. 各引擎新固定/自动组合完整独立Home验收，自动场景真实Selkies客户端调整尺寸、100/150/200%及复位、重连/DPR1与2、点击输入、上限；固定独立小窗口实测。非显示字段按同一DPR和不同DPR的真实渲染契约核对，不以CSS遮罩伪造浏览器观测。
4. 目录与实际API/空状态及有数据UI、请求拒绝、发布恢复、Go test/vet和相关Python检查；最小冻结发布保留生产容器/Home/账号/旧作业，不带入R6I/R7G。
5. 设计/规格、组件README、管理/客户端/运维、验收及索引、progress/roadmap/偏差和本工作项收尾。启动时磁盘1.7GiB（历史观测），薄镜像、顺序QA，不删除真实数据或失败证据释放空间。

基线R6R Adapter `7e9f7ec24483012105c9e327e86cd5b525eb30fa28273b342e7e64c96978cc02`。证据根 `infra/sealskin/runtime/r6s-shared-display-20261001/`。本项已获用户授权实现及限定发布，不自动切换已有浏览器。

实施补充：DEV-109修复冻结runner客户端缓存路径；DEV-110修复探针恢复页面与语音就绪；DEV-111以Chromix v4固定字体子像素定位策略处理真实同DPR文字画布漂移。所有早期失败保留；Chromix新镜像另建通用来源，不修改旧缓存。Camoufox自动完整22份重放与恢复已通过，当时其余组合和发布仍在验收，最终结果见下文。


## 最终收尾（2026-10-01）

五项完成条件逐条达到：空/有数据页面及六默认新建选项通过；共享fixed/auto显示、设备复用和旧格式兼容通过；六组合各22份观察、恢复及真实输入/动态显示通过；3组同Home显示切换、6组发布恢复、15组runner拒绝、28组实际入口拒绝、Go test/vet和53项主机检查通过。DEV-106～113已解决，历史失败及Home保留，DEV-110异常QA回收未记为正常关闭通过。

限定发布完成，运行Adapter为b4dc0eb6…，只更新最小Adapter/空闲runner和六默认组合及引用来源/缓存；生产容器/Home/绑定、账号、旧目录和作业保持。13:36 UTC Work/Chromix healthy、测试offline、Personal原有上游unknown保持。QA清理通过，发布后可用约5.10GiB。实际版本、完整摘要、证据与回退边界见[验收](../../infra/sealskin/r6s-shared-display-acceptance-2026-10-01.md)。

设计/规格、Adapter/Camoufox/三引擎README、管理与客户端/运维说明、验收与偏差索引、进度/路线图和工作项索引已同步；原需求、实际行为和验收结果完成复核。未迁移现有浏览器，目标客户端新页面、生产新组合首次使用与R6O百分比保存仍分别保留。下一项按[完整计划核对](../plan-completion-2026-09-30.md)先复核R7F/R6H服务器证据，再进行全计划审计；R7G供应方缺证/禁止部署及异机资源条件保持。

收尾静态检查：25份受影响文档相对路径检查无缺失，git diff --check通过；未重复执行已通过且源码未变化的运行测试。
