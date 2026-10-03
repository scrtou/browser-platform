# Camoufox 冻结环境与 SealSkin Worker

R6AH磁盘治理已完成：缓存清理后可用约4.2GiB，真实数据和恢复材料保持；后续构建使用任务独立缓存并及时回收。见[验收](../sealskin/r6ah-disk-acceptance-2026-10-02.md)。

2026-09-30 登记器元数据偏差 DEV-074 已独立收尾：固定/自定义登记共用实现及既有九项回归、r10 生产登记/绑定/启动通过；三个 accepted 条目的七字段与原 artifact 派生值逐项一致。Trilium 桌面菜单仍由 DEV-073/R7F 跟踪，见 [完成条件复核](../sealskin/r7f-completion-review-2026-09-30.md)。

[文档导航](../../docs/README.md) · [开发进度](../../docs/progress.md) · [开发计划](../../docs/roadmap.md) · [验收索引](../../docs/acceptance/README.md)

这里实现 Personal 环境基线之后的 Camoufox 阶段：固定依赖和浏览器，一次生成完整设备配置，后续启动只重放产物。2026-09-12 的 **r4 已通过完整重建、存储、渲染稳定性、正式 X11 入口及 Selkies Web 串流验收**，并安装为独立 SealSkin 应用 `camoufox-personal-r4`。现有 Personal/Work 应用、会话和 Home 保持原绑定。具体证据及客户端验收范围见 [运行记录](acceptance-2026-09-12.md)。

2026-09-14 [R5A](../sealskin/proxy-protocols-acceptance-2026-09-14.md) 进一步发现并修复刚写入后直接 TERM 的存储丢失，见 [DEV-008](../../docs/deviations/DEV-2026-09-14-008-resume-storage-observation.md)。新 r6 候选增加独立 [正常退出层](../browser-runtime/README.md)，浏览器二进制、冻结设备与 seeds 保持；完整产物验收、真实容器停止恢复、显式关闭失败保留及即时 Cookie/localStorage/IndexedDB 重建均已通过。旧 r4 和中间 r5 不能沿用新候选的停止保证，生产尚未采用新版本。

## 固定版本

R5D 的 r7 在同一浏览器/冻结环境基础上加入 [显示认证层](../browser-access/README.md)，将 nginx/Selkies 材料与 TLS 私钥移出 Docker 环境和持久化 Home。新产物 `env-tw-camoufox-r7` 已重新验收：完整重放、两个 QA Home 各十次重建、离线恢复及正常 `/init`/真实显示、控制器重启和 Worker 恢复通过；五类错误材料拒绝及最终扫描也通过。版本与范围见 [R5D 报告](../sealskin/entry-authentication-acceptance-2026-09-15.md)。生产 r7 迁移未成功；R4B 后续按用户要求修订为 r9，应用、Home、策略和完整报告须绑定最终修订，不能套用旧候选。R5D 未重跑启用一致性策略的 R5C3 全矩阵。

| 组件 | 固定值 |
| --- | --- |
| Camoufox Python 包 | `0.5.6` |
| BrowserForge | `1.2.4` |
| BrowserForge 数据包 | `apify_fingerprint_datapoints 0.15.0` |
| Playwright | `1.62.0` |
| Python | `3.14.4`，来自固定基础镜像 |
| 浏览器发布 | `v152.0.4-beta.30`，Linux x86_64 |
| 浏览器归档 SHA-256 | `5720d45b894ce1770543de024c6f10d514b38be560fa2dc3226b3d8586caf672` |
| 基础镜像 | LinuxServer Firefox，摘要见 [versions.json](versions.json) |
| Worker 镜像 | `browser-platform/camoufox:0.5.6-beta.30-r4`；应用和产物同时绑定实际 image digest |

[versions.json](versions.json) 和 [requirements.lock](requirements.lock) 固定全部 36 个 Python distribution，包括生成器数据。安装使用 `--only-binary=:all: --require-hashes`，独立虚拟环境不修改 Selkies 的 Python 依赖。浏览器归档先校验官方 SHA-256，再校验 `application.ini` 的版本、BuildID 和 SourceStamp；安装后的完整文件清单在启动时逐文件验证。

