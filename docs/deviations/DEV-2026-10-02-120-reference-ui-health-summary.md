# DEV-120 · UI 统计必须保留过期健康语义

状态：已解决并部署（2026-10-02）；关联 [R6AA](../work-items/R6AA-2026-10-02-reference-ui.md)。

预期：参考截图的统计卡片只能反映实际可用数据，过期/阻塞健康不能计入健康数量；现有未知状态和权限条件保持。

事实：agy首轮候选在manage.go中仅按Observed且Health=healthy累计Healthy，未排除Stale/Blocking；Issues还未覆盖已观测的非healthy状态。原有浏览器详情仍保留过期提示，但新统计会产生矛盾。主流程另发现新增测试引用不存在的newTestServer导致编译失败，尚未通过验收，未整合或部署。

处理：已让指定Gemini模型修正统计与准确文案；主流程将以真实模板/现有测试夹具验证统计、导航、字段和权限，不降低测试条件。仅独立源码副本受影响，生产保持。

证据：私有 `infra/sealskin/runtime/r6aa-reference-ui-20261002/` 的agy结果、源码副本及parent-tests-1.log；最终健康统计、权限、模板与表单回归已通过。

补充审查：首轮还含只读搜索框、未接通的代理/账号弹窗和未定义测试夹具。真实浏览器随后发现原生dialog的Tab循环与延迟close事件抢焦点，均修复；关闭仅在焦点仍在dialog/body时恢复，不覆盖用户新焦点。69种布局、18次提交、搜索清空、三弹窗键盘、无脚本/引擎联动及两套Go test/vet全部通过，限定Adapter发布与保护比对通过。见[R6AA验收](../../infra/sealskin/r6aa-reference-ui-acceptance-2026-10-02.md)。
