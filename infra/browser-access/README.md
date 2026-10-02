# Worker 显示认证层

[入口登录与 Session 访问](../sealskin/entry-auth/README.md) · [正常退出层](../browser-runtime/README.md) · [Camoufox](../camoufox/README.md) · [DEV-033](../../docs/deviations/DEV-2026-09-14-033-worker-display-secrets.md)

本层用于 R5D 新建 Worker，基于固定 r6 镜像增加 nginx/Selkies 显示认证材料的隔离。它保留原浏览器、Home、环境重放和正常退出行为。r7 产物重放、真实 `/init`/显示认证、五类错误材料拒绝、控制器/Worker 恢复及最终进程/Home/日志扫描已通过 [R5D 隔离验收](../sealskin/entry-authentication-acceptance-2026-09-15.md)。生产旧 Worker 未替换。

## 数据边界

控制器生成的显示账号和密码为独立随机 UUID。原密码只用于控制器内存中的 Basic Auth 和加密 Session 快照，不进入 Docker 环境、argv 或 Home。上游代理凭据仍只交给该代次 Relay；此层不读取上游凭据。

控制器显式挂载私有宿主 tmpfs 到 `/run/browser-platform-session-secrets`。`session_runtime` 在其中建立 `session-<UUID>/`，仅包含：

| 文件 | 用途 |
| --- | --- |
| `binding.json` | 绑定 Session UUID 和运行 UID |
| `basic.htpasswd` | 随机显示密码的带盐 SSHA 校验值；不含密码 |
| `master-token` | 可选协作 token；未启用时为空 |

宿主目录为运行 UID 所有、0700，三个文件为 0600、单链接普通文件。Worker 只读挂载自己的目录到 `/run/browser-platform-session-input`。它不能读取父目录或其他 Session 的材料。

Worker 另有自己的 `/run/browser-platform-display` tmpfs。启动验证输入的挂载类型、只读状态、权限、属主、文件类型、绑定和内容；任一异常拒绝启动。nginx 使用其中的密码校验文件，并把自签名 TLS 私钥放在此 tmpfs。Selkies 在进程内读取专属 `master-token` 文件，不重新导出环境变量或命令参数。

SSHA 用于校验高熵随机显示密码，不用于用户选择的登录密码。入口账号仍使用 PBKDF2-SHA256，见入口访问说明。专属协作文件仍是秘密，不得归档到普通 Home、产物或公开证据中。

## 固定构建与集成

构建器只接受本机已有的完整 `sha256:` 镜像 ID，并核对正常退出能力和 Linux amd64。安装器再次校验四份 LSIO/Selkies 输入源码的 SHA-256；上游变化必须重新审查，不能跳过摘要校验。新增层不得更换基础层。

```bash
python3 infra/browser-access/build-image.py \
  --base-image sha256:<已核对的完整基础镜像摘要> \
  --tag-prefix browser-platform/camoufox:0.5.6-beta.30-r7-entry \
  --output /private/new-worker-build.json
```

镜像标记 `io.browser-platform.session-auth=1` 和构建输入摘要。`rebind-worker.py` 将新镜像绑定为新的不可变环境产物，之后必须运行 `infra/camoufox/acceptance.py`；旧 r6 验收不能替代新产物验收。R5D 的 r7 固定信息见 `infra/sealskin/runtime/r5d-entry-auth-2026-09-14/worker-build-1.json`（本机忽略目录）。

控制器在应用的最终 Docker overrides 之后检查实际镜像能力和挂载，拒绝秘密环境替换、`FILE__`、入口命令替换及材料路径遮蔽。新 Session 记录 `display_secret_version=1`；旧 Worker 的兼容恢复不代表通过新的凭据边界验收。

## 恢复、停止与日志

控制器启动和原代次 resume 从密封 Session 重建专属材料，重新核对 Docker 环境、标签和只读挂载。正常停止删除 Worker 后，清理器重新清查所有 Docker 引用再移除材料；状态未知或仍有引用时保留材料和停止意图。宿主重启后须先创建、正确授权并挂载 tmpfs，再启动控制器。

nginx 访问日志仅保留固定事件和 HTTP 状态；原始 error 文本不写日志。Selkies Python 日志不渲染动态消息、参数或 traceback，保留固定事件和级别。该边界避免认证失败把请求或 token 写入普通输出，代价是日志不再包含原始异常详情；私有排障仍须避免把能力复制到公开记录。

验收分别记录正常 `/init`、正确/错误显示认证、HTTP/WebSocket、缺失/错误材料拒绝、控制器恢复、Worker resume 和最终 inspect/进程/Home/日志扫描。R5D 的最终证据在本机忽略目录 `infra/sealskin/runtime/r5d-entry-auth-2026-09-14/` 的 `client-qa-13/`、`worker-auth-negative-2/`、`runtime-security-3/`；QA 已清理。实际协作房间未测，可选协作 token 的文件/进程契约仅有控制测试，不能扩展为多人显示验收。

R4B 另将同一认证层装到保留原 Firefox/Wayland 的 Work 候选。三个真实 Linux 客户端共取得 44 个显示帧并通过错误登录、无 Cookie Session 拒绝和输入附着；缺少输入、错误 Session、权限过宽、符号链接、可写挂载五类实际 `/init` 均拒绝且未监听显示端口。控制器 stop、s6 停止、同 Session resume 和三类存储恢复通过，342 个 Docker/进程/Home/日志面未发现材料泄漏。私有组合 QA 已按身份清理，生产 Work 与 Mac r9 QA 保持；见 [R4B 阶段验收](../sealskin/target-client-migration-acceptance-2026-09-15.md)。

## 2026-10-02 · R6AR 共享缩放已部署

按远程浏览器保存界面缩放百分比：管理页或远程 UI Scaling 修改，刷新/新客户端共用。支持 auto@system 和旧 Wayland Work；0 跟随客户端默认，100–300、步长 25。固定 DPR1/auto@1 不接受非零。不同已打开页面需要刷新；并发修改遇到冲突提示时刷新重试。保持比例/铺满继续仅用于固定画面。

新 Adapter `8fb90eb2…` 已通过旧 Work 和三引擎 30 个真实显示场景；生产 Home、会话、Worker 与配置保持。回退旧 Adapter 前须通过新版本正常重置非零百分比并核对新增字段已消失，不能覆盖旧目录。新 Mac/Trilium 精确硬件组合未据此补造验证。详见 [验收](../sealskin/r6ar-display-persistence-acceptance-2026-10-02.md)。
