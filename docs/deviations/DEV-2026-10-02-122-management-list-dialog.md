# DEV-122 · 列表管理弹窗的渐进增强与焦点

状态：已解决并部署。[R6AC](../work-items/R6AC-2026-10-02-management-lists.md)。

agy组件原稿缺少dialog能力检测和可访问名称，Tab循环包含隐藏/禁用输入且遗漏嵌套summary，关闭事件无条件恢复焦点可能干扰下一操作；样式使用通用dialog-header可能影响已有新增弹窗。选择修复实现：能力检测后才移动原表单，绑定独立标题/控件ID，焦点只包含可见可用控件和summary，保护延迟关闭焦点，CSS限制为record-dialog。保留模型原稿并通过无脚本/键盘/原表单比对验收，不降低条件。

修复后的组件在浏览器、代理、账号三个管理弹窗和1280/768/390三宽度通过Tab/Shift+Tab首尾循环、关闭/Esc恢复焦点、延迟close不抢搜索焦点、原生details回退与控件ID唯一检查。133表单契约一致，24次回环提交通过，见[R6AC验收](../../infra/sealskin/r6ac-management-lists-acceptance-2026-10-02.md)。
