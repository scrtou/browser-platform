# DEV-163 · 开机恢复在Guard稍晚就绪后未继续对账

状态：已解决（R6AX范围）。关联[R6AX](../work-items/R6AX-2026-10-03-v1-release.md)。

新控制器v7整机重启后，原Firefox Guard于10:21:39.239启动，在10:21:52.583输出本次启动的正确就绪摘要，耗时约13.34秒。原10秒Guard检查已返回`NETWORK_GUARD_NOT_READY`；Worker仍停止，原Session、操作、三个容器和Home保留。Adapter只做一次开机Reconcile，之后保持unknown。最终驱动没有访问浏览器或执行新安装，而是以`ORIGINAL_GENERATION_NOT_RESUMED`失败；私有日志与inventory保留于`fresh-qa-v7/failed-final-boot-*`。

Guard检查拒绝旧启动日志和未完成初始化的namespace是正确行为，不能放宽为容器running即可信。差异在于开机恢复没有利用剩余的逐浏览器195秒预算，继续处理已经发生进展的原代次；已有显式Reconcile/Resume本就支持按原幂等键重试，不创建新Worker。

修复：仅对Service已确认进入休眠恢复但返回`ErrResumeFailed`的情况，在同一个逐浏览器截止点内最多尝试三次Reconcile，间隔两秒。每次重新核对归属/当前状态，沿用原恢复幂等键；普通未知归属、已删除记录和其他错误不自动重试，取消立即终止。Guard的10秒门槛、本次StartedAt日志过滤与全部网络/显示检查保持。永久失败仍记录unknown并继续其他浏览器，用户明确停止的意图优先。

需验证：瞬时恢复失败后继续、同一预算/取消、永久错误次数上限、归属错误不重试；完整Go回归和精确重建。先用新Adapter在当前失败代次原地恢复并核对原容器/操作/Session，再进行新程序下完整运行与真正整机重启。1.0及最终安装、生产切换保持未完成。

完整Go test/vet和新恢复回归通过；候选Adapter `b4c6ec2f776c7ae6017e848ee2c6b4c48a9d62ba425171a2f88e644144f73f6c`已构建，其余五个程序摘要不变。控制器仍为DEV-162的`2a966873…`，Guard镜像与10秒检查未修改；原地恢复及最终整机重启继续验证。

最终验证：原v7失败代次经新Adapter开机调用链原地恢复，三个容器、Session、operation保持，正常关闭后精确warm标记和SQLite完整性通过；v9同一最终Adapter及控制器的三引擎运行、四服务重启和真正整机重启全部通过，Worker在入口QA前自动恢复。最终原包新安装和生产部署亦通过。见[R6AX验收](../../infra/sealskin/r6ax-v1-install-acceptance-2026-10-03.md)。
