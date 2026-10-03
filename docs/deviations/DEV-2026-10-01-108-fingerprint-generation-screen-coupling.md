# DEV-108 · 设备来源生成仍受显示数据集约束

状态：已解决，R6S服务器验收并部署。关联[R6S](../work-items/R6S-2026-10-01-shared-display-templates.md)。

首个默认Camoufox自动组合在生成阶段失败。真实镜像trace定位BrowserForge无法从Linux数据集生成1280×720对应headers；此前来源生成仍直接使用用户显示尺寸，未完全解除设备来源与显示策略的耦合。失败未产生accepted产物，保留spec和trace。

处理：首次通用来源生成固定使用已验证的1920×1080参考尺寸提取设备来源，再由组合层单独应用自定义尺寸或删除auto/system下的固定显示覆盖。原BrowserForge完整来源保留为provenance，非显示配置精确复用，不以参考尺寸替代实际显示验收。既有缓存不重抽，仍核对来源/目标/镜像摘要；两种显示策略必须实际测量匹配。

最终验证（2026-10-01）：Camoufox参考尺寸仅用于设备来源生成；固定/自动各22份观察、恢复及同Home显示切换通过，设备缓存与非显示配置保持。 证据根为 `infra/sealskin/runtime/r6s-shared-display-20261001/`，见[R6S最终验收](../../infra/sealskin/r6s-shared-display-acceptance-2026-10-01.md)。
