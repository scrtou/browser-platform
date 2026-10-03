# DEV-106 · 空模板页隐藏引擎且Firefox无可新建组合

状态：已解决，R6S服务器验收并部署。关联[R6S](../work-items/R6S-2026-10-01-shared-display-templates.md)。

用户反馈与线上核对一致：R6R虽有三个accepted browser target，但真实来源列表为空，生成引擎表单只在来源行内出现。Firefox没有accepted environment兼容三元组，新建浏览器依实际组合过滤，因而只显示Camoufox/Chromix。此前“刷新即可选择”没有覆盖真实空状态，R6R有数据UI证据不能扩大到此场景。

处理：组合入口独立于来源行，空状态显示引擎和创建/选择指纹来源的操作提示；内置auto/system显示预置始终可见。为三个引擎准备真实验收的默认组合，追加完整环境和兼容关系后新建可用。验收必须覆盖真实空状态、默认目录和新建路径，不能只添加下拉选项。

最终验证（2026-10-01）：空/有数据页面及新建页面三宽度验收通过，六个真实accepted默认组合已限定发布。 证据根为 `infra/sealskin/runtime/r6s-shared-display-20261001/`，见[R6S最终验收](../../infra/sealskin/r6s-shared-display-acceptance-2026-10-01.md)。
