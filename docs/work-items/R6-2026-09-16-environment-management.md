# R6 · 远程浏览器管理面（设计与父项）

状态：进行中（父项；设计已于 2026-09-17 修订为第 2 版，子项 R6A、R6B 已收尾）。登记日期：2026-09-16。实现日期：2026-09-17。结束日期：未结束。

> 2026-09-17 需求修订：用户要求面板可以新增/删除/修改远程浏览器，为每个浏览器配置代理（不配置就直连）、指纹（固化或自定义）、浏览器页面登录 URL 与账号密码。第 1 版提案（只在已有 Profile 间选择、不新增/删除、指纹只可从已验收产物选择）已按此修订，见[管理面规格第 2 版](../specs/proxy-environment/management.md#需求与修订说明)；修订只改设计文档，未改代码或生产。“登录 URL 与账号密码”按平台入口账号理解；用户同日确认，并补充两级访问：登录管理面板需要管理员账号密码，登录单个远程浏览器入口也需要各自账号密码。R6A 候选对任意登录账号放行列表，已登记 [DEV-045](../deviations/DEV-2026-09-17-045-manage-list-role.md)，后由 R6B 修复。

## 目标与范围

- 对应 [R6 后续产品能力](../roadmap.md#r6) 和 [环境管理面规格](../specs/proxy-environment/management.md)。
- 设计并最终实现：面板新增/修改/删除远程浏览器；每个浏览器的代理（http/https/socks5）或无代理（受管理 DIRECT）；指纹（固化目录或自定义高层规格经生成/验收作业）；固定入口 URL 与访问账号密码管理；安全关闭。
- 继续使用 Adapter 作为业务授权和 Profile 状态所有者，SealSkin 作为 Session/Docker 生命周期所有者；不在客户端直接操作 Docker、Home 或上游代理。
- 当前交付为设计文档（第 2 版）与子项 R6A、R6B 的候选代码；两项均未部署，本记录不表示 R6C–R6F 已实现或验收。

## 设计结论

- 访问使用现有 R5D 的 HTTPS 表单登录、短期 Cookie、CSRF、Origin、Profile 授权和显示 Cookie；账号表增加 `admin`/`user` 角色：管理面板仅管理员，浏览器入口用各自分配的账号；面板可创建/重置/禁用账号并分配浏览器，展示固定入口 URL；管理员敏感操作需近期重新认证；不使用长期 HTTP Basic。
- Profile 定义改为 Adapter 私有的可修订目录，运行中可增删改；现有静态配置首次启用时导入。Adapter 增加只用于管理面的管理员 SealSkin 客户端安装/删除应用定义与创建 Home；SealSkin 仍是唯一 Docker 生命周期所有者。
- 指纹：固化产物目录（`accepted` 且镜像摘要匹配）或自定义——只接受规格 46.2 高层字段，服务端隔离生成并完整验收后发布；禁止运行中切换任意指纹字段。
- 代理先进入短期草稿，凭据写入 Secret Store，隔离探针通过后固化 ProxyConfig/NetworkPolicy 修订；无代理即受管理 DIRECT；Worker 始终经 Guard/Relay 或 DIRECT 网关，不能裸直连或热切换。
- 关闭复用现有 `profile.Stop`/`Reconcile` 状态机，撤销显示访问并保留 Home；停用、删除（归档 Home）和物理清除是不同的管理员动作。
- 启动由服务端生成一次性 `launch_plan`，冻结账号、Profile 修订、Home、Artifact、代理、网络策略和能力摘要，客户端不能提交任意后端参数。

## 阅读与代码核对

| 材料 / 代码入口 | 当前结论 |
| --- | --- |
| `adapter/internal/access`、`infra/sealskin/entry-auth/` | 已有账号密码、Profile 授权、短期登录/显示 Cookie、CSRF、Origin 和日志边界，并已随 R4B 组合部署生产 |
| `adapter/internal/profile` | 已有 Ensure/Stop/Reconcile、Home 独占、持久化停止意图和 UNKNOWN 保留；关闭按钮应复用，不新增 Docker 路径 |
| `adapter/internal/sealskin` | 已有 Session、Worker、Guard/Relay、环境身份和运行时能力快照 |
| `docs/specs/proxy-environment/{types.go,schema.sql,specification.md}` | 已有 Profile、环境产物、代理、网络策略、运行绑定和审计的参考契约；修订不可变、停止后切换 |
| R5A/R5B/R5D 验收 | 代理协议/认证、Secret Store、入口认证和显示授权已有隔离候选，均须与 R4B 生产材料合并后再发布 |

## 实施与偏差

设计阶段未修改代码、配置、账号、Home、Session 或生产资源。R6A、R6B 随后完成 Adapter 候选代码与 Go 隔离测试，生产仍未修改；DEV-045、收尾复核发现的 DEV-046 与规格锁契约 DEV-047 已由 R6B 处理。后续如发现“手动选择”需要跨 Home 复用、代理地区与指纹冲突、或 SealSkin 缺少所需控制能力，必须建立单独偏差记录，不降低验收条件。

## 验收复核

| 原要求 | 实现位置 | 预定检查 | 当前结果 |
| --- | --- | --- | --- |
| 两级访问：管理员面板与浏览器入口账号 | Adapter access / 账号表 v2 | 未授权、过期、撤销、CSRF、限速、显示 Cookie；`user` 不能进入面板、无写能力；管理员重新认证；最后管理员保护 | R6B 已实现并通过 Go 测试；[DEV-045](../deviations/DEV-2026-09-17-045-manage-list-role.md) 已解决；候选未部署，真实客户端归 R6F |
| 新增/修改/删除浏览器 | Profile 目录、管理员 SealSkin 客户端、Home 归档 | 修订/乐观锁、运行中限制、删除前资源为零、归档保留、应用与授权撤销 | R6B 已实现目录、标签/起始页/停用修改与热更新；新增、删除、应用和 Home 创建/归档仍归 R6C |
| 代理或 DIRECT | Secret Store / Relay / proxy draft / DIRECT 策略 | 凭据脱敏、隔离探针、无裸直连、修订绑定、DIRECT 前置 | 设计完成，未实现（R6C/R6D） |
| 固化/自定义指纹 | 环境目录 / 生成验收作业 / Profile 修订 | 只绑定 `accepted` 产物、作业隔离与失败保留、运行中拒绝、Home 独占 | 设计完成，未实现（R6C/R6E） |
| 手动关闭 | `profile.Stop` / `Reconcile` | 正常关闭、失败保留、资源清理、Home 保留 | R6B 已实现管理入口并通过处理器/网关测试；真实控制器与客户端组合归 R6F |

## 文档与收尾

- [x] 架构设计、代理/环境规格和 R6 路线图已登记；2026-09-17 按用户需求修订为第 2 版并同步设计/计划/进度。
- [x] 现有入口、状态所有权、凭据和生命周期边界已核对。
- [x] 创建实现子项并开始代码工作：[R6A 授权环境列表](R6A-2026-09-17-environment-list.md) 于 2026-09-17 开始并收尾（用户决定不等待 R2 剩余条件；候选未部署）。
- [x] [R6B Profile 目录、账号角色、管理员面板与关闭按钮](R6B-2026-09-17-directory-roles-stop.md) 于 2026-09-18 完成 candidate-2 代码、Go 隔离验收与文档收尾；DEV-045–047 已解决，未部署生产。
- [ ] 完成独立 QA、客户端验收、生产候选、部署与回退。

收尾结论：第 2 版设计完成；R6A、R6B 已收尾，父项保持进行中直到新增/删除、应用与 Home 生命周期、代理/DIRECT、固化/自定义指纹及组合 QA 完成。下一步：R6C（新增/删除浏览器、固化指纹与 DIRECT/现有代理修订），尚未开始。
