# R7F · R7 组合候选、生产发布与目标客户端验收

2026-10-01当前复核：服务器证据及后续版本链已由[R6T](../../infra/sealskin/r6t-server-plan-audit-2026-10-01.md)逐条核对。后续R7F有限客户端反馈与旧Tab完整矩阵分开记录；本父项仍保留未测客户端/历史条件。用户已选择暂缓客户端并推进其余计划，下面“未收尾不开始下一项”为原阶段历史，不覆盖此后顺序授权。

状态：待验证（按用户选择保留待验收）。开始日期：2026-09-23。


**执行顺序更新（2026-09-30）：** 用户明确选择选项 1：R7F 保留待验收，当前只推进 R7G 隔离开发与验证，不部署生产。R7F 原完成条件、未测客户端项和数据不适用范围不变；本次调整不表示 R7F 已收尾。


## 2026-09-30 续跑：父项完成条件复核

本轮结果：三个 accepted 条目的七个模板元数据字段与实际代码从原 artifact 派生值全部一致，生产快照保持；DEV-074 已独立收尾，DEV-061 的生产重建待办已更新。原七项条件的逐项证据、历史复合基线缺口、生产数据不适用与客户端未测范围见 [父项复核](../../infra/sealskin/r7f-completion-review-2026-09-30.md)。未用新的生产停止去补造历史前置，也未把“继续”当作用户验收或调整执行顺序的答复。

用户要求继续。本轮把已定版服务器材料、生产维护、独立 QA 与目标客户端证据对应到原七项完成条件，纠正仍把已完成生产重建列为待办的偏差记录；不重做已经通过的打包、构建或生产维护，也不把“继续”当作客户端检查结果。

- 代码地图：已核对的完整发布链与各阶段回执；本轮对 `environment-job.py:template_metadata/catalog_entry` 从 artifact 派生的字段与当前 accepted 目录逐项只读比较，决定 DEV-074 自身契约是否已满足。客户端菜单仍按 DEV-073 单独追踪。
- 完成条件：形成逐条证据/限制/剩余动作表，独立关闭已满足自身条件的实现偏差；原 1280×800、数据范围和历史维护条件不悄悄降级。确需用户改变交付范围时，在可审阅结果完成后明确提出。
- 边界与文档：仅只读核对和文档，保留生产 Home/Session/浏览器；更新适用偏差/索引、父项复核表、验收/工作项索引、progress/roadmap 和客户端说明，不启动 R7G。

本轮复核收尾：11 份文档、581 个相对链接/锚点及 `git diff --check` 通过；元数据读取前后生产快照一致，无临时运行资源或产品代码变更。组件/偏差/验收与工作项索引、progress/roadmap 和客户端边界已同步，设计/规格契约未变。已提出执行顺序选择；未收到明确答复前 R7F 保留待验收，不开始 R7G。

## 2026-09-30 续跑：服务器发布材料定版与剩余客户端核对

本阶段服务器材料已完成：352 文件、1,030,354,192 字节，包内外分别验证固定 manifest `c6219af4…` 通过；实际控制器 96 文件/47 payload 与精确镜像和原 overlay 链一致，两个客户端外挂包、三个 Worker 激活脚本、三个 accepted 环境目录依赖均匹配。Work 最新恢复点/回执/生产重建证据、备份工具和分组件恢复说明已纳入；原失败与 342 文件候选保留。17:30 UTC 生产身份保持，Personal/Work healthy，“测试”维持主动关闭状态。详情见 [定版验收](../../infra/sealskin/r7f-server-release-seal-acceptance-2026-09-30.md)。客户端新问题已提出，未收到反馈的参数/菜单仍保留未验证，R7F 父项未收尾。

Work 正常重建阶段已收尾，用户要求继续。本轮在 R7F 内固定最终服务器发布组合：沿用已复建验证的 Adapter 源码和二进制，补齐现行控制器发布清单/实际代码核对、Worker 外挂客户端文件和环境产物、当前配置/应用/目录摘要、新 Work 备份和恢复回执、各阶段验收以及分组件恢复说明。已验证的 109 文件旧包保留原状，新的清单从独立目录生成。

- 完成条件：发布材料逐文件摘要与实际部署/适用验收对应，验证器从包内外分别核对同一固定清单；明确需要本机精确镜像和独立密钥，不冒充整机灾备或客户端通过。按原完成条件逐项登记服务器完成范围与客户端未验证项。
- 代码地图：`check-release-materials.py` 的外部 manifest pin/路径/权限/文件集合校验 → 旧准备脚本的只读快照与构建证明 → 控制器不可变镜像及实际发布标识 → Worker mount 的客户端和 environment/acceptance 字节 → 既有 backup verify/restore 回执。
- 边界：只读生产和复制静态材料，不重新构建或发布，不停止生产浏览器，不复制运行中 Home/明文凭据或回放共享状态。新包是同主机受控恢复所需的版本材料；镜像层与独立密钥列为外部输入，异机恢复不是本轮交付。
- 客户端：只请求缺失的 Trilium 桌面右键观察及当前版本/尺寸；已通过的页面/输入不重复。用户主动关闭的“测试”可进入原桌面观察，无需启动或重建。
- 文档清单：新验收及索引、组件/运维与客户端说明、适用偏差、progress/roadmap 和本工作项/索引；保持用户已有改动，不开始 R7G。

本阶段收尾核对：12 份文档、550 个相对链接/锚点、3 个私有打包脚本语法和 `git diff --check` 通过；随包四个恢复 CLI/工具的可用性检查通过，隔离读取容器与临时工具目录已清理。17:30 UTC Personal/Work 新鲜 healthy，“测试”维持已确认主动关闭的 BROWSER_EXITED，配置/账号/应用/策略和所有 Profile 的 Session/容器身份保持。设计与管理规格契约未改变；组件/恢复/运维说明、验收和工作项索引、progress/roadmap 已同步，服务器材料阶段已收尾，未开始 R7G。

## 2026-09-30 续跑：生产 Work 正常重建维护

