# Work Firefox 受管理网络层

2026-09-30 后续生产维护：Work 正常停止后全部资源为零，匹配本镜像的 5,938 条目新 age 备份/verify/独立 restore 通过，5,740 个 Home 文件内容/权限一致，副本未激活。用户固定入口重开后，17:15 UTC 新 operation/Session/容器与原 Home/完整应用/策略核对通过，浏览器/显示/DIRECT 和 Worker HTTPS/绕过拒绝通过；用户确认页面/输入正常，原书签/登录项不适用。本维护范围已收尾；Personal/“测试”身份保持，详见 [生产重建验收](../sealskin/r7f-work-production-rebuild-acceptance-2026-09-30.md)。下段保留迁移阶段范围。

2026-09-30：R7F 已增加服务端批准目录的存量迁移/回退路径，完整应用从加密 API 读取；迁移只改变此目录已验收的镜像和独立 DIRECT policy，保留 Home、Firefox/Wayland 与停用状态。本次停止时点 5,195 条目加密 create/verify/独立 restore 已完成，恢复副本未激活。用户已完成实际迁移、启用并打开；revision 8 使用精确目标镜像，Worker 受管域名/TLS/HTTPS 与有效 DNS 拒绝检查通过。Mac 真实公网页面已确认；当前组合独立 QA 的正常重建/三类存储、实际回退/再次迁移与网关故障关闭已通过，详见 [恢复验收](../sealskin/r7f-work-recovery-acceptance-2026-09-30.md)。生产真实 Home 重建和完整客户端矩阵仍待完成。管理页迁移操作继续要求近期密码确认；详情与当前部署范围见 [迁移验收](../sealskin/r7f-legacy-migration-acceptance-2026-09-30.md)。

[文档导航](../../docs/README.md) · [Work 受管理出网工作项](../../docs/work-items/R7B-2026-09-21-managed-work-egress.md) · [Firefox Proxy](../firefox-proxy/README.md)

本目录在精确、已验收的 Work Firefox/Wayland 退出与显示认证镜像之上增加最小网络配置层，不更换 Firefox、桌面、Selkies、正常退出或显示认证实现。Firefox 被锁定为只连接当前 generation 的 `profile-relay:1080` SOCKS5，域名解析交给 Relay，禁用 DoH 和 WebRTC 直连候选。Worker 仍必须共享 Guard 网络命名空间；浏览器配置本身不能替代 Guard 的 fail-closed 规则。

构建器只接受本机完整 `sha256:` image ID，要求父镜像已有正常退出和 Session 显示认证标签，离线构建后核对父层前缀并生成不可覆盖的输入摘要标签。网络配置复用 [Firefox Proxy](../firefox-proxy/README.md) 的权威文件，临时构建上下文只包含 Dockerfile 与这两个公开配置，不向 Docker daemon 发送仓库运行目录或秘密材料。

```bash
python3 infra/work-firefox-managed/build-image.py \
  --base-image sha256:ec848635e68db2d1c805fcf9972ef4586bcd86a9ed14b2075b0c5a40fbbc503f \
  --tag-prefix browser-platform/firefox:work-wayland-managed-r1 \
  --output infra/sealskin/runtime/r7b-work-egress-2026-09-21/work-managed-image.json
```

产物只是候选镜像；必须再通过 R7B 的独立 Firefox/Wayland DIRECT 验收，并在 R7F 固定发布包、回退和生产维护门槛内绑定，不能直接替换运行中的应用。

2026-09-29 阶段历史：R7F 已复核原 Work 镜像、候选镜像的完整父层/能力/输入摘要，以及生产 DIRECT 主机/网关前置；Work 当前停止时点 5,195 条目加密备份、verify 与独立 restore 通过。原应用与仅换镜像的审阅草稿已固定，但旧 Work 无网络模式，尚缺受管理目录迁移路径和生产验收，草稿不可部署。详见 [续跑验收](../sealskin/r7f-production-review-acceptance-2026-09-29.md)。

## 当前组合的独立迁移/恢复检查

[check-work-migration.py](../sealskin/checks/check-work-migration.py) 使用 `prepare-network-qa.py` 建立的独立 `qa` 目录，要求精确控制器镜像、DIRECT 主机证据挂载、显示 tmpfs 和 loopback Session 端口 28443。`qa/bin` 中放入核对摘要的 Adapter、provision/install-app/profile-accounts 工具；不使用生产配置启动 QA Adapter。

私有 `--baseline` 包含 `controller`、`adapter_sha256`、`direct` 发布值，`--source-plan` 为已复核的完整批准目录。检查器把源定义映射为固定 QA 身份，追加的脚本/目录、应用及数据均留在 QA 根；它不修改输入批准目录。`--age-dir` 指向固定 age/age-keygen 工具目录。以操作者选择的新私有路径替换下方占位参数：

```bash
python3 infra/sealskin/checks/check-work-migration.py prepare \
  --root <private-run>/qa --baseline <private-run>/production-before.json \
  --source-plan <reviewed-private-migrations.json> --age-dir <age-tools>
python3 infra/sealskin/checks/check-work-migration.py run \
  --root <private-run>/qa --age-dir <age-tools>
python3 infra/sealskin/checks/check-work-migration.py cleanup --root <private-run>/qa
```

`prepare` 不可覆盖重跑；`run` 拒绝覆盖已有结果，失败时保留操作门禁、Home 和证据，先诊断再沿既有生命周期恢复。成功后 `cleanup` 核对零代次、精确标签/挂载/进程归属，删除 QA 控制器/上游、网络、匿名卷及显示 tmpfs，保留私有磁盘证据。生产基线和结束时目录、Session、容器身份与健康需另外只读核对；完整示例及结果边界见上述恢复验收。

绕过检查共用 [worker-bypass.py](../sealskin/checks/worker-bypass.py)：完整 DNS 查询与明确本地拒绝为通过条件，超时仍为未定。QA Home 备份仅覆盖普通文件，排除节点记录在私有清单，不替代生产控制根完整备份。
