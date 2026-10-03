# DEV-101 · Chromix 自定义多语言被引擎参数覆盖

状态：已解决并部署。关联 [R6R](../work-items/R6R-2026-10-01-multi-engine-generation.md)。

预期：通用来源 languages 的完整顺序在生成后 navigator.languages 中保持。

事实：独立新镜像的 zh-CN/en-US/en 来源，使用公开 fingerprint 模式与 fingerprint-locale 时，网页只返回 [zh-CN]；accept-lang 参数没有修正。证据在私有 `runtime/r6r-multi-engine-20261001/diagnostic-chromix-2/`。未发布失败组合。

处理：修复实现。新自定义产物使用已验证的显式持久种子/标量参数和实际 X11 屏幕，语言使用受管理原生 profile 偏好；旧产物启动参数保持。需重新验证完整语言列表、时区、屏幕及跨Home/重启稳定性，不降低多语言验收。

结果：R6R最终固定镜像/源码的相关完整验收与拒绝/恢复检查通过，限定部署完成；详见[R6R验收](../../infra/sealskin/r6r-multi-engine-acceptance-2026-10-01.md)。原失败证据保留，能力边界未降低。