本维护范围已完成：17:08 UTC 正常停止 Work 并核实零资源/无 Home 挂载；5,938 条目 age 归档、verify、独立 restore 成功，5,740 个 Home 普通文件及其他持久条目内容/权限一致，副本未激活。用户通过固定入口重开后，17:15 UTC 核实新 operation/Session/容器、原 Home/完整应用/目录/策略及其他 Profile journal 保持，浏览器/显示/DIRECT 与 Worker HTTPS/四类绕过拒绝通过。用户回复“1.正常 2。不适用”：页面和输入通过，原书签/登录项不适用；不扩大为生产三类存储读回。Personal/“测试”身份和配置/账号/应用/策略摘要保持。见 [本轮验收](../../infra/sealskin/r7f-work-production-rebuild-acceptance-2026-09-30.md)。

用户在明确下一步为 Work 真实 Home 重建验收后要求继续。本轮沿已有 R7F 生产维护授权，仅维护 Work：先固定当前应用、镜像、目录和运行身份，经 Adapter 正常停止并确认零资源，保留最新 journal，完成匹配停止时点的 age 备份/verify/独立 restore，再由现有固定入口创建使用原 Home 的新代次并核对数据和网络。Personal 与用户主动关闭窗口后的“测试”保持原状态。

- 完成条件：停止前 Work 新鲜健康且精确镜像/应用绑定符合批准记录；正常停止无强杀，Session/Worker/Relay/Guard/网络全部释放；新备份可恢复且未激活；重开后 Work 使用原 Home/应用/策略及新 Session，DIRECT/显示健康，用户确认浏览器内页面与适用数据。独立 QA 三类存储结果保持原范围，不向生产写入合成测试数据。
- 代码地图：本机 control socket 的 `Stop` → 同 Profile 生命周期锁/持久 stop intent → 控制器正常浏览器退出及资源回收 → `secure-backup.py` 的固定运行证据/create/verify/restore；重新创建只走已认证固定入口，`resume-profile` 仅恢复休眠代次、不能替代新建。
- 执行边界：不部署代码或镜像，不回退 Work，不恢复旧共享 journal/账号/Session，不删除真实 Home；若正常关闭遇到对话框或无法证实零资源，保留现场并处理实际失败。
- 验证与收尾：停止时点文件与独立恢复副本逐项比对，重开后原 Home/精确版本/当前网络和其他 Profile 身份复核；更新 Work/运维/客户端说明、验收索引、进度/计划和本项。固定入口重开与浏览器内数据需要用户实际操作，服务器证据不冒充该结果。

重开前阶段复核已通过 11 份文档、484 个相对链接/锚点、2 个私有 Python 脚本语法与 `git diff --check`；解密 tmpfs 已清理，恢复副本未激活。重开后 Personal 新鲜 healthy，“测试”仍为已确认主动关闭的 BROWSER_EXITED，其他 Profile 身份保持。设计/管理规格契约无变化，本轮只补运行与用户证据，组件/运维/客户端说明、验收索引、progress/roadmap 已同步；R7F 父项的客户端尺寸/菜单及发布包封版仍保留，没有开始下一项。

重开后收尾检查：11 份文档、484 个相对链接/锚点、2 个私有脚本语法和 `git diff --check` 通过；新证据权限、tmpfs 清理与恢复副本未激活状态再次核对通过。

## 2026-09-30 续跑：当前发布材料与恢复边界复核

本轮结果：76 文件最终源码副本以原 Go 镜像复建，与发布/安装/实际进程二进制逐字节相同；109 文件材料包、7 个本机精确镜像和两份既有密文/回执核对通过，5 项校验器回归通过，DEV-080 已解决。原 R6F age 备份认证旧恢复身份后，现行接口旧身份 401、新恢复身份及 profile-admin 200，DEV-070 已解决。生产配置、账号、目录、Session 和容器身份保持；但最终“测试”BROWSER_EXITED，未宣称整体健康或 R7F 完成。见 [材料与身份验收](../../infra/sealskin/r7f-release-materials-acceptance-2026-09-30.md)。

阶段收尾：15 份文档、693 个相对链接/锚点、2 个新增 Python 文件语法及 `git diff --check` 通过；本轮构建容器已移除，旧身份验证的临时明文目录已清理，原 Home、core、密文和失败记录保留。组件/运维/恢复说明、验收/偏差/工作项索引和 progress/roadmap 已同步；设计/规格契约没有变化。用户随后确认主动关闭“测试”窗口，当前状态保留；完整发布包封版、客户端未测项和生产 Work 重建继续由 R7F 承接，没有开始下一项。

用户要求继续。本轮仍在 R7F 内核对当前 Adapter 的源码/构建/运行摘要、目录配置、控制器与 Worker 精确镜像、加密备份和回退材料，形成可重复检查的私有材料清单；不部署 R7G，不停止生产浏览器。

- 完成条件：当前材料能与原验收、最终源码清单和实际二进制逐项对应；明确历史旧二进制不能直接读取迁移后目录，当前恢复材料不回放共享 journal/账号/Session 快照；未验证部分保持原条件。
- 代码地图：原部署脚本的只读 snapshot/摘要检查 → Go 构建与最终源码清单 → 配置/模板/迁移目录 → 当前二进制只读 inspect/probe；恢复材料引用备份工具的 verify/restore 回执，不通过重新运行部署脚本核对。
- 验证与文档：固定输入后独立核对源码与二进制、私有材料完整性、实际镜像和生产身份保持；更新适用验收、组件/运维说明、偏差/验收/工作项索引、progress/roadmap。生产 Work 重建与客户端缺项仍单独保留。
- 初步复核发现旧私有 source 副本有 4 个文件不匹配最终 76 文件清单，当前仓库则全部匹配，登记 DEV-080。保留原副本，通过新的最终源码副本和固定工具链复建核对解决，不把旧副本宣称为最终来源。
- DEV-070 补证：定位到仍保留的旧 R6F 恢复文件，先以原 age 备份和回执认证来源，再在进程内验证旧签名身份拒绝与当前身份可用；不打印密钥/密钥摘要，不修改生产授权或恢复旧状态。
- 收尾时新发现：“测试”在 16:55 UTC 新鲜报告中为 `BROWSER_EXITED`，显示/代理仍正常，Personal/Work healthy。沿 DEV-073 继续只读核对退出原因并询问是否为用户关闭；不把静态材料通过扩大为三者当前健康，不停止或重建生产浏览器来代替诊断。

