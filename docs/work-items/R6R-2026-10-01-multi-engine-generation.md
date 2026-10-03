# R6R · Camoufox、Chromix 与 Firefox 自定义生成

状态：已收尾并部署。用户要求生成组合支持三个引擎，承接 R6Q；实现、完整隔离验收、限定发布和文档检查完成。

## 范围与调用链

通用指纹源/显示源 → Adapter accepted 目标与生成能力过滤 → v3 作业 → 按引擎分派的固定镜像生成与完整验收 → environment/template 目录发布 → 浏览器绑定。现有 Camoufox 流程保留；Chromix 目前仅固定产物、每 Home 种子；原生 Firefox 尚无可新建的 accepted 目标。

采用本机已固定版本：Camoufox152.0、Chromix154.0.8037.57、原生Firefox155.0.1（来自 r10 桌面基础镜像）。Chromix 新自定义产物固定来源/目标种子，旧产物保持每Home种子；原生Firefox固定语言/时区/显示和原生设备配置，不宣称具备 Camoufox 的设备伪装能力。三者共享高层来源，但缓存/产物/报告按引擎目标隔离。

新增两个薄Worker修订，禁止任意 flags/脚本注入。Firefox使用独立 `.firefox` Home 配置，不迁移 Work 旧 Home；引擎切换继续受 Home 保护。生成器必须逐项验证实际语言列表、时区、显示/窗口、版本、缓存及重启稳定性；不支持的参数明确拒绝。

## 完成条件

1. 三个 accepted 且已实现生成器的目标可选；缺失/伪造/不匹配目标拒绝，旧模板/v1/v2/v3/旧缓存保持。
2. Chromix、Firefox 新产物/镜像精确绑定；同一来源在不同引擎隔离，同引擎换显示复用原配置，版本/镜像漂移拒绝。
3. 每个新增引擎两个显示组合、完整语言/时区、两Home十次重建、存储和离线恢复、真实HTTPS经QA代理/直连拒绝、显示认证/正常桌面输入、发布恢复和管理绑定验证通过。Camoufox保持既有完整验收与回归，不降低原验收条件。
4. 从R6Q精确Adapter源码构建完整test/vet；主机/镜像相关测试、真实模板目录/API及有数据响应式UI通过。
5. 仅发布新镜像、最小Adapter/空闲runner及追加已验证Firefox目标，保留所有生产容器/Home/账号/作业和旧目录条目。当前磁盘约4.2GiB，使用小上下文离线增量构建，独立QA顺序执行；保留所有失败证据，不删除真实数据释放空间。

## 文档/收尾

设计/规格、Adapter与各引擎README、管理UI/客户端/运维、验收及索引、progress/roadmap、工作项。偏差发现即登记。QA与源码/部署证据在ignored `infra/sealskin/runtime/r6r-multi-engine-20261001/`。

基线R6Q Adapter `ab60d3a58db9395c066ca0dfe4fadcc6fd4430f9c2eb3d9c1ff24571d14b276a`；不发布无关R6I/R7G，不重建或停止生产浏览器。目标客户端实机和跨OS设备模拟保持后续边界。

偏差：[DEV-101](../deviations/DEV-2026-10-01-101-chromix-custom-languages.md)，公开 fingerprint-locale 覆盖多语言，改为受管理原生偏好后重新完整验收。

偏差：[DEV-102](../deviations/DEV-2026-10-01-102-native-firefox-window-placement.md)，原生Firefox窗口默认放置导致底边裁切，新增专用规则并重验。

偏差：[DEV-103](../deviations/DEV-2026-10-01-103-generator-image-tag-reuse.md)，新增构建器重复输入必须复用已校验镜像，不能移动历史标签。

补充偏差：[DEV-104](../deviations/DEV-2026-10-01-104-native-window-capability.md) 原生窗口能力入队前拒绝；[DEV-105](../deviations/DEV-2026-10-01-105-empty-template-catalog.md) 空目录发布恢复。

## 收尾复核

1. 三目标及原v1/v2/v3兼容：固定版本能力、完整语言/时区、原生Firefox UA和双向Home保护已覆盖。未支持的原生非全屏窗口由Adapter/runner拒绝。
2. 两新增引擎各两显示组合accepted；每组合两Home十次重建、离线恢复、网络/显示/真实输入全部通过。跨显示非显示字段、Chromix来源种子与同Home A→B→A存储保持。
3. 四项发布恢复、十项runner拒绝、十四项安装入口拒绝、六组有数据UI、Go全test/vet、56项主机测试、35项冻结运行依赖测试与Camoufox镜像artifact单测通过。
4. 已部署最小Adapter、固定runner/registry并追加Firefox目标；原生产容器、Home、账号、配置及旧作业保持。Work/Chromix healthy、测试停止；Personal上游unknown在发布前已存在，保留事实并归既有运维排查。
5. 设计、规格、组件README、管理UI/客户端/运维、验收与索引、progress/roadmap、偏差状态均更新；QA运行资源已清理，离线Home/所有失败证据保留。

证据及回退边界见[R6R验收](../../infra/sealskin/r6r-multi-engine-acceptance-2026-10-01.md)。原生组合生产首次使用和目标Mac客户端反馈仍未验证，属于使用反馈/原客户端验证计划；跨OS模拟、原生独立窗口能力及R6O百分比持久化为后续能力扩展。本项不自动切换旧浏览器，不开始下一计划。
