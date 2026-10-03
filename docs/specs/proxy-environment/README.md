# 代理与浏览器环境配套规格

当前交付证据入口：[server-2026.10.02.3](../../releases/server-2026.10.02.3.md)与[R6AS矩阵](../../../infra/sealskin/r6as-fixed-version-matrix-acceptance-2026-10-02.md)。动态控制器/Relay、共享缩放保存、旧Work兼容及原生启动180秒预算已部署；本轮R6AT只统一封存，没有更改产品契约。供应方缺证和各验证对应的实际版本继续明确保留。

R6AS已补齐Camoufox152、Chromix154.0.8037.57、Firefox155.0.1的六协议认证与受管理DIRECT固定矩阵，以及注明版本的升级/恢复/回退证据，见[验收](../../../infra/sealskin/r6as-fixed-version-matrix-acceptance-2026-10-02.md)。LaunchURL按顺序创建网络与原生Worker，使用与恢复相同的180秒有界等待；取消/歧义仍保留独占与操作身份。此结果不扩展为商业供应方自然漂移或任意浏览器大版本迁移已测。


R6AE更新：修改密码在首页/管理页打开共享弹窗，原地址保留无脚本回退；密码创建、重置和自助修改最低4、最高256个UTF-8字节，原哈希强度、当前密码验证、CSRF和其他登录撤销语义保留。浏览器详情按概览、常用设置、网络、环境模板、危险操作分页签，代理/账号按实际功能分组；短表单保持单页。指纹四类删除为直接按钮打开对象确认框，原引用保护和确认勾选保留。 见[本项验收](../../../infra/sealskin/r6ae-dialog-layout-password-acceptance-2026-10-02.md)。

[文档导航](../../README.md) · [当前架构](../../design.md) · [开发进度](../../progress.md) · [验收索引](../../acceptance/README.md)

原设计第 45–50 节已独立为 [规格正文](specification.md)，保留原章节与验收编号。本目录定义目标契约和配套数据示例，不会自动部署 SealSkin、代理或浏览器，也不表示所有 API、协议和健康能力已经实现。当前实现与缺口以 [开发进度](../../progress.md) 为准，测试证据由 [验收索引](../../acceptance/README.md) 导航。

2026-09-29 R7F 补齐 Adapter 对控制器 `network_direct_version` 的只读传递，缺字段仍为 0，不扩展现有运行能力要求的配置集合。DIRECT 的运行契约不变；当前生产与 Work 未迁移边界见 [续跑验收](../../../infra/sealskin/r7f-production-review-acceptance-2026-09-29.md)。

| 文件 | 用途 |
| --- | --- |
| [specification.md](specification.md) | 代理、环境、一致性、网络、健康、凭据的要求与 P/E/C/N/H/S 验收 |
| [types.go](types.go) | 使用标准库的 Go JSON 数据契约；不是服务实现 |
| [schema.sql](schema.sql) | 在空库执行的 SQLite 规格快照；不是旧表或 SealSkin YAML 的迁移 |
| [management.md](management.md) | R6 管理面第 2 版：新增/修改/删除远程浏览器、代理或 DIRECT、固化/自定义指纹、入口账号、关闭与 launch plan；R6A–R6F 已于 2026-09-20 收尾 |
| [config.example.json](config.example.json) | Camoufox + 带认证 SOCKS5、Chromium + DIRECT 两种配置 |
| [health.example.json](health.example.json) | 带分项结果、新鲜度和 UNKNOWN 的合成健康报告 |

示例中的域名、secretRef、Session ID 均为占位值。`203.0.113.10` 是文档地址，报告中的 US 是测试夹具，不代表对该地址的真实地理定位。

两个 Profile 初始 `enabled=false` 且未绑定环境产物。导入时只能创建草稿；配置受控探测端点、解析器和密钥，选定已测试的引擎/镜像版本，物化环境并通过能力校验后，才能绑定 `environmentArtifactId` 和启用。配置中的 Camoufox 必需能力是验收要求，不是本仓库已经实现的功能。

`persistentHome` 是适配层命名空间内的逻辑标识，由服务解析为 SealSkin 用户下的命名 Home 或受控宿主机路径；客户端不能提交任意挂载路径。`NetworkPolicy.mode=direct` 表达 DIRECT，不创建伪造的直连代理地址。

JSON 到 SQL 的映射：`RevisionRef` 展开为 `_id`、`_revision` 列；`expectedLocation` 展开为 `country/region/city`；策略和环境同时存储完整 JSON；`network_mode` 从被引用策略派生，不接受调用方单独赋值；其余结构体字段按 camelCase → snake_case 映射。Profile、修订记录的时间由服务生成。SQL 标量和 JSON 中重复出现的字段必须在同一事务中一致写入，读取时校验一致性。

生产连接逐一启用 `foreign_keys`，使用 WAL 和短事务；SQL 校验不能代替 JSON 语义校验、网络强制策略或运行实例核对。修订一经发布不可原地修改；配置修改新建修订，在对应 Profile 停止并解除占用后切换引用。

可用 Python 标准库的 `sqlite3` 在临时数据库执行建库规格。若已安装 Go，可在本目录使用 `GO111MODULE=off go test` 检查类型声明能否编译；这不验证浏览器行为。网络、Profile 恢复和环境稳定性必须执行 [规格正文](specification.md) 中的 Linux 集成验收。

R6L 已交付 [Chromix 154 固定模板](../../../infra/chromix/README.md)：仅 Linux/en-US/UTC/1280×720/DPR1，独立 Home/稳定种子与受管网络；服务器部署通过，用户已创建并打开首个生产Chromix/DIRECT，完整目标客户端矩阵仍待验证。完整跨接口指纹及其他组合未测，不等同全部 E/C 组完成。

R6P 独立指纹源与显示策略、版本引用及组合验收要求见[管理规格](management.md#r6p独立指纹模板与显示模板)。

R6Q 通用指纹来源与生成目标分离：配置不绑定引擎，生成作业及最终产物仍精确绑定引擎版本；旧来源和队列兼容见[管理规格](management.md#r6q-通用指纹配置与生成目标)。


R6R 三引擎自定义生成及能力限制见[管理规格](management.md#r6r-三引擎自定义生成)和[组件操作](../../../infra/environment-engines/README.md)。

R6S当前共享显示来源契约见[管理规格](management.md#r6s-三引擎共用显示模板)：自定义fixed/DPR1与内置auto/system均供三个引擎使用，交付状态单列。

当前39项规格的实现、对应测试、实际部署与缺口见[R6T审计](../../../infra/sealskin/r6t-server-plan-audit-2026-10-01.md)。本页和规格正文的日期段落保留历史时点；当前采用R6S Adapter与R6J1控制器，不以旧“未部署”段落覆盖后续组合交付。
