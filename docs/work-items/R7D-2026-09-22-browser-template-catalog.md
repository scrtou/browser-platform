# R7D · 指纹、浏览器与显示模板兼容目录

状态：已收尾。开始日期：2026-09-22；收尾日期：2026-09-23。候选未部署。

## 目标与范围

- 用户要求 / 对应计划：承接 R7 方案第 4 步；R7A–R7C 已按未部署候选收尾，用户要求继续当前任务。
- 本项交付：把现有 accepted 环境产物提升为可验证的指纹模板来源，增加浏览器模板、显示模板及服务端兼容组合目录；关键配置变化只允许在浏览器停止且 records/workers/resources 为零后生成新 revision，并保留旧 revision 作为回退来源。
- 指纹约束：同一 revision 跨重启稳定；浏览器引擎/版本/User-Agent/平台/OS、locale/languages/timezone、screen/window/DPR 与显示规则必须形成已验收的一致组合。代理修订只改变网络出口，不得自动改写指纹。
- 自定义边界：继续复用 R6E 的受限高层字段（locale、languages、IANA timezone、screen、DPR、window），不开放 UA、WebGL、Canvas、字体等低层逐项拼装。
- 本次不做：不实施 R7E 首页/网络代理 Tab 视觉改版，不执行 R7F 生产发布；不启动/停止生产 Personal 或 Work，不修改真实 Home、账号、Session、凭据。

## 阅读与代码核对

| 材料 / 代码入口 | 当前事实 |
| --- | --- |
| docs/progress.md / docs/roadmap.md / R7C 工作项 | R7C 已收尾但未部署，生产 Work 仍 disabled/stopped；下一项明确为 R7D。 |
| profile/management.go / service.go | 现有 environment_catalog 只把 accepted artifact 作为创建浏览器的环境来源；CreateBrowserRequest 仍直接携带 language/timezone/wayland，尚无浏览器模板、显示模板或兼容组合引用。 |
| profile/directory.go | 普通 BrowserPatch 只能改名称、起始页和启用状态；尚无关键模板切换的独立、停止后应用路径。 |
| profile/environment_jobs.go | 已有高层自定义输入校验：BCP47、IANA timezone、screen/window、DPR=1，并由服务端固定 Linux、WebRTC/定位关闭等能力，可作为 R7D 自定义入口安全边界。 |
| 既有 Personal / Work | Personal 当前为 Camoufox/X11/fixed 1920×1080 路径；Work 为 Firefox legacy/Wayland 且已停用。旧记录没有 R7D 模板引用，迁移必须显式处理，不能靠字段推测成 accepted 新组合。 |
| 工作区 | 开始本项时已有 R6F/R7C/运维等大量未提交改动；R7D 只追加最小相关变更，不清理、不覆盖其他改动。 |

## 完成条件与验证

- [x] accepted 指纹/浏览器/显示模板可由服务端读取，非 accepted 修订不进入可选组合。
- [x] 服务端只返回显式验收过的兼容组合；Camoufox/Firefox legacy、X11/Wayland、screen/DPR 不允许任意混配。
- [x] 指纹模板的引擎/version/UA/平台/地区/screen/DPR 一致性在加载或绑定前 fail closed；缺少 R7D 元数据的旧 artifact 不被误标为新模板。
- [x] 网络代理变化不修改 artifact/browser/display 引用，并有回归测试。
- [x] 运行中关键模板切换返回 busy，Stop / app replacement / directory mutation 均为零。
- [x] stopped 且资源为零时可应用已验收组合，写入新 Profile revision；旧 revision/绑定信息可执行显式回退。
- [x] 新浏览器只允许目录明确 `allow_new_browsers` 的 Camoufox accepted 组合；`firefox_legacy` 在目录校验层禁止普通新建。
- [x] 聚焦测试和全量 Go test、vet、gofmt/diff-check、race 通过。
- [x] 本项不生成新 artifact，因此不重复 R6E/R6F 的真实多次重建/显示验收；没有创建生产或 QA 浏览器资源，生产无副作用。

## 文档与收尾清单

- [x] 更新 Adapter README、R7 管理规格，记录目录格式、兼容规则、停止后应用和回退边界。
- [x] 本项没有降低设计验收标准的偏差；PATCH deep-merge 风险通过完整 PUT 实现规避，不需登记 deviation。
- [x] 新增 [R7D 验收报告](../../infra/sealskin/r7d-browser-template-catalog-acceptance-2026-09-23.md)并登记验收索引。
- [x] 更新 docs/progress.md、docs/roadmap.md 与本索引，明确候选未部署及下一项 R7E。
- [x] 复核临时 race volume 已清理，保留开始本项前已有的脏工作区，不清理/覆盖其他候选改动。

## 收尾结论

R7D 已形成未部署候选：显式 accepted compatibility 是唯一 R7D 选择来源；模板切换在生命周期锁内证明 stopped/0-resources 后先写 `updating` 门禁、完整 PUT 应用定义、再提交 Profile revision，失败可安全继续；历史模板 revision 可显式回退，网络 revision 与模板绑定彼此独立。当前生产没有 `template_catalog`，现有 r9/Work legacy 条目也没有 R7D coherence metadata，因此生产行为未变化。下一项为 R7E 管理页模板/网络代理 Tab 与首页。