## 2026-09-30 续跑：Trilium 0.106.0 用户反馈登记

本轮仅登记 Trilium 用户反馈并核对 R7F 剩余完成条件。用户按上一轮最终六项清单回复：首页/窄窗口、代理页、四类下拉与 Tab 焦点、Personal/Work 公网页面和输入均正常；“测试”桌面右键为“无法检查”，当前 Trilium 为 0.106.0。窗口尺寸/DPR 未提供，不将其推断为历史 1280×800，也不将无法检查记为通过。

- 完成条件与验证：原始回复和逐项解释写入忽略目录，更新客户端矩阵/指南、页面验收、DEV-073 与索引、工作项/验收索引、SealSkin 说明、progress/roadmap；校验相对链接/锚点与 `git diff --check`。
- 实现与范围：沿用上一轮已核对的管理 Tab、原生下拉和固定入口调用链；本次无实现、配置或部署变更，不重复运行产品 QA。
- 剩余条件：精确 1280×800 客户端证据、Trilium 菜单、生产 Work 真实 Home 停止重建/数据确认和特定旧恢复身份拒绝仍未完成；发布包/回退材料及父项整体收尾仍需最终核对。DEV-073/074 与 R7F 保持进行中，R7G 未部署。不要求用户为了菜单退出运行中的浏览器。

本轮 Trilium 反馈登记收尾：11 份文档、589 个相对链接/锚点及 `git diff --check` 通过；原始反馈和逐项解释以 0600 保存于忽略目录。未重跑产品测试、未部署或停止生产浏览器；本轮已完成证据登记，R7F 父项及未测条件保持。

## 2026-09-30 续跑：Mac 用户反馈登记与 Trilium 补测

本轮仅登记用户反馈、同步验收文档并提供 Trilium 操作步骤，继续归属 R7F；不实施新功能或部署。用户确认 Mac 首页/窄窗口、代理页、四类下拉正常，“测试”桌面右键没有 Firefox。客户端记录为 Google Chrome / macOS 15.1 (24B83)，Chrome 版本、当前窗口尺寸与 DPR 未提供；“能”仅确认可以使用 Trilium，不计为 Trilium 验收通过。

- 完成条件与验证：原始回复及逐项解释保存在忽略目录，区分实际用户证据、历史 Linux 结果和未测范围；文档通过相对链接/锚点与 `git diff --check`，不重复运行已完成的产品 QA。
- 代码地图复核：管理页网络 Tab 和新增浏览器原生下拉仍由 `manage.go` 呈现；`templateChoices` 拼接显示名称和 screen，选择本身不提交，实际变更仍需独立表单提交。本次只核对既有入口与验收范围。
- 文档清单：客户端矩阵、Trilium 指南、页面验收、DEV-073 及偏差索引、验收/工作项索引、SealSkin 说明、progress/roadmap 和本记录；设计/规格契约未改变，DEV-074 仍待 R7F 整体收尾。
- 后续：已请求 Trilium 首页/窄窗口、代理页、下拉/Tab 焦点、Personal/Work 公网页面和输入/滚动、r10 桌面菜单及当前客户端参数。生产真实 Home 重建和旧恢复身份仍属 R7F 后续验证，不包含在本轮客户端操作中。

本轮登记收尾：11 份文档、589 个相对链接/锚点及 `git diff --check` 通过；原始反馈与文档更新前快照以 0600 保存在忽略目录。逐项核对了用户回复与验收问题，未将 macOS 版本当作 Chrome 版本，未沿用历史尺寸或把 Trilium 可用性记为通过。本轮无产品、配置、服务或生产 Home/Session 变更，R7F 父项仍进行中。

## 2026-09-30 续跑：客户端页面验收

本轮服务器侧完成：Chromium 151 的 9 组真实渲染、模板/网络选择、Tab/Enter/后退/刷新与局部滚动可达性通过；DEV-079 已仅修正生产显示模板 label，原 ID/revision/设备/缩放/兼容及运行实例保留。15:45 UTC 三者新鲜 healthy，生产 r10 文件/菜单/进程只读核对通过。QA 无浏览器启动，控制器/上游/网络/匿名卷/进程/tmpfs 已清理。用户随后确认 Mac 四项通过，详见上方反馈登记；Trilium 后续第 1–4 项通过、菜单无法检查，客户端精确尺寸等仍未验证。详见 [本轮验收](../../infra/sealskin/r7f-client-ui-acceptance-2026-09-30.md)。

设计和管理规格保持原契约；组件说明、客户端文档/矩阵、偏差与验收索引、progress/roadmap 已同步。没有开始 R7G，未以 Linux 结果或 `/proc` 文件核对替代目标客户端证据。 阶段收尾检查：13 份文档、639 个相对链接/锚点、检查器语法及 `git diff --check` 通过；清理后生产身份/健康复核通过。

真实截图发现显示模板 label 仍使用 X11/Selkies，已登记 DEV-079。本轮加入该展示元数据的 QA 复验与限定生产修正：只改变 label，固定 ID/revision、兼容/缩放配置及运行实例保持，不提交浏览器绑定表单。

用户要求继续，按上一轮收尾继续完整客户端矩阵。本轮固定线上 Adapter，在独立 QA 账号/目录/控制器上验证真实浏览器渲染：首页、网络代理 Tab、浏览器/指纹/显示与网络下拉、键盘导航、1280×800 和窄窗口布局；不提交生产浏览器绑定或网络配置、不停止生产浏览器。Mac 浏览器版本、首页/管理页及 r10 桌面菜单和 Trilium 可用性已请求用户分项确认，不沿用历史实机参数。

