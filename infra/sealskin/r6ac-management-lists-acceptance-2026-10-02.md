# R6AC · 管理四子项列表验收

状态：PASS，已限定部署（2026-10-02）。[工作项](../../docs/work-items/R6AC-2026-10-02-management-lists.md) · [设计](../../docs/reference-ui-design.md)

## 范围

浏览器、代理、指纹数据、访问账号统一紧凑列表。指纹数据涵盖指纹模板、系统/自定义显示模板、验收任务和已验收组合；创建来源及生成验收表单默认折叠。浏览器每行显示名称、状态、网络和打开/详情管理；代理/账号较长操作从详情管理弹窗打开。手机保持表格，在表格容器内横向滚动，不把数据重新排成卡片。

实际调用本机agy / gemini-3.8-flash-high：第一次整文件请求触发输出长度限制，无源码交付；拆分后实际产出list.css/list.js。主流程完成Go模板转换，移动原表单而不复制，修正[DEV-122](../../docs/deviations/DEV-2026-10-02-122-management-list-dialog.md)，完成独立验证。不能把此次模板转换全部归为Gemini产出。

## 通过证据

- 冻结候选与工作树完整Go test/vet通过，原权限/字段/能力门控/引用删除保护/停止要求回归保持。
- 44组新旧渲染夹具、133个表单契约一致：方法、提交地址、控件字段/值/默认选择、校验约束及删除确认。仅规范化两次登录生成的非空随机CSRF值；字段是否存在/类型和空值保持比较，真实CSRF鉴权由原Go回归覆盖。
- 真实Chromium1280/768/390共105种布局通过，含四子项、指纹三子功能、长名称/空态/无可用模板；列表默认不展示原大卡片，控件ID无重复。
- 三类记录详情弹窗在三个宽度下有可访问名称、独立归属、Tab/Shift+Tab循环、关闭/Esc恢复焦点；关闭后搜索不被延迟事件干扰。无脚本使用原生details，原表单仍可查看/提交。
- 原三类新增弹窗、搜索、引擎/指纹联动、首页详情/侧栏/历史导航回归通过；24次真实回环HTTP POST/303：原登录和删除确认18次，移动后代理删除/账号分配6次。没有对生产浏览器做新建/删除/停止。
- 仅2个源码路径相对R6AB变化：管理模板及其既有UI契约测试；管理处理器与所有其他产品文件逐字一致。截图人工复核通过。

## 发布与保护

基线R6AB Adapter `f8292880c9c042beb11065c7ba9a1453e2130689c3b952cda75ed3ca91e5e894`。仅替换Adapter并重启其服务，保护生产浏览器、Home、Session、账号/代理/模板目录、任务、控制器与R6Z1 runner；不夹带R6I/R7G。新Adapter SHA256 `a237c21c618240bc2b90eafcf7d11ceba2358cc12dccc6b5afdb3d6248412e85`，实际进程摘要、ready、线上登录入口及前后保护快照核对通过，before/after/deployment.json已保存。

私有证据 `infra/sealskin/runtime/r6ac-management-lists-20261002/` 保存agy两次回执/组件原稿、主流程转换和修正、冻结源/清单、表单比对、test/vet、105布局截图与24次提交、发布脚本/快照及回退二进制。QA脚本为 `infra/sealskin/checks/check-management-lists-ui.py` 和 `check-list-form-contracts.py`。回退只恢复本项profile-adapter-before并重启Adapter，不能回滚用户后续目录/数据。Mac/Trilium用户实机反馈另列。

本项QA容器已回收，独立Go缓存277.3MiB已清理；源码、截图、二进制及回退证据保留，最终可用空间约1.43GiB。
