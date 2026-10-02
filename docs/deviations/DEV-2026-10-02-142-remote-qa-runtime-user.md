# DEV-142 · 独立机组合验收误用root运行身份

状态：处理中。关联[R6AW](../work-items/R6AW-2026-10-02-protected-builtins.md)。

预期：SSH安装工具可使用root，但浏览器显示认证与正常关闭契约要求非零业务UID；QA应按同一契约创建合成Home/显示材料。

事实：独立机首个自动显示组合由root启动runner，验收器将宿主UID0写入PUID和合成显示绑定。Worker正确返回SESSION_AUTH_INPUT_INVALID，正常关闭工具返回BROWSER_SHUTDOWN_USER_INVALID，浏览器和X11未启动，最终NATIVE_QA_BROWSER_TIMEOUT。该任务未accepted，失败容器/日志暂时保留。私有证据为独立机`r6aw-protected-builtins-20261002/qa/jobs`及`failed-worker-private.log`；无生产影响。

处理：保留原失败记录，使用独立非root QA账号、私有`/srv`目录和复制的只读程序依赖重新入队；不修改显示认证和正常关闭的UID约束。确认失败容器没有浏览器、X11或业务数据后正常docker stop并移除该QA容器；不触及任何真实Home或原恢复目录。修正环境后重新执行原完整验收门槛。

待验证：非root实际启动、24组合结果、QA资源清理及独立机既有容器保持。
