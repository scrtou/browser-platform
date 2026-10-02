# R6AS · 固定版本网络与升级恢复矩阵

状态：进行中。前项 R6AR 已收尾并提交 `74a0e49`。

范围：补齐用户授权剩余 4c。版本固定为 Camoufox 152.0、Chromix 154.0.8037.57、原生 Firefox 155.0.1。每引擎覆盖 SOCKS5 none/username_password、HTTP CONNECT none/basic、HTTPS CONNECT none/basic 与受管理 DIRECT；真实浏览器 HTTP/HTTPS/WS/WSS、远端 DNS、认证/上游/TLS 失败、旁路阻断和资源清理。沿用当前 R7G1 控制器/Relay 和已验收产物，不能以简单代理 Fixture 替代真正 Guard/Relay。

升级/恢复区分：当前支持的服务器补丁 `.2 → R7G1/R6AR` 与对应回退，在上述固定浏览器上验证原 Home 数据、冻结产物和正常退出；已发布同浏览器版本 Worker 修订按精确旧/新镜像记录。补齐原生 Firefox 的独立检查点恢复；既有 R6AP Camoufox/Chromix/旧 Work 证据核验后引用。任意未提供已验收目标的大版本升级不能标为通过，不能用同版本重建替代跨版本迁移。

验收入口：规格 P02/P03/N01–N07/E06；`prepare-network-qa.py` → 当前控制器正常 launch/stop → 专属 Guard/Relay → `network-observer.py` 与真实 native CDP/BiDi → `check-network-browser.py` 的 packet/失败断言；恢复走正常停止与加密检查点。现有旧协议矩阵只硬编码 Camoufox/固定环境，需要增加显式原生 QA 适配，保留历史断言。

使用已授权独立机器和合成 Home。真实账号、供应方凭据、生产 Home 保持离线；未完成 journal 和失败证据不删除。商业供应方自然漂移仍 NOT_TESTED。若发现偏差立即登记。

完成条件：支持矩阵逐格有证据或明确外部条件；六协议逐引擎真实网络/失败/包观测；DIRECT 对应传输与失败证据；补丁升级/恢复/回退与固定镜像、存储/产物比较；隔离清理、生产保护；相关 README/规格、验收索引、进度/roadmap/执行表与 Git 收尾。之后统一封存当前发布版本。

## 实施与当前证据

独立机已导入当前精确镜像并准备受限 Docker API、合成 Home、真实 Guard/Relay 与私有观测端点。原生 QA 只追加调试入口，生产 launcher/image 不变；NSS 测试信任写入各引擎独立 QA Home。

- Camoufox 六协议组合共70项网络/失败检查、HTTP/HTTPS/WS/WSS及恢复读回已通过。前五组位于 `camoufox/protocols-1790947206/`；HTTPS basic 最终完整通过位于 `camoufox/protocols-1790948379/`。此前恢复调试端口尚未就绪的失败保留，修正只增加只读就绪等待，不重发已可能执行的操作。
- 原生 Firefox 异机加密检查点恢复、再打开、第二检查点回退、源指纹及三类存储、认证显示/输入、HTTPS/旁路拒绝通过；真实身份未启用。
- R6Z1 的同版本修订证据已复核：3项发布恢复/失败保留、同种子新镜像的22份观察与离线恢复通过；这些证据不代表跨浏览器大版本或任意旧 Home 迁移。
- Camoufox服务器补丁在线升级、新Relay代次和程序回退均通过；原Worker（在线升级）、固定环境及三类存储核对通过。其DIRECT及另外两引擎完整矩阵继续进行。Chromix 既定策略保留 WebRTC API 并禁止未代理 UDP；QA按此契约实际尝试ICE并核对包观测，Firefox系列仍断言API禁用。没有降低旁路拒绝要求。

工具：`run-fixed-version-matrix.py` 串行准备、六协议、程序升级、DIRECT和清理；`native-network-client.py`仅在QA挂载目录使用CDP/BiDi；`check-fixed-program-upgrade.py`通过真实Adapter入口、正常停止及独立状态验证旧/新程序。全部详细证据位于被忽略的 `infra/sealskin/runtime/r6as-fixed-matrix-20261002/`。本项仍未收尾，完整结果和清理须继续核验。
