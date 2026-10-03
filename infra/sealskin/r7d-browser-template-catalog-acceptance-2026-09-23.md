# R7D · 指纹、浏览器与显示模板兼容目录验收 — 2026-09-23

[验收索引](../../docs/acceptance/README.md) · [当前进度](../../docs/progress.md) · [R7D 工作项](../../docs/work-items/R7D-2026-09-22-browser-template-catalog.md) · [R7 v4](../../docs/browser-workspace-plan.md)

日期：2026-09-23。状态：**Adapter 模板目录、兼容约束、停止后应用/回退、管理 JSON API 与自动化通过，未部署生产**。本项没有启动或停止生产 Personal/Work，没有修改真实 Home、账号、Session、网络策略、代理凭据或生产应用；生产 Adapter 仍保持既有 R6H 版本和配置。

## 实现范围

- 新增可选 `template_catalog`，要求 `environment_catalog`。目录是私有、严格 JSON version 1，分别保存 accepted browser templates、display templates 与显式 compatibility 三元组；缺字段、未知字段、非 accepted、重复/未知引用均拒绝。
- 浏览器模板固定 engine、version、Linux OS、platform、UA 产品族与 `allow_new_browsers`；`firefox_legacy` 不允许普通新建。环境 artifact 增加 R7D coherence metadata：template revision、browser template ID、engine/version、OS/platform、完整 User-Agent；同时继续使用 accepted artifact 的 locale/languages/timezone、screen/DPR 与 SHA-256。显示模板固定 X11/Wayland、Selkies、screen/DPR 与 fixed/fit scaling。
- compatibility 解析时要求 artifact/browser/display 三者完全匹配；engine/version/UA 产品+版本、OS/platform、locale=languages[0]、timezone、screen/DPR 任一不一致即 fail closed。旧 R6 artifact 缺 R7D 元数据时继续可由旧兼容路径读取，但不会自动进入 R7D 模板目录。
- `GET /manage/templates` 只返回脱敏后的 accepted compatible combinations，不返回完整 UA 或生成的低层指纹值。启用 R7D 后，新增浏览器必须同时提交允许新建的 browser template、accepted environment artifact 与 display template；不能再用裸 artifact 绕过组合目录。
- `POST /manage/browsers/{id}/template` 提供服务端 apply/rollback API，要求目标浏览器的 manage grant；存在 access gateway 时还要求近期 reauth。运行中或资源不为空返回冲突，且不会隐式调用 Stop。
- 模板切换在同一 Profile 生命周期锁中先证明 stopped 且 records/workers/resources 全为零，再持久化 `RecordUpdating` + pending target 作为启动门禁；随后对 SealSkin installed app 使用完整 PUT，而不是会 deep-merge 的 PATCH；最后提交新 Profile revision。应用替换失败或进程中断时 pending 状态保留，`Ensure` 拒绝启动，同一 base revision/target/idempotency key 可继续。
- 每次成功切换把上一套完整 R7D 模板绑定按 Profile revision 存入历史；显式 rollback 只能回到历史中的精确绑定，且目标必须仍是当前目录中的 accepted combination。网络绑定独立保存，模板 apply/rollback 不改变网络 policy/profile/secret refs；网络 revision 也不改写 browser/environment/display template 字段。
- R6E 的高层自定义边界保持不变：用户仍只提交 locale/languages/timezone/screen/DPR/window；R7D 没有新增 UA/WebGL/Canvas/字体等逐项自由拼装入口。

## 自动化结果

| 检查 | 结果 |
| --- | --- |
| 固定 `golang:1.27-alpine`、无网络：`go test -count=1 ./...` | PASS，全部 Adapter 包 |
| 同工具链：`go vet ./...` | PASS |
| `gofmt -l .` / `git diff --check` | PASS |
| 固定 Go 1.27 工具链挂入既有 checks 镜像、无网络、`CGO_ENABLED=1 go test -race -p 1 -count=1 ./...` | PASS，全部 Adapter 包 |
| race 一次性 Docker volume | PASS；脚本 trap 清理，最终 inspect 为 `CLEANED` |

新增/扩展自动化覆盖：严格私有 template catalog、显式 accepted compatibility、旧 artifact fail closed、engine/version/UA/OS/platform 一致性、locale/languages/timezone、screen/DPR、legacy Firefox 禁止新建、裸 artifact 新建绕过拒绝、运行中模板切换零隐式 Stop/零 app replacement/零目录 revision、stopped/0-resources apply、新 revision、完整 PUT 不保留旧 provider 字段、中断 pending 启动门禁与重试、历史 revision rollback、网络与模板 revision 隔离、管理 API 能力门控和错误分类。

## 未部署条件与下一步

本项只完成控制面候选，没有生成或安装生产 `template_catalog`，也没有为当前生产 r9/Work legacy 条目补写 R7D coherence metadata。现有生产 artifact 因缺这些新元数据不会被候选代码猜测成 R7D 模板；因此即使代码存在，只要生产不配置 `template_catalog`，行为保持不变。

R7D 不生成新的浏览器指纹 artifact，因此没有重复 R6E 已完成的“真实 artifact 10 次重建”或 R6F Mac/Trilium 浏览器显示验收；R7D 只绑定已经 accepted 的不可变 artifact，并用服务端字段一致性和 revision 边界阻止错误组合。生产启用前，R7F 必须从实际目标 artifact/显示栈生成真实 accepted template catalog，固定摘要和回退材料并做隔离发布/客户端验收。下一项 R7E 只实现管理页面中的模板/代理下拉与首页，不改变本报告的服务端安全边界。