- 代码地图：access 的授权首页与登录 → manage.go 的 Tab/兼容目录/原生表单 → profile 的环境/模板/代理目录只读摘要；已有 Go 测试验证 DOM/CSS 契约，本轮补真实 Chromium 几何与交互。
- 完成条件：留存精确版本和隔离输入、截图/几何/表单证据，检查页面无横向溢出及标签/选择可用；失败立即记录偏差。Linux 与 Mac/Trilium 明确区分，用户未回复的分项保持待验证。
- 收尾：清理 QA 控制器、浏览器进程、网络和显示 tmpfs，核对生产身份保持；更新客户端说明/矩阵、验收索引、progress/roadmap、本项及必要偏差。生产真实 Home 重建和旧恢复身份不在本轮客户端操作内。

## 2026-09-30 续跑：当前发布组合的隔离恢复与回退

本轮结果：固定线上组合的真实管理入口迁移、Wayland 公网、正常停止后新代次三类存储、网关故障关闭、完整 App/Definition 回退与再迁移读回全部通过。首轮工具适配失败及续跑保留，最终从干净 QA 完整复跑 8 项通过；133 个 QA Home 普通文件独立加密恢复一致。两个 QA 作用域均清理，15:29 UTC 生产三浏览器原目录/Session/容器身份保持且新鲜 healthy，详见 [本轮验收](../../infra/sealskin/r7f-work-recovery-acceptance-2026-09-30.md)。

本次交付只修改 QA 工具与文档，产品/设计/管理规格契约及生产部署未变。DEV-078 共享探针修正、3 项针对性回归和实际正常/故障拒绝证据完成。组件说明、验收/偏差索引、progress/roadmap 与本项已同步；父项的生产真实 Home 重建、完整目标客户端与特定旧恢复身份等条件保持，未开始 R7G。 最终静态复核：12 份文档、573 个相对链接/锚点、4 个 Python 文件语法及 `git diff --check` 通过。

用户确认继续第 1 项。本轮在独立 QA 控制器、Home、账号、Profile 目录和 Docker 作用域中固定当前线上 Adapter、控制器、旧 Work 父镜像与受管理目标镜像。生产仅取只读版本/身份基线，保留三个运行浏览器。

- 完成条件：经实际管理员登录/近期认证执行旧记录迁移；真实 Firefox/Wayland 写入三类测试存储，经正常停止与新代次读回；实际管理接口回退精确原 App/Definition，保留 Home、journal、账号和不可变策略历史；重新批准迁移后确认同一 QA Home 的测试数据仍可读。当前版本网关故障与原始绕过拒绝只在该 QA 中验证。
- 代码地图：管理 HTTP/访问网关 → `legacy_migration.go` 生命周期锁及持久门禁 → 加密完整 App/策略 API → 固定控制器的正常停止/网络资源回收；真实存储观测复用 `check-work-direct.py` 的 BiDi/Wayland 路径。
- 验证与清理：固定摘要、实际迁移/回退及存储结果；确认全部 QA generation、控制器/代理进程、网络及 tmpfs 清理，生产身份保持。更新 Work/Adapter README、DEV-078、验收索引、progress/roadmap 和本项。独立 QA 结果不冒充生产 Work 回退或 Trilium 验收。
- 复核发现共享 `check-work-direct.py` 仍使用单字节 DNS 查询且把任意 OSError 算作不可达，沿 DEV-078 继续修复共享工具；原 R7B 与本日私有探针的历史范围保留。

## 2026-09-30 续跑：Personal 上游与健康重建前置

本轮结果：旧绑定当前探针仍超时，现有授权 `tw` r1 通过 SOCKS5/TLS/HTTPS。完成新停止时点 1,204 条目 age create/verify/独立 restore、1,035 个 Home 文件一致性核对后，用户经管理页完成绑定并打开；Personal revision 12、`tw` r1、独立 policy，新代次 `PROXY_OK`、浏览器/显示及 Worker 域名/TLS/HTTPS、有效四类绕过拒绝均通过。14:59 UTC 三个 Profile 均新鲜 healthy，Work/“测试”的 Session/容器身份保持，配置与代理目录未改，策略表只追加精确 Personal 策略、旧策略未变。详见 [本轮验收](../../infra/sealskin/r7f-personal-recovery-acceptance-2026-09-30.md)。

用户在 Mac 浏览器确认 Personal/Work 公网页面正常；原有书签/登录确认项不适用，未推断浏览器版本、视区或 Trilium 通过。DEV-069/071 已满足本次恢复/兼容绑定范围并关闭；DEV-070 已补新备份中的当前恢复身份/公钥/API 复核但仍缺特定旧身份拒绝。Work 正常重建/三类存储/实际回退、完整客户端矩阵及 r10 桌面证据继续待完成。此次没有产品代码或部署变更；设计/管理规格契约不变，更新组件操作范围、偏差/验收索引、progress/roadmap 和工作项。本项原完成条件不缩减，不开始 R7G。

阶段静态与资源收尾：16 份文档、641 个相对链接/锚点、`git diff --check` 及 4 个私有脚本语法通过。解密临时目录已清理，没有新建临时容器；实际运行/备份与用户反馈逐项核对后保留加密归档、未激活恢复副本及私有证据。R7F 父项未完成的复选框继续保留。

用户要求继续，本轮仍在 R7F 内处理 Personal 剩余条件。只读基线确认 Personal revision 9、绑定 `personal-tw-socks` revision 1、stopped/0 resources；Work 与“测试”均 running、各 1 Worker/5 resources，保留现有 Home、Session 和网络身份。

- 范围与完成条件：核对 Personal 当前绑定的上游和已存在且明确授权 Personal 的候选代理；使用现有 Secret Store 引用、精确 grant 和控制器有界 SOCKS5/TLS 探针，不提取凭据。形成当前可用/不可用及适用范围的证据，并复核备份/原应用和绑定前置。可用候选的实际绑定仍走管理页近期认证；新代次健康与用户端数据未验证前不收尾。
- 代码地图：`network_profiles.go:ProbeNetworkProfileDraft` / `grantFor` → `sealskin.Client.ProbeProxyDraft` → 管理员加密 `environment-management/proxy-probe` → Secret Store 精确授权 resolve 和进程内有界协议探测。此探针不启动浏览器、不创建容器、不追加策略、不撤销版本，也不代替新代次 Guard/Relay 健康。
- 验证与文档：保存前后目录/配置摘要及 Profile 资源身份、当前探针结果，更新 DEV-069/071、适用验收、progress/roadmap、工作项与索引；不部署 R7G，不改 Work 的成功代次。

