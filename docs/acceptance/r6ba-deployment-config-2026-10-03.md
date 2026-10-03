# R6BA · 部署配置与端口验收

结果：PASS（源码、文档和本机隔离验证，2026-10-03）。**新安装器的真实整机安装与runuser跨用户执行未复测**：独立机SSH连接超时，本机sudo需密码。原R6AX整机证据不扩大为本次验证。

关联[工作项](../work-items/R6BA-2026-10-03-deployment-config.md)、[DEV-169](../deviations/DEV-2026-10-03-169-public-http-port-preflight.md)和[部署说明](../deployment-v1.md)。基线 `cd02a40`；运行Adapter、CLI和镜像均未修改。

| 场景 | 证据与结果 |
| --- | --- |
| 安装器回归 | `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s infra/deployment -p 'test_*.py' -v`，28项通过 |
| 配置与优先级 | 纯CLI兼容、JSON读取、显式CLI覆盖、默认值、QA覆盖、admin省略/null通过；私有普通文件、未知/重复字段、类型、路径、密码/账号拒绝通过；错误不回显密码 |
| 完整文件生成路径 | 保留真实安装文件生成，替换系统/Docker执行；三个自定义端口正确传播到Compose、Caddy、Adapter和引导配置；初始化成功/省略/失败分别生成对应回执或失败文件 |
| 端口边界 | 高位范围/互斥、生产公开80/443、QA回环、高位生产公网拒绝、显式443规范化通过；80冲突在安装目录创建之前拒绝 |
| 密码边界 | 管理员密码仅作为stdin；argv/stdout/stderr/请求回执/生成文件不含密码；check-only不调用初始化；错误与超时使用固定错误码 |
| 真实账号工具 | 本机独立临时目录、实际已部署profile-accounts二进制，使用当前非root用户直接执行；仅替代runuser身份切换。配置创建首位管理员、PBKDF2哈希与错误密码核验、重复初始化不改变原文件、0600/所有权和无明文检查通过 |
| 账号/登录回归 | 3项现有Go测试通过：显式初始化表拒绝异常；初始化前后登录页、旧登录撤销、新管理员登录；并发首次初始化与重复初始化不覆盖 |
| 就绪分支 | readyz+TLS页面逻辑的HTTP替身测试验证待初始化页/登录页两种结果，错误状态不能生成成功回执；不将此称为真实公网TLS安装 |
| 文档与清理 | 端口关系图、初装/已有实例文件对应、三类账号、密码配置及原文件保管、CLI优先级与旧包边界同步；链接/空白检查通过。临时账号树与任务Go缓存清理，生产无变更 |

Go选择：`TestExplicitBootstrapStateRejectsAmbiguousOrCorruptRegistry`、`TestBootstrapGatewayRevokesOldLoginAndEnablesInitializedAdmin`、`TestInitCreatesOnlyFirstAdminAndNeverReplaces`。

私有证据在 `infra/sealskin/runtime/r6ba-deployment-config-20261003/`：`installer-tests.log`、`account-gateway-tests.log`、`local-account-smoke.json`、`document-checks.json`。真实CLI SHA-256为 `e6545f679d71e2bcf02fbd68a1bd23dd4dab3f23085031d88aef13138d0d68fb`。

`remote-account-smoke.log`保留SSH超时。首次本机QA脚本把无浏览器授权强制预期为 `[]`，但现有CLI合法编码为 `null`；按实际账号契约核对两者均为零授权，修正QA断言后重跑通过，未改CLI或降低权限要求，原输出保留 `local-account-smoke-attempt1.log`。

交付为主分支安装器及文档，不重写v1.0标签/原包，不部署到生产。独立机连通恢复后的整机新安装/跨用户/TLS复测单列后续，不阻断本次源码交付但不得标为已验证；指纹增强等功能未开始。