来源：[官方 PyPI](https://pypi.org/project/camoufox/0.5.6/)、[BrowserForge PyPI](https://pypi.org/project/browserforge/1.2.4/)、[固定浏览器发布](https://github.com/daijro/camoufox/releases/tag/v152.0.4-beta.30)、[官方用法](https://camoufox.com/python/usage/)。

## 产物与启动边界

[environment.py](environment.py) 的 `generate` 命令调用一次 BrowserForge，再调用固定版本的 Camoufox 配置转换器，保存：

- 完整 BrowserForge dataclass 结果与完整 `resolvedConfig`。
- Canvas、Audio、字体 spacing seed，以及字体、语音、WebGL、屏幕、设备参数。
- Firefox preferences、语言、时区、固定屏幕和 X11 约束。
- 包版本、依赖锁摘要、浏览器归档/文件清单摘要、适配器源码摘要和 Worker image digest。

仅选取这些数据进入产物；生成器返回的进程环境和整个启动对象不保存。没有 GeoIP 自动定位、默认扩展下载或启动时补种子。产物使用精确 UTF-8 字节计算 SHA-256，原子创建且拒绝覆盖已有文件。不同 Profile 的产物放在被 Git 忽略的 `artifacts/`，按具体修订绑定。

`verify` 和 `launch` 路径不导入 Camoufox/BrowserForge。它们验证完整产物，再把已保存的配置传给固定浏览器；没有重新调用 `launch_options()`。验收进程还通过 import guard 检查这一点。参数被完整保存只证明重放输入稳定，页面结果是否稳定仍必须由真实浏览器验收证明。

代理继续锁定为 `profile-relay:1080`、SOCKS5 远端 DNS；DoH、WebRTC 和网页定位关闭。Worker 只使用对应的 internal 网络，或受管理模式下共享对应 Guard 的命名空间。正常启动还要求只读挂载匹配的验收报告，并设置 `BROWSER_PLATFORM_ACCEPTANCE_SHA256`：报告必须来自同一产物和镜像，完整执行 unit、启动拒绝、两个 Home 各 10 次删除重建、环境一致性与离线恢复，且整体通过。缺失或失败的报告会在 `/init` 之前终止 Worker。

验收 Worker 通过显式测试入口读取候选配置，以便验证尚未发布的产物；正常镜像入口和 GUI 浏览器入口都会检查验收报告。候选产物和验收报告不得直接替换已绑定 Profile 的修订。

## 构建、生成和验收

以下命令在本目录执行。需要 Docker 和 Python 3.11+；主机不需要安装 Camoufox。当前登录尚未获得 Docker 组时，可用 `sg docker -c '…'` 执行 Docker 命令；验收脚本会自动处理这种情况。

```bash
python3 fetch-browser.py
docker build --pull=false -t browser-platform/camoufox:0.5.6-beta.30-r4 .

mkdir -p artifacts .build/generation-home
chmod 700 artifacts .build/generation-home
CAMOUFOX_IMAGE_DIGEST="$(docker image inspect browser-platform/camoufox:0.5.6-beta.30-r4 --format '{{.Id}}')"
docker run --rm --network none --user "$(id -u):$(id -g)" \
  --mount "type=bind,src=$PWD/artifacts,dst=/output" \
  --mount "type=bind,src=$PWD/.build/generation-home,dst=/config" \
  --entrypoint /opt/camoufox-python/bin/python \
  "$CAMOUFOX_IMAGE_DIGEST" /usr/local/lib/browser-platform/environment.py generate \
  --output /output/env-tw-camoufox-r4.json --image-digest "$CAMOUFOX_IMAGE_DIGEST"

python3 acceptance.py --phase all --recreations 10 \
  --output evidence/acceptance-r4-2026-09-12.json
```

生成步骤只用于新环境，已经存在同名产物时会拒绝覆盖。重新构建出的镜像可能有不同摘要，不能直接复用其他镜像绑定的产物。新修订需要新的 ID、revision、输出路径和完整验收，旧环境必须保留原产物。本机 r1–r4 保留相同的完整 BrowserForge 结果、设备配置和 seeds；r4 相对 r3 只绑定了修正 Openbox 窗口规则和 SealSkin 启动 URL 的新镜像，Firefox preferences 也完全相同。

验收自动创建专用临时 QA Home，不挂载 Personal/Work 的 Home。测试页面由受控拦截器提供，Cookie、LocalStorage 和 IndexedDB 由页面自己的脚本读写；Canvas/Audio 也在页面执行域观测，避免把 Camoufox 的隔离执行域当作网站执行结果。外网测试单独通过浏览器访问 `https://example.com/`，并检查容器直接 IPv4/IPv6 和公网 DNS 失败。

重放验收中的 Worker 使用 Xvfb 1920×1080、只读根文件系统、drop ALL capabilities、1.5 CPU quota 和 1536 MiB 内存。屏幕和 DPR 与生成产物分别比较，CPU quota 与页面 `hardwareConcurrency=8` 分开记录。正式 Selkies 桌面需要基础镜像的可写根文件系统与初始化权限，另由 GUI 检查验收；它不继承测试容器的只读根声明。

`--phase unit`、`--phase negative`、`--phase replay` 用于定位单项失败；这类报告不能授权正常 Worker 启动。`--recreations 0` 只做短测试，也不能满足启用门槛。稳定字段出现差异时，脚本仍完成独立存储检查并保存逐次证据，最终返回非零状态；不会删掉失败字段来产生通过报告。

## 原生渲染和窗口设置

Firefox 152 的 `privacy.baselineFingerprintingProtection` 会独立于旧 RFP/FPP 开关向 Canvas PNG 写入随机 `deBG` 元数据；`gfx.font_rendering.fallback.async` 会使首次繁体文字形回退不一致。本环境锁定前者及旧 RFP/FPP 开关为 false，并关闭异步字体回退，由冻结的 Camoufox 原生配置提供稳定设备参数。探测等待完整 131 项语音加载后比较，没有删除失败字段或注入 navigator hooks。

基础镜像的 Openbox 默认最大化所有窗口，会产生 innerWidth 大于冻结 outerWidth 的不一致。[configure-desktop.py](configure-desktop.py) 为 Camoufox 加入不强制最大化、无装饰的规则。r4–r7 的窗口为 outer 1600×900、inner 1600×844，居中放在 1920×1080 桌面上；用户在 R4B 反馈该窗口过小。

R4B 使用 [桌面规格](spec.tw.desktop.json) 将窗口改为 1920×1080、位置 (0, 0)，screen/DPR 仍为 1920×1080 / 1。[resize-window.py](resize-window.py) 只调整新产物的显式窗口尺寸/位置，保留完整原始 BrowserForge 结果作为生成来源，其他设备、seeds、preferences 和旧产物不变。`--id` 必须新建、revision 必须增大；输出仍须完整验收，不能沿用旧报告。原 [spec.tw.json](spec.tw.json) 保留 r4 的历史规格。

正常 Openbox 桌面另有 `keepBorder=yes` 的 1 像素边框，会将全桌面客户区压为 1918×1078；仅修改窗口产物的 r8 因此不满足正常桌面与重放一致性。当前配置器改为 `keepBorder=no`；[Dockerfile.desktop](Dockerfile.desktop) 可在已核对的 r7 镜像上应用这一小型桌面层，再用 `rebind-worker.py` 生成 r9。构建引用使用已核对到精确 image ID 的本地标签，`BASE_IMAGE_ID` 仍传完整 ID，`DESKTOP_INPUT_SHA256` 记录 Dockerfile/配置器输入摘要。新镜像必须保留原正常退出与显示认证层，且通过重放、正常桌面和客户端分项后才可迁移。发现、失败与验证范围见 [DEV-041](../../docs/deviations/DEV-2026-09-15-041-camoufox-window-size.md)。

窗口修订示例（从项目根目录执行，使用独立输出路径）：

```bash
python3 infra/camoufox/resize-window.py \
  --artifact infra/camoufox/artifacts/env-tw-camoufox-r7.json \
  --id env-tw-camoufox-r8 --revision 8 --width 1920 --height 1080 \
  --output infra/camoufox/artifacts/env-tw-camoufox-r8.json
```

此步骤只生成窗口候选；r9 还需绑定上述桌面层镜像并执行完整 `acceptance.py --phase all --recreations 10`。每次验收使用新的输出报告，保留失败历史，不覆盖已挂载的文件。

2026-09-15 的 r9 已通过完整产物验收（23 次稳定观测）、正常 Openbox 桌面及 Linux 公网客户端复测：客户区 1920×1080、边框 0，网页 outer 1920×1080 / inner 1920×1024；点击、上传/拖放、断线和原生截图预览通过。原独立 QA Home 与用户三类测试存储保持，入口保留供 Mac 新窗口/预览复测。精确镜像、产物和失败历史见 [R4B 阶段验收](../sealskin/target-client-migration-acceptance-2026-09-15.md)，未宣称生产迁移或全部旧协议/一致性矩阵已在 r9 重跑。

2026-09-29 新建模板化 Camoufox 崩溃后，发现基础桌面的 FireFox 项会启动未受管的 `/usr/bin/firefox`。r10 候选从 Openbox 默认菜单、desktop entry 和命令入口移除系统 Firefox，默认 `HARDEN_OPENBOX=true`；已绑定的 Camoufox 二进制、环境配置、seeds 和 preferences 不变。候选镜像 `sha256:9a128663…`、r10 产物、两 Home 各 10 次重建、离线恢复及独立正常 X11/Selkies GUI 已通过；桌面右键无新窗口、系统 Firefox 不存在且正常停止释放 Home 锁。r10 已在生产绑定“测试”并从固定入口恢复，新鲜健康通过；目标 Mac/Trilium 及生产桌面右键直接用户证据仍待验收。详见 [r10 候选验收](managed-desktop-recovery-acceptance-2026-09-29.md) 与 [DEV-073](../../docs/deviations/DEV-2026-09-29-073-managed-browser-desktop-recovery.md)。

## 独立 SealSkin 应用

以下命令从项目根目录执行；安装命令拒绝覆盖已有应用 ID。[prepare-sealskin.py](prepare-sealskin.py) 先在绑定的镜像中验证产物和完整成功报告，再生成可检查的应用 JSON。

```bash
python3 infra/camoufox/prepare-sealskin.py \
  --artifact infra/camoufox/artifacts/env-tw-camoufox-r4.json \
  --acceptance infra/camoufox/evidence/acceptance-r4-2026-09-12.json \
  --app-id camoufox-personal-r4 --session-origin https://mysession.azhen.de \
  --output infra/camoufox/.build/sealskin-app-r4.json

go -C adapter run ./cmd/sealskin-install-app \
  --admin-config ../infra/sealskin/config/admin.json \
  --api-base-url http://127.0.0.1:8000 \
  --definition ../infra/camoufox/.build/sealskin-app-r4.json

go -C adapter run ./cmd/sealskin-smoke-session \
  --config ../infra/sealskin/adapter-config.json --app-id camoufox-personal-r4 \
  --language zh_TW.UTF-8 --timezone Asia/Taipei --wayland=false --hold 10m
```

应用禁用自动更新，使用实际 image digest、Personal internal 网络、固定环境变量和指定 Session origin。产物/报告通过 Docker `mounts` 增加只读挂载，保留 SealSkin 自己管理的 Home `volumes`。正式 GUI Worker 设为 1536 MiB、1.5 CPU quota、256 MiB shm、512 PID 和 `no-new-privileges`。该应用目前供独立 cleanroom 验收使用，没有把既有 `/browser/personal/` 入口切换到 Camoufox。

临时会话保持期间，以实际新容器名运行：

```bash
python3 infra/camoufox/check-gui.py --container QA_CONTAINER \
  --artifact infra/camoufox/artifacts/env-tw-camoufox-r4.json \
  --acceptance infra/camoufox/evidence/acceptance-r4-2026-09-12.json \
  --output infra/camoufox/evidence/sealskin-gui.json
```

此检查使用 X11 键盘/剪贴板操作自建页面，逐字段比较正式桌面和重放结果。[check-stream.py](check-stream.py) 另启动独立 Chromium QA 客户端测试真实 HTTPS Session 和 Selkies WebSocket；测试端使用临时 Home 和主机网络，不改变 Worker 的 internal 网络。它只从临时 `0600` 文件读取 Session URL，日志和证据不包含 token。`sealskin-smoke-session --session-file` 创建该文件并在退出时删除。

客户端浏览器单独下载到测试缓存，不进入 Worker 镜像。固定 Playwright 1.62.0 对应 Chrome Headless Shell 151.0.7922.34 / revision 1234，脚本也核对这个版本：

```bash
mkdir -p infra/camoufox/.build/playwright-client-browsers
docker run --rm --network host --user "$(id -u):$(id -g)" \
  -e PLAYWRIGHT_BROWSERS_PATH=/client-browsers \
  --mount "type=bind,src=$PWD/infra/camoufox/.build/playwright-client-browsers,dst=/client-browsers" \
  --entrypoint /opt/camoufox-python/bin/python \
  browser-platform/camoufox:0.5.6-beta.30-r4 -m playwright install chromium --only-shell
```

先用 smoke 命令的 `--session-file ../infra/camoufox/.build/private-smoke-session.json` 产生私有文件，再运行：

```bash
python3 infra/camoufox/check-stream.py \
  --artifact infra/camoufox/artifacts/env-tw-camoufox-r4.json \
  --session-file infra/camoufox/.build/private-smoke-session.json \
  --origin https://mysession.azhen.de \
  --output-dir infra/camoufox/evidence/stream-check
```

测试前先完成 `check-gui.py`，由它准备临时页面；串流测试使用新的输出目录，拒绝覆盖已有报告。API stop 请求成功后仍需确认对应 Docker 容器已消失。

`artifacts/`、`evidence/` 和 `.build/` 被 Git 忽略。部署备份必须同时保存精确产物、成功报告及镜像，不能通过重新生成来恢复原设备配置；不要覆盖已挂载的报告路径。

## 自定义指纹作业

R6E 的 [environment-job.py](environment-job.py) 处理 Adapter 写入私有 spool 的自定义指纹作业：`queue/job-<hex>.json` 是 Adapter 按规格 46.2 校验后派生的完整规格（Linux、DPR 1、WebRTC/定位关闭），执行器再次以 `validate_spec` 校验。每次只处理一个最早的作业（spool 文件锁），主机 `MemAvailable` 低于 `--min-free-mib`（默认 2048）时写入 `HOST_MEMORY_LOW` 并保持排队。生成在 `--image` 指定的固定镜像中以只读根、无网络、drop ALL、1.5 CPU/1536 MiB 执行 `environment.py generate`，生成器偶尔不满足屏幕约束（`ENVIRONMENT_SPEC_MISMATCH`）时最多重试 3 次，不修改产物；随后创建一次性 internal/egress 网络与 [QA 代理夹具](../sealskin/checks/qa-artifact-proxy.py)（别名 `profile-relay`），执行本目录的 `acceptance.py --phase all --recreations N`（默认 10），通过后由镜像自身 `verify` 核对产物与报告，再原子追加目录条目（同 ID 拒绝覆盖）。产物与报告保存在 `<spool>/artifacts/<环境 ID>/`，目录模板的只读挂载指向这两个文件；日志与生成 Home 保存在 `<spool>/evidence/<作业>/`。失败作业保留全部证据并写入稳定失败码，不进入目录。

```bash
python3 infra/camoufox/environment-job.py run \
  --spool /private/environment-jobs --catalog /private/environment-catalog.json \
  --image sha256:<固定 Worker 镜像 ID> --session-origin https://mysession.azhen.de \
  --browser-template-id camoufox-linux-v152 \
  [--clipboard-addon infra/sealskin/runtime/client-addons/<包>] [--recreations 10] [--watch 30]

python3 infra/camoufox/environment-job.py register \
  --artifact infra/camoufox/artifacts/env-tw-camoufox-r9.json \
  --acceptance infra/camoufox/evidence/acceptance-r9-1-2026-09-15.json \
  --catalog /private/environment-catalog.json --session-origin https://mysession.azhen.de \
  --browser-template-id camoufox-linux-v152
```

`--watch` 让执行器常驻轮询；省略时只处理一个作业后退出，适合由定时器触发。`register` 把已完整验收的固化产物登记为 `source=frozen` 条目，使用与自定义作业相同的模板与核对。两条路径都要求显式浏览器模板 ID，并从已接受产物自身派生 revision、engine、browser version、OS、platform 和完整 User-Agent；字段缺失或 UA 版本自相矛盾时拒绝发布，供 R7D 兼容目录继续做三元组核对。执行器未安装为服务，生产未启用；2026-09-18 的真实隔离作业与执行器单元测试见 [R6E 验收](../sealskin/custom-fingerprint-acceptance-2026-09-18.md)，执行位置差异见 [DEV-051](../../docs/deviations/DEV-2026-09-18-051-environment-job-runner.md)，R7D 元数据补齐见 [DEV-074](../../docs/deviations/DEV-2026-09-29-074-environment-registration-template-metadata.md)。

## 常见拒绝码

| 错误码 | 含义 |
| --- | --- |
| `ENVIRONMENT_ARTIFACT_MISMATCH` | 精确文件字节与预期 SHA-256 不符 |
| `ENVIRONMENT_VERSION_MISMATCH` | Python、依赖、浏览器、适配器或摘要不匹配 |
| `BROWSER_BUNDLE_MISMATCH` | 浏览器文件清单或文件内容改变 |
| `ENVIRONMENT_SEED_MISSING` | 缺少必须保存的种子，拒绝隐式生成 |
| `BROWSERFORGE_RESULT_INCOMPLETE` | 缺少完整生成结果 |
| `ENVIRONMENT_CONFIG_DRIFT` | 语言、时区、显示参数、镜像绑定或运行环境发生漂移 |
| `UNSUPPORTED_CAPABILITY` | 包含未支持的属性或能力要求 |
| `ENVIRONMENT_ACCEPTANCE_REQUIRED` | 没有绑定验收报告 |
| `ENVIRONMENT_ACCEPTANCE_FAILED` | 报告失败或仅执行了部分阶段 |
| `ENVIRONMENT_ACCEPTANCE_MISMATCH` | 报告摘要、产物或镜像绑定不匹配 |
| `ENVIRONMENT_ACCEPTANCE_INCOMPLETE` | 缺少完整的重建、稳定性或恢复证据 |

## 受管理网络与客户端包

2026-09-14 [R4A](../sealskin/client-migration-acceptance-2026-09-14.md) 已验证正常 Camoufox 的 Guard 网络、Linux 客户端边界、原生复制/截图和停止重建。`prepare-sealskin.py --network-policy-id ID --network-policy-sha256 SHA` 生成由 SealSkin 管理的网络引用，不设置静态 `docker_overrides.network`；与 `--network` 互斥。默认不传参数时保留已有静态 internal 网络路径。

可选 `--clipboard-addon` 接受与当前仓库三个脚本完全一致、无 symlink 且不允许其他用户写入的目录，并只读挂载；开启 Files upload，下载按钮仍隐藏。当前安装器还将固定分辨率显示的画面和输入层映射到客户端完整视区，以适配 1280×800 等非 16:9 视区；这保留远端 1920×1080 screen/DPR，但会在不同比例下产生非等比缩放。先冻结新的客户端包，不覆盖旧目录：

```bash
python3 infra/sealskin/build-client-addon.py \
  --output-parent infra/sealskin/runtime/client-addons
```

输出目录及完整摘要供准备器使用。新前端按 Unicode code point 处理文字与 composition；Selkies `language` 参数为系统 `LC_ALL`，应传 `zh_TW.UTF-8`，不要传浏览器 BCP 47 `zh-TW`。本次新包尚未更新生产两个旧 Wayland Worker。

隔离工具：先按 [网络 QA](../sealskin/lifecycle/README.md#验证与范围) 准备控制器和 NSS 工具，再用 `checks/prepare-network-browser.py --engine camoufox --artifact ... --acceptance ... --clipboard-addon ... --root ...` 创建正常应用；`checks/run-client-qa.py --root ... --check boundary|native-copy|screenshot-paste --output NEW_DIRECTORY` 顺序执行，避免同时操作同一桌面。`checks/check-network-browser.py --root ... --output NEW_DIRECTORY` 保存独立网络证据；`checks/check-camoufox-rebuild.py --root ... --clipboard-addon ... --output NEW_DIRECTORY` 经 SealSkin stop/new 验证 Home 数据。以上 checks 均位于 `infra/sealskin/`，只接受对应 QA 拓扑，不操作真实 Profile。

## 迁移准备

从项目根目录执行，下例只写入新的私有候选目录：

```bash
python3 infra/camoufox/prepare-migration.py \
  --config infra/sealskin/adapter-config.json \
  --policy-registry infra/sealskin/config/.config/sealskin/profile-network-policies.json \
  --storage-root infra/sealskin/storage \
  --artifact infra/camoufox/artifacts/env-tw-camoufox-r4.json \
  --acceptance infra/camoufox/evidence/acceptance-r4-2026-09-12.json \
  --clipboard-addon infra/sealskin/runtime/client-addons/native-clipboard-c79102f832b141bd \
  --profile personal --new-home personal-camoufox-r4 \
  --new-app-id camoufox-personal-r4-guard --new-policy-id personal-camoufox-r4-socks5-r1 \
  --output infra/sealskin/runtime/camoufox-migration-review
```

工具验证原策略完整修订，复制其代理设置到新的 Home/App 身份，旧策略和 journal 保留；生成的回退配置保留原路径引用与其他 Profile。当前助手只支持已验收的台湾环境及现有 SOCKS5 策略格式，其他格式或配置漂移会拒绝。工具不会实施切换，`readyToSwitch=false`；[运维步骤](../../docs/operations.md#camoufox-入口切换与回退准备) 说明实机、备份与维护核对。

R4B 增加控制器能力核对（[DEV-040](../../docs/deviations/DEV-2026-09-15-040-migration-controller-capabilities.md)）：先从产物绑定的精确镜像读取正常退出/显示认证标签，再向运行中的 Adapter inspect 读取控制器实际 `capabilities`。缺少网络/启动日志或目标镜像要求的版本时，在生成候选前拒绝；旧 Adapter 没有能力字段也视为未知。匹配时在新 Profile 写入 `required_runtime_capabilities`，准备结束再次核对能力、绑定及输入摘要。入口登录账号/CA 的相对路径也固定到原配置目录；不复制或替换 journal。完整发布仍需各 Profile 的镜像、显示 tmpfs、授权入口和回退条件，能力版本通过不是部署完成证明。

2026-09-15 的生产旧控制器已实际拒绝 r7 迁移准备，独立 r7 QA 则生成候选并保留全部输入；失败代次已清理，生产入口增加启动保护，见 [R4B 阶段验收](../sealskin/target-client-migration-acceptance-2026-09-15.md)。正式 Personal 仍在维护中。

生产独立应用 `camoufox-personal-r4` 仍在此前的静态网络，固定入口未迁移。R4A 的隔离 Guard 结果不能视为 R4B 的 Mac/Trilium、真实站点或生产切换通过。


## 受管理运行时观测

R5C3 的 [一致性策略](../sealskin/lifecycle/runtime-coherence.md) 可在已完整验收的正常 r6 Worker 中启用私有 Marionette，端口仅监听 loopback。控制器以固定有界脚本创建、隐藏并关闭自己的观测标签，读取精确受控 HTTPS 页面；不切换用户焦点、使用键鼠/剪贴板或读取用户页面。没有启用该策略的生产应用保持原行为。

页面值与冻结产物/重建验收基线比较；Intl 原始语言标签由固定 Babel/CLDR 数据规范化，不采信页面自报的匹配结果。国家和时区不同只按显式约束处理，不重新随机化语言、时区、设备参数或 seeds。新 US/en-US/纽约环境已完成两 Home 各 10 次重建和离线/存储恢复，作为 R5C3 独立 QA 产物；没有切换真实 Personal/Work Home，Mac 实机及生产迁移仍归 R4B。

## 独立模板组合执行器（R6P）

管理页分别保存通用指纹模板和显示模板，生成组合时选择引擎。新指纹源 version 2 不含 engine/browser_version；新 v3 队列包含生成目标 ID/修订/引擎/版本快照，并精确引用 `templates/fingerprints/<id>.json` 与 `templates/displays/<id>.json` 的 SHA-256；来源、窗口/屏幕和固定 DPR1 在执行器再次核对。通用源的 `fingerprint-cache/<id>/<目标快照SHA256>/environment.json` 与 receipt 保存首次按目标生成的完整来源、镜像与摘要；旧无 version 源保持 `fingerprint-cache/<id>/` 缓存与 Camoufox152 限制，旧 v1/v2 作业继续读取。目标哈希由 ID/修订/引擎/版本的排序紧凑 JSON 计算，不含镜像，因此同目标镜像变化会拒绝而非随机重建。执行器生成前及发布前（含兼容目录锁内）再次核对 accepted 目标，产物实际版本必须匹配。已固定的来源不可重建成随机设备。当前自定义目标为 Camoufox 152.0/Linux；新执行器固定 r10 受管桌面镜像，历史 r9 产物不变。

`environment-job.py run` 必须传 `--template-catalog`、当前 Adapter `--catalog`、`--browser-template-id camoufox-linux-v152` 和同一 `--spool`。新组合通过完整两个 Home 各十次重建/恢复验收及镜像校验后，先追加环境目录，再登记 accepted 显示兼容项。发布中断可使用原产物和匹配的成功报告继续；目录记录一致时不改写。失败报告、漂移和不完整缓存保留且拒绝发布。失败作业不会自动重跑；排查后用同样参数加 `--retry-job job-<hex>` 显式恢复，不能同时使用 `--watch`。已 accepted 重试无副作用；失败验收应新建组合任务，不能删除旧报告再冒充通过。

部署使用冻结的执行器源码与依赖清单，不能直接指向脏工作区。`deploy-engine-neutral-templates.py --root <私有R6Q目录>` 生成限定发布材料，`--apply` 核对证据及生产输入后仅更新 Adapter 和空闲执行器服务；不替换目录、真实 Home 或会话。队列有未完成作业时拒绝维护。回退须先核对新增作业/模板/目录，不能覆盖用户新操作；旧 Adapter 可继续读取完整 accepted 产物，R6P 版本不理解通用 version 2 源及 v3 队列；已有这些数据时不能直接降级。

独立验证工具：`check-template-desktop.py` 使用两个 accepted 组合在新 Home 做 A→B→A，检查实际尺寸、边角点击、文字、显示认证和存储；`check-template-publication.py` 复制 QA 来源/缓存，注入两类发布中断并用真实镜像校验恢复；`check-template-ui.py` 在隔离 Chromium 检查服务器渲染页面。见 [R6P 验收](../sealskin/r6p-template-separation-acceptance-2026-10-01.md)。

备份必须保留整个私有 spool（templates、fingerprint-cache、queue/status、artifacts、evidence）以及两份目录和固定执行器/镜像。需要一致快照时先等待空闲并停止作业服务；不删除失败日志。R6K 的已有归档不会自动包含新来源缓存，不能仅依赖重新生成来恢复设备身份；异机全依赖闭包继续属于灾备后续。

R6Q 当前交付与证据见 [工作项](../../docs/work-items/R6Q-2026-10-01-engine-neutral-fingerprint-templates.md)。R6Q 当时生成器能力只列 Camoufox 152/Linux，accepted Chromix 运行模板不意味着已有 Chromix 自定义生成器。

R6Q 当时交付已部署，完整结果及旧模板兼容范围见 [R6Q 验收](../sealskin/r6q-engine-neutral-acceptance-2026-10-01.md)。


## R6R 多引擎后继

R6Q 的 Camoufox 单引擎限制由 R6R 扩展：v3 通用来源分派新增 Chromix154、原生Firefox155，Camoufox152原生成与验收流程保留。执行器新增 `--native-targets` 私有 registry；旧源/v1/v2不改派。多引擎的缓存、报告、限制、精确部署与回退见[组件说明](../environment-engines/README.md)。

R6R已限定部署并收尾，完整范围和未验证项见[三引擎验收](../sealskin/r6r-multi-engine-acceptance-2026-10-01.md)。

## R6S 共用显示策略

Camoufox152与Chromix/Firefox共同支持自定义fixed/DPR1和内置auto/system。Camoufox自动产物为v2，移除固定screen/window/DPR覆盖并绑定系统DPI；固定产物继续v1。第一次设备源生成以1920×1080参考尺寸提取配置，再独立组合显示，旧缓存不重抽。自动验收使用真实Selkies客户端与两Home完整重放，正式入口仍要求完整匹配报告。运行器显式`--client-browsers`固定动态QA客户端依赖。版本、发布和回退见[多引擎组件](../environment-engines/README.md)。

R6S服务器交付已部署：Camoufox固定/自动各22份观察及离线恢复、真实动态输入和同Home切换通过；旧固定产物与缓存保持。探针就绪修复后的新作业单独验收，早期无窗口QA关闭超时保留为失败，见[最终验收](../sealskin/r6s-shared-display-acceptance-2026-10-01.md)。

R6AW正在增加四个规定内置通用指纹和固定1920×1080/DPR1显示；严格来源读者接受builtin字段并核对保留ID/内容，普通自定义来源和旧格式保持兼容。内置组合仅在独立完整验收后安装，重复发布保留已安装组合保护；状态见[R6AW](../../docs/work-items/R6AW-2026-10-02-protected-builtins.md)。