## 2026-09-30 续跑：旧 Work 受管理网络迁移

用户已确认启用并打开 Work。12:47 UTC 运行检查为 **revision 8、enabled/running、DIRECT healthy**，精确镜像/Guard 归属、1 Worker/5 resources/1 Relay/1 Guard/2 networks 及经 Relay 的域名/TLS/HTTPS 通过。复核私有探针发现直接 UDP DNS 使用无效报文且把超时计为拒绝，立即登记 [DEV-078](../deviations/DEV-2026-09-30-078-work-dns-probe-evidence.md)；12:51 UTC 有效 DNS 查询分别得到 EPERM（Guard drop +1）和 ENETUNREACH，规则摘要不变，已补齐明确拒绝证据；原结果与失败保留。浏览器页面、原有数据及客户端类别已一次性请求用户确认，未反馈前不计通过。

此前实际迁移后的只读核对通过：Work revision 7、ready、无 pending、managed DIRECT、当时仍 disabled/stopped/0 resources，原 Home/Application/Firefox/Wayland 保留；完整 resolved App 与批准镜像及 policy 精确一致，迁移回执与目录策略摘要一致。随后用户经现有登录启用并从固定入口打开，未直接改目录或绕过访问网关。生产网络检查以只读健康、绑定与独立有界连接探测为主，故障注入仍使用独立 QA，不用真实 Home 的破坏性操作代替隔离证据。

本轮阶段结果：迁移与显式回退、持久门禁/重试、加密完整应用读回及 DEV-077 已通过代码与隔离验收；Adapter `7f4e2a1a…` 和私有批准目录已限定发布，发布时原 Profile/账号/应用/策略与 Session/Worker/网络身份保持。“测试”12:30 UTC 强制探测 healthy；Work 本次 5,195 条目 create/verify/独立 restore 成功，恢复副本未激活。管理页实际迁移、启用和打开已完成，详见[9 月 30 日验收](../../infra/sealskin/r7f-legacy-migration-acceptance-2026-09-30.md)。

阶段收尾：组件/设计/规格、DEV-077/078、验收索引、progress/roadmap 与工作项索引已同步。此次启用后只补运行证据和修正私有探针，产品设计及管理规格契约未变。Work 的 Firefox GUI 公网、实际回退、正常重建/运行数据，Personal 上游、恢复身份及 Mac/Trilium 条件仍保留；本项继续进行中，不开始新计划。

发布阶段静态复核：13 份文档、668 个相对链接/锚点通过，76 个源码文件匹配最终测试快照；临时 Go/checks 容器与解密 tmpfs 已清理，备份/恢复副本、批准输入及回退材料保留。启用后更新的 12 份文档、599 个相对链接/锚点与 `git diff --check` 再通过；本轮只读补测没有创建临时容器或改变生产生命周期。

用户确认继续开发。本轮在 R7F 内补齐服务端批准的 legacy → managed DIRECT 迁移，不启动 R7G 发布。既有 83 个修改文件和 34 个未跟踪文件保留。

- 范围：服务端固定原 Profile/Home/App、原应用摘要、已验收目标镜像及备份/验收摘要；管理端只提交迁移 ID、revision、幂等键，沿用管理员授权、近期密码确认、CSRF 和生命周期锁。保留 Firefox/Wayland、Home、账号和禁用状态，不伪造 Camoufox 模板。
- 完成条件：运行中或有残留资源时无修改；原应用/目录漂移拒绝；先写持久启动门禁，再追加精确 DIRECT 策略、替换应用及提交目录；失败/响应丢失后同请求可恢复，异请求拒绝。通过协议、服务、网关及并发/重启恢复验收后，形成明确可复核的发布候选。
- 代码入口：`config/main` → 管理 HTTP 授权入口 → `profile` 目录与迁移状态 → 管理员加密 API（读取完整应用、追加策略、完整 PUT）；SealSkin 继续独占容器生命周期。
- 代码核对发现 `Ensure` 在取得生命周期锁前读取目录，等待期间可能跨过配置变更门禁，立即登记 [DEV-077](../deviations/DEV-2026-09-30-077-launch-definition-lock.md)；本轮先修复锁内读取并覆盖并发回归。
- 验证：固定 Go 1.27 隔离 test/vet/race、真实加密协议夹具、独立 QA 状态文件；生产只读基线与最终发布输入核对。真实 Work 公网/数据恢复及 Mac/Trilium 未完成前，父项保持进行中。
- 文档清单：Adapter/Work README、设计和管理规格、偏差与验收索引、progress/roadmap、工作项索引及本记录。

## 2026-09-29 续跑范围：发布事实与剩余条件核对

用户在查看当前进度后要求继续。本轮沿 R7F 推进，不将 R7G 候选部署到生产。先核对已部署二进制、目录、Profile 实际资源、r10 新鲜健康、既有加密恢复证据和 Work 迁移前置，再整理可复核的 Work 候选及回退输入。现有“测试”浏览器的 Home、Session 和运行资源保留。

- 完成条件：形成新的脱敏服务器核对报告；区分已有备份/绑定与仍缺的运行验收；明确 Work 精确镜像、DIRECT 前置、目录迁移路径和未满足条件；同步当前进度、计划、组件说明与验收索引。
- 验证方法：生产只读 `inspect`/`probe`、实际进程和镜像摘要、目录与控制器配置一致性；隔离工具链执行适用回归。不能用服务健康代替 Mac/Trilium 或 Work 公网验收。
- 发现部署说明与最新生产事实混杂，记录为 [DEV-075](../deviations/DEV-2026-09-29-075-release-status-drift.md)，本轮修正文档并保留各历史验收的原范围。
- 需要真实客户端的确认已请求；未经反馈的项目继续待验证。管理绑定继续使用现有近期认证和生命周期门槛，不直接修改生产目录。
- 发布准备发现 Adapter 丢失控制器的 DIRECT 能力字段，见 [DEV-076](../deviations/DEV-2026-09-29-076-direct-capability-observation.md)。本轮补齐只读协议和 inspect 映射；验证后只发布 Adapter，保留原二进制并复核全部 Profile 运行身份。

