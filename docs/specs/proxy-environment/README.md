# 代理与浏览器环境配套规格

本目录对应 [design.md 第 45–50 节](../../design.md#45-proxy-architecture--specification)。所有文件是数据契约示例，不会自动部署 SealSkin、代理或浏览器；本机 SealSkin/Firefox、Relay sidecar、锁定代理的 Firefox/BiDi 和 internal 网络直连阻断结果记录在 [运行验收记录](../../../infra/sealskin/acceptance-2026-09-12.md)。当前 HTTPS 路径通过不代表 DNS、IPv6、WebRTC、代理故障和重启窗口已经完成验收。

| 文件 | 用途 |
| --- | --- |
| `types.go` | 使用标准库的 Go JSON 数据契约；不是服务实现 |
| `schema.sql` | 在空库执行的 SQLite 规格快照；不是旧表或 SealSkin YAML 的迁移 |
| `config.example.json` | Camoufox + 带认证 SOCKS5、Chromium + DIRECT 两种配置 |
| `health.example.json` | 带分项结果、新鲜度和 UNKNOWN 的合成健康报告 |

示例中的域名、secretRef、Session ID 均为占位值。`203.0.113.10` 是文档地址，报告中的 US 是测试夹具，不代表对该地址的真实地理定位。

两个 Profile 初始 `enabled=false` 且未绑定环境产物。导入时只能创建草稿；配置受控探测端点、解析器和密钥，选定已测试的引擎/镜像版本，物化环境并通过能力校验后，才能绑定 `environmentArtifactId` 和启用。配置中的 Camoufox 必需能力是验收要求，不是本仓库已经实现的功能。

`persistentHome` 是适配层命名空间内的逻辑标识，由服务解析为 SealSkin 用户下的命名 Home 或受控宿主机路径；客户端不能提交任意挂载路径。`NetworkPolicy.mode=direct` 表达 DIRECT，不创建伪造的直连代理地址。

JSON 到 SQL 的映射：`RevisionRef` 展开为 `_id`、`_revision` 列；`expectedLocation` 展开为 `country/region/city`；策略和环境同时存储完整 JSON；`network_mode` 从被引用策略派生，不接受调用方单独赋值；其余结构体字段按 camelCase → snake_case 映射。Profile、修订记录的时间由服务生成。SQL 标量和 JSON 中重复出现的字段必须在同一事务中一致写入，读取时校验一致性。

生产连接逐一启用 `foreign_keys`，使用 WAL 和短事务；SQL 校验不能代替 JSON 语义校验、网络强制策略或运行实例核对。修订一经发布不可原地修改；配置修改新建修订，在对应 Profile 停止并解除占用后切换引用。

可用 Python 标准库的 `sqlite3` 在临时数据库执行建库规格。若已安装 Go，可在本目录使用 `GO111MODULE=off go test` 检查类型声明能否编译；这不验证浏览器行为。网络、Profile 恢复和环境稳定性必须执行主文档中的 Linux 集成验收。
