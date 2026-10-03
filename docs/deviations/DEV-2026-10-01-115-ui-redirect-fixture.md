# DEV-115 · UI 跳转验收的模拟传输不完整

状态：已解决（R6V 验收并部署）。关联 [工作项](../work-items/R6V-2026-10-01-fingerprint-data-ui.md)。

预期：真实浏览器提交模板后，经 303 返回相应功能，并可检查前进/后退和刷新。首版 QA 用 Playwright route.fulfill 模拟响应；实测仅截获初始 GET 与 POST，303 后的 GET 未被再次截获，在无网络容器中以 `ERR_INTERNET_DISCONNECTED` 失败，页面成为空错误页。服务端路由及返回测试已通过，未证明产品跳转有问题。

处理：修复 QA 传输，在独立容器回环地址启用临时 HTTP fixture 服务，真实处理 POST → 303 → GET，再重复完整浏览器场景；不开放外部网络、不触碰生产数据、不降低提交/返回条件。原失败日志与最小诊断保存在 `infra/sealskin/runtime/r6v-fingerprint-data-20261001/`，后续验收记录最终结果。

最终回环HTTP真实15次提交/303/GET、三宽度、键盘/历史导航/禁用脚本通过；最终截图及数字输入高度核对通过，见[R6V验收](../../infra/sealskin/r6v-fingerprint-data-acceptance-2026-10-01.md)。