## 范围与授权

本轮结果（2026-09-29）：[生产续跑验收](../../infra/sealskin/r7f-production-review-acceptance-2026-09-29.md)已记录 Adapter `346d6377…` 限定发布、DIRECT 能力真实观测、全量 Go/五包 race、Work 5,195 条目加密归档/verify/独立 restore、15 项 Work 前置及不可部署的迁移草稿。Personal 实际已绑定代理目录 revision 1，历史 1,193 条目备份/恢复回执已核对；旧的“尚未绑定/未备份”仅是下方历史阶段结论。生产配置、账号、Home、Session、Worker 和网络身份保持，“测试”新鲜 healthy。DEV-075/076 由本轮处理；R7F 原完成条件不缩减，仍缺 Work 迁移路径/生产公网、Personal 当前上游、恢复身份和目标客户端等条件。

后续仍在 R7F 内推进：先补齐旧 Work 从 unmanaged 进入受管理网络的可审查迁移路径，沿用本轮匹配备份、原 Firefox/Home、已验收镜像和近期认证/生命周期门槛；不能直接安装仅换镜像的草稿。生产 DNS/HTTPS/故障关闭/正常换代与数据恢复、Mac/Trilium 确认分别留证。R7G 不在本轮部署。

本轮收尾核对：DIRECT 需求/代码/加密协议/线上观测一致；Go 与 Python 回归、限定发布和身份保持通过；Work 备份与未激活恢复副本、不可部署草稿和旧二进制已留存；DEV-075/076、组件/设计/规格、验收索引、进度与计划已同步。19 份文档的 747 个相对链接/锚点及 `git diff --check` 通过，测试容器和解密 tmpfs 已清理。真实客户端未收到反馈，R7F 父项继续进行中。

- 对应 [R7 方案](../browser-workspace-plan.md)第 6 步；用户于 2026-09-23 在明确获知本项包含生产维护、Work 启用和目标客户端验收后授权继续。
- 固定 R7A–R7E 的 Adapter、控制器 overlay、Work 受管理镜像、生产模板目录与代理目录配置，形成可独立复核和回退的发布候选。
- 发布前保留当前 Adapter 二进制、配置、Profile/账号/Session/控制状态摘要及 Personal/Work Home 的匹配时点加密恢复材料；只在既有生命周期所有权内停止、更新和恢复。
- 发布候选后验证登录、管理页、首页、Personal 保持、Work 受管理公网、DNS/HTTPS、Guard/Relay/DIRECT、故障关闭、正常停止/换代和 Home 数据恢复；目标 Mac/Trilium 验收首页、代理 Tab、三个模板选择与浏览器打开。
- 公开记录只保存脱敏摘要；Cookie、密钥、代理凭据、Session URL 和原始私有证据留在忽略的 `infra/sealskin/runtime/`。

## 明确边界

- 不删除或重建 Personal/Work 真实 Home，不复用 Personal 的策略、Secret Store 授权或 generation 给 Work。
- 不把 Work 接入裸公网 bridge，不以关闭 Guard、放宽宿主机防火墙或手工删除占用完成验收。
- 不修改账号密码或 Trilium Core；模板切换、网络绑定和启用只使用已验收目录、stopped/0-resources 门槛及现有 revision/幂等契约。
- 工作树含 R7C–R7E 及更早文档/运维改动；候选须用显式文件清单和摘要固定，不夹带未审查的 `__pycache__` 或运行材料。

## 完成条件

- [x] 发布包清单、源码/配置/镜像摘要、回退二进制和恢复入口经独立静态核对；全量 Go test/vet/gofmt、关键包 race 与适用控制器回归通过。2026-09-30 由最终 Adapter/当前控制器适用测试、精确源码复建及 [352 文件定版核对](../../infra/sealskin/r7f-server-release-seal-acceptance-2026-09-30.md) 补齐；不包含异机灾备或客户端通过。
- [ ] 生产维护前基线证明 Personal 身份与受管理网络健康，Work disabled/stopped/0 resources，服务、配置、账号/Profile/Home/Session 摘要和备份可恢复。
- [ ] R7 Adapter/控制器及目录配置按限定服务切换；失败自动或显式回退时保留 Home、journal、账号和 Session 密钥。
- [ ] Work 使用独立受管理 DIRECT 或明确选定的统一代理修订，真实 DNS/HTTPS 与出口成功，Guard/Relay/网关故障时无直连回退；停止重建后 Cookie/localStorage/IndexedDB 及用户数据抽样恢复。
- [ ] Personal 入口、显示、代理、Home 与现有数据保持；登录、首页、管理页、授权边界和敏感信息脱敏通过。
- [ ] 目标 Mac/Trilium 1280×800 验收新首页、网络代理 Tab、浏览器/指纹/显示模板选择、Personal 与 Work 打开；未确认项保持待验证。
- [ ] 更新组件说明、设计/规格、验收索引、progress/roadmap 与本工作项；记录部署版本、生效范围、回退材料和所有未完成条件。

## 发布前候选准备 · 2026-09-23

已完成不触碰生产的第一阶段准备：

