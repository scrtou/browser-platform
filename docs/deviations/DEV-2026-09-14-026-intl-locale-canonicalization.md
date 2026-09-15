# DEV-026 · Intl 语言标签规范化依赖浏览器结果

状态：已修复并通过隔离验收（候选 4；未部署生产）。工作项：[R5C3](../work-items/R5C3-2026-09-14-runtime-coherence.md)。

预期：实际页面 locale 与冻结配置相符；使用标准语言标签语义区分等价写法和真正的语言/地区差异，不能依赖页面自己判断相符。

实测：候选 3 的 US/en-US 冻结环境在独立重建/恢复验收中通过。实际页面 `navigator.language=en-US`、Intl locale 为 `en`，两个 `Intl.Locale.maximize()` 返回值仍分别为 `en-US` 和 `en`。控制端直接比较页面的两个 normalized 字段，错误返回 `INTL_LOCALE_MISMATCH`。证据位于私有 `candidate-3/c3-topology-access-1/` 等目录；该代次未获放行，已正常停止。

处理：修复控制端比较，使用固定 Babel 2.17.0 所带 Unicode CLDR likely-subtags；保留实际原始标签与规范化来源。与冻结 locale 的语言/文字/地区/变体比较，不使用页面的 normalized 字段作为通过依据。不支持或缺失的标签保持 UNKNOWN，真实差异仍 FAIL；不修改冻结环境或放宽国家/时区条件。新增 wheel 的 URL、版本和 SHA 加入现有不可变依赖锁，离线构建同样校验。

待验证：`en`/`en-US`、`zh-TW`/`zh-Hant-TW` 等价；`en-GB`、不同文字/语言、错误和缺失值拒绝；实际 C01–C03 新固定候选复测。与 DEV-025 一并进入下一候选，原候选和失败不改写。

验证结果：候选 4 使用固定 Babel 2.17.0 / CLDR 46，458 项控制测试包含显式 script/territory/variant、别名、等价与无效标签；采用 parse_locale，未使用可能丢弃显式 script 的 Locale.parse 默认消歧。`c01-entry-2/`、`c02-entry-3/`、`c03-entry-2/` 的真实 en-US / Intl en 比较符合预期；严格时区差异仍拒绝。详细证据均位于被忽略的 `infra/sealskin/runtime/r5c3-coherence-2026-09-14/`，不代表生产已更新。
