# R6AD · 指纹数据新建与删除弹窗验收

状态：PASS，已限定部署（2026-10-02）。[工作项](../../docs/work-items/R6AD-2026-10-02-fingerprint-dialogs.md) · [设计](../../docs/reference-ui-design.md)

## 交付

指纹/显示创建、组合生成验收，以及指纹/显示/组合/结束任务四类删除全部复用原生记录dialog。删除标题注明对应记录，危险标题红色、较窄确认框；所有弹窗有关闭与取消按钮、Esc、Tab循环和焦点恢复。表单DOM仅移动，不复制，不改现有字段、默认选择、校验或提交地址。原details作为禁用脚本或无dialog能力时的回退。

继续调用本机agy、gemini-3.8-flash-high；本次回执虽称SUCCESS，但只报告等待搜索，未修改组件。主流程据此直接扩展上一轮经审查的agy组件，不冒称本次增量由Gemini完成。原稿、回执和最终diff保留。

## 验证边界

以下均通过，截图人工复核完成。

- 独立冻结候选与工作树完整Go test/vet；所有业务处理器及其他产品源码不变，仅管理模板CSS/JS变化。
- 44组夹具133个原表单契约一致；仅规范化独立登录产生的非空随机CSRF值，真实鉴权由原Go测试覆盖。
- 105布局回归涵盖新旧页面、三宽度、长名称/空态/不可用来源；七类操作分别检查独立弹窗、对象标题、关闭/取消不提交、Esc、Tab与返回焦点、必填校验和删除必选确认。
- 原四管理子项、记录详情、搜索/引擎联动、首页和侧栏导航、无脚本回退继续检查；真实回环HTTP POST/303合计45次，包含七类新弹窗各三个宽度的21次提交，以及此前24次回归。没有对生产做新建/删除。

## 发布与保护

基线Adapter `a237c21c618240bc2b90eafcf7d11ceba2358cc12dccc6b5afdb3d6248412e85`。已仅替换Adapter并重启其服务，保留生产浏览器/Home/Session/账号/目录/作业/控制器/R6Z1 runner，不部署R6I/R7G。新Adapter `093902b8c6ad6a7fa2388304d6f3a032df71ba7d0933752829627b994f048bdd`，运行进程摘要、ready、登录入口及前后保护快照通过，before/after/deployment.json已保存。

私有证据 `infra/sealskin/runtime/r6ad-fingerprint-dialogs-20261002/` 保存agy回执、候选清单、表单比对、Go日志、UI结果与截图、发布/回退材料。QA脚本为 `infra/sealskin/checks/check-fingerprint-dialogs-ui.py`，来源表单对照复用check-list-form-contracts.py。回退只恢复本项profile-adapter-before并重启Adapter，不回滚用户数据。Mac/Trilium实机反馈单列。

QA容器已退出，本项独立Go缓存回收264.5MiB，源码/回退/验收证据保留。