- 基线固定为 `ab6b1586549ebadae591a5a149d571eba7f56032`；实际发布 payload 显式清单共 32 个代码/配置/测试脚本文件，纯文档/验收/runtime/cache 排除；私有运行清单 SHA-256 为 `db535e22d789de19d2af424cfcc66e628a3d1f7996963c7f46fd9cfe67666cf5`。
- 已移除 `infra/work-firefox-managed/__pycache__/` 生成缓存，运行材料和缓存不进入候选。
- Adapter 与 Relay 的固定 Go 1.27 全量 test、vet、gofmt 和 `git diff --check` 通过；checks 镜像挂入固定 Go 1.27 后，Adapter `profile/httpapi/access/control` 关键包 race 与 Relay 全包 race 通过。
- 2026-09-23 当时的适用 lifecycle pytest 为 **5 passed / 117 skipped**；skip 来自 checks 环境没有 `age`。2026-09-27 已按下方续跑记录补齐为 118 passed，但第一项还包含发布包、回退二进制和恢复入口，仍保持未勾选。
- 公开脱敏记录见 [R7F 发布前候选静态验收](../../infra/sealskin/r7f-prerelease-acceptance-2026-09-23.md)。

本阶段当时没有替换 Adapter/控制器，没有启用或启动 Work，没有停止 Personal，也没有修改真实 Home、账号、Session、凭据。后续 2026-09-27 的代理地址偏差处理已新增精确授权的 Secret Store 版本和不可变策略，但仍未绑定或切换运行 generation。

## 生产维护前只读基线 · 第一轮

- 生产 Adapter 服务 `active`；实际二进制 SHA-256 仍为 R6H `fe4e13c4676afb8ab7b1f5cef17d6f0514a3a691942c1fe8c7dde1b481ca34fa`，本轮未替换。
- 生产配置 SHA-256 `dafa9bf8…054ee`，状态 `c8d2e728…a5a12`，Profile 目录 `78f2f455…48726`，入口账号表 `92cf7655…b2426`；仅记录摘要，不公开文件内容。
- Personal inspect：running，1 record / 1 Worker / 0 orphan / 5 resources / 1 Relay / 1 Guard / 2 networks，network phase running；强制只读 probe 后报告已新鲜，但代理项仍为 `PROXY_UPSTREAM_UNKNOWN`，整体 `unknown`。因此“Personal 受管理网络健康”尚未满足，不能进入完成勾选。
- Work inspect：stopped，records/workers/orphans/resources/relays/guards/networks 均为 0。当前 Profile/配置格式没有独立 `enabled` 布尔值可由本轮只读脚本证明，因此只记录已观察到的 stopped/0-resources，不把旧文档的 disabled 状态重新当作本轮证据。
- 本轮没有执行 stop/reconcile/resume、没有重启服务、没有打开 Work、没有修改配置或 Home。

继续发布前必须先解释或恢复 Personal 的上游探测结果，并完成匹配时点恢复材料；在此之前生产切换条件保持未完成。

## 2026-09-27 续跑：备份回归与生产网络前置

- 使用固定 checks 镜像 `sha256:7de36814…`、固定 `age v1.2.1`、无网络和只读源码重新执行 `test_secure_backup.py`、`test_secure_backup_legacy.py`、`test_secure_backup_coherence.py`、`test_secure_backup_runtime_nodes.py`，最终 **118 passed**。首次 117 passed / 1 failed 来自 `/tmp` 默认 `noexec`，旧部署 CLI 集成测试按设计需要执行临时生成的 fake Docker CLI；改为仍受限但显式 `exec` 的一次性 tmpfs 后，原测试和断言未经修改全部通过。因此缺少 `age` 导致的 117 项未验证已补齐，但发布包、回退二进制和匹配时点生产恢复材料尚未全部完成，第一项完成条件仍不勾选。
- 生产 Adapter 摘要仍为 `fe4e13c4…`；Personal 仍为 running、1 record / 1 Worker / 5 resources / 1 Relay / 1 Guard / 2 networks，Work 仍为 stopped 且全部运行资源为 0。连续强制探测得到 `PROXY_UPSTREAM_UNKNOWN` / `PROXY_PROBE_TIMEOUT`，整体保持 unknown；entry/control/session/worker/browser/display/freshness 均通过。
- 只读分层诊断确认探测目标 `https://example.com/` 从宿主机正常返回 200，策略冻结地址与 VPS 系统解析器返回的单个地址一致，Relay 的 nft 输出规则仍只允许精确上游地址/端口且没有观察到末端兜底丢包；但是从宿主机和受控 Relay 网络到既有上游端点的 TCP 建连均连续超时，Relay 只记录脱敏 `UPSTREAM_UNREACHABLE`。后续对照又确认 Cloudflare `1.1.1.1` 和 Google `8.8.8.8` 均对该代理主机名返回 `NXDOMAIN`，同一解析器的 `example.com` 控制查询为 `NOERROR`。因此 VPS 系统解析结果可能是私有/缓存地址，不能再作为当前公开 DNS 正常的证据；需要代理供应方恢复记录，或从实际可用客户端取得当前节点地址后建立新的受管修订。
- 在上游恢复前停止 Personal 会使原策略下的健康重建失去前置保证，因此本轮没有 stop/reconcile/resume、没有重启服务、没有修改策略/凭据/Home，也没有执行 R7 生产切换。匹配时点 Personal 备份必须等待上游恢复并重新取得 `PROXY_OK` 后进行；不切换到 VPS 直连，也不以 Work 的 DIRECT 候选替换 Personal 现有策略。
- 用户随后提供其实际可用客户端的解析结果；该公开 IPv4不同于冻结地址和 VPS 系统解析结果。从 VPS 使用现有受管凭据对该数值地址完成 SOCKS5 认证、CONNECT、TLS 与 HTTP 200，说明凭据和代理服务可用，问题是解析视角/地址漂移，已登记 [DEV-069](../deviations/DEV-2026-09-27-069-proxy-dns-address-drift.md)。下一步先经控制器 Secret Store 与隔离探针建立新不可变修订；旧 generation 在新修订通过前保持不动。
- 已经由生产控制器的 TLS、管理员 JWT 和端到端加密接口导入新的凭据版本，授权范围精确为 Personal 当前 Profile/Home/Application；控制器侧草案探针返回 `PROXY_PROBE_OK`、HTTP 200。探针通过后追加不可变策略 `personal-camoufox-r9-socks5-r2`，摘要 `2ad6aa03…1fed`。Profile 绑定仍指向旧修订，Personal 仍运行原 generation；此准备步骤未停止浏览器、未修改 Home，也未放宽 Guard。
- 下一步是固定本次生产候选与回退材料，然后正常停止 Personal、确认 0 resources 并生成匹配时点 age 备份。只有备份 verify 与隔离 restore 通过后，才允许部署限定 R7 组合并将 Personal 绑定切换到已探针通过的新策略。
- 停机前读取旧备份元数据时，一份旧 `admin` 恢复私钥被错误输出到本次私有操作会话，已登记 [DEV-070](../deviations/DEV-2026-09-27-070-private-recovery-key-transcript-exposure.md)。当前生产管理调用使用独立 `profile-admin`，因此继续受控维护；R7F 收尾前必须让旧 `admin` 私钥失效并重新验证恢复材料。

### 2026-09-27 管理员轮换复核

- 新 `admin` 恢复身份通过控制器加密管理 API；Adapter 使用的独立 `profile-admin` 控制身份仍可完成启动期控制面对账。
- 新生成的无关签名身份被控制器返回 401，证明未授权身份不会被接受。
- 旧 `admin` 私钥已不在私有运行材料中，无法做逐字的旧身份拒绝测试；[DEV-070](../deviations/DEV-2026-09-27-070-private-recovery-key-transcript-exposure.md) 保持打开，直到取得不泄露私钥的旧身份拒绝证据或由维护者确认关闭。
- Personal 的 R7C 目录绑定尚未执行：管理写操作要求现有入口管理员会话及近期密码确认，不能以直接编辑目录或绕过网关代替绑定流程。

## 验证与清理

- 构建与自动化使用固定工具链和独立缓存；网络/浏览器 QA 使用独立命名资源，结束后核对 Session、Worker、Guard、Relay、network、volume 和临时端口清零。
- 生产检查在每个有副作用步骤前后记录同一组脱敏身份与计数；HTTP 200、容器 running 或页面一次打开不能单独视为完成。
- R7F 完成前不开始新的产品功能；如目标客户端确认尚未返回，保持待验证并明确服务器端已完成范围。

## 2026-09-29 新建浏览器退出事件

- 用户经已上线的新建流程创建 Camoufox 模板化浏览器后，窗口在使用中消失。只读核对证明 Profile 目录记录、Home、Worker、Relay 和 Guard 仍在，浏览器主进程退出，健康状态为 `BROWSER_EXITED`。
- Home 中 core 确认为 Camoufox 主进程 `SIGSEGV`，容器未被 OOM 杀死。原始 core、Home 和所有运行资源均保留，本轮没有停止、重启、删除或读取用户网页数据。
- 桌面右键菜单的 Firefox 来自基础镜像，命令为系统 `/usr/bin/firefox`，不是绑定指纹产物的 Camoufox。现有 `BROWSER_EXITED` 恢复提示沿用早期原生 Firefox 路径，错误要求所有 Profile 右键启动 FireFox，已登记 [DEV-073](../deviations/DEV-2026-09-29-073-managed-browser-desktop-recovery.md)。
- Adapter 候选已将模板化 Profile 改为经管理页“安全关闭”和固定入口新代次恢复，不再提示桌面 Firefox；针对性 Go 测试通过。Worker r10 候选 `sha256:9a128663…` 已移除系统 Firefox 菜单与启动入口，并通过 2 项桌面单测、11 项启动拒绝、两 Home 各 10 次重建、离线恢复及独立正常 X11/Selkies GUI。隐藏 Camoufox 后桌面右键没有产生新窗口，系统 Firefox 文件/进程不存在，正常停止后 Home 锁释放且未生成 core；GUI 临时资源已清理。首轮纯内网缺 Relay 的失败报告保留，第二轮受管 Relay验收通过，详见 [r10 候选验收](../../infra/camoufox/managed-desktop-recovery-acceptance-2026-09-29.md)。目标 Mac/Trilium 和生产发布仍待完成，R7F 保持进行中。
- 用户随后明确授权发布 r10 并安全恢复“测试”浏览器。发布演练发现环境登记器缺少 R7D 模板一致性元数据，已登记 [DEV-074](../deviations/DEV-2026-09-29-074-environment-registration-template-metadata.md)；生产目录、Adapter 和当前故障代次在修复及回归通过前保持不变。
- 2026-09-29 维护窗口：登记器修复及 9 项单测、Adapter 全量 Go test/vet 通过；r10 以 `f785549f…` / acceptance `c7e3c6d9…` 登记到生产环境目录，兼容目录追加唯一 r10 组合；Adapter 候选 `bbef7657…` 原子替换并重启，`readyz` 200。按授权对“测试”执行安全关闭，Profile 已 stopped 且 records/workers/orphans/resources/relays/guards/networks 全为 0，Home 保留。下一步需管理员在管理页近期确认密码后把该 Profile 的环境选择从 `env-tw-camoufox-r9` 改为 `env-tw-camoufox-r10`，再启动固定入口并复核新镜像/右键限制；未绕过该门槛。
- 管理员已完成近期确认和模板提交；“测试”现为 Profile revision 7，绑定 `env-tw-camoufox-r10` / `f785549f…`，在该维护步骤结束时保持 stopped/0-resources。随后用户从已登录的固定入口创建新 Session，结果见下方 2026-09-29 复核。

## 2026-09-29 固定入口恢复复核

- 用户已从固定入口重新打开“测试”。Adapter 强制 `probe` 于 14:04 UTC 返回 `overall=healthy`；`BROWSER_RUNNING`、`DISPLAY_READY`、`PROXY_OK`、`SESSION_RUNNING` 与 `REPORT_FRESH` 全部通过，未生成 recovery 阻断。
- 运行态为 1 record / 1 Worker / 5 resources / 1 Relay / 1 Guard / 2 networks，绑定环境 `env-tw-camoufox-r10`，artifact SHA 为 `f785549f…`；Home 保留。
- 该结果完成了 r10 生产固定入口和服务器端恢复条件，但不替代生产远程桌面实际右键行为的直接用户证据，也不替代 Mac/Trilium 复测、Work 公网及 R7F 其余组合条件。工作项继续保持“进行中”。
