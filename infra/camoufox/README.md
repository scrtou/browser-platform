# Camoufox 冻结环境与 SealSkin Worker

[文档导航](../../docs/README.md) · [开发进度](../../docs/progress.md) · [开发计划](../../docs/roadmap.md) · [验收索引](../../docs/acceptance/README.md)

这里实现 Personal 环境基线之后的 Camoufox 阶段：固定依赖和浏览器，一次生成完整设备配置，后续启动只重放产物。2026-09-12 的 **r4 已通过完整重建、存储、渲染稳定性、正式 X11 入口及 Selkies Web 串流验收**，并安装为独立 SealSkin 应用 `camoufox-personal-r4`。现有 Personal/Work 应用、会话和 Home 保持原绑定。具体证据及客户端验收范围见 [运行记录](acceptance-2026-09-12.md)。

2026-09-14 [R5A](../sealskin/proxy-protocols-acceptance-2026-09-14.md) 进一步发现并修复刚写入后直接 TERM 的存储丢失，见 [DEV-008](../../docs/deviations/DEV-2026-09-14-008-resume-storage-observation.md)。新 r6 候选增加独立 [正常退出层](../browser-runtime/README.md)，浏览器二进制、冻结设备与 seeds 保持；完整产物验收、真实容器停止恢复、显式关闭失败保留及即时 Cookie/localStorage/IndexedDB 重建均已通过。旧 r4 和中间 r5 不能沿用新候选的停止保证，生产尚未采用新版本。

## 固定版本

R5D 的 r7 在同一浏览器/冻结环境基础上加入 [显示认证层](../browser-access/README.md)，将 nginx/Selkies 材料与 TLS 私钥移出 Docker 环境和持久化 Home。新产物 `env-tw-camoufox-r7` 已重新验收：完整重放、两个 QA Home 各十次重建、离线恢复及正常 `/init`/真实显示、控制器重启和 Worker 恢复通过；五类错误材料拒绝及最终扫描也通过。版本与范围见 [R5D 报告](../sealskin/entry-authentication-acceptance-2026-09-15.md)。r7 尚未迁移生产，R4B 必须使用匹配 r7 的应用、Home 与策略候选；R5D 未重跑启用一致性策略的 R5C3 全矩阵。

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

基础镜像的 Openbox 默认最大化所有窗口，会产生 innerWidth 大于冻结 outerWidth 的不一致。[configure-desktop.py](configure-desktop.py) 为 Camoufox 加入不最大化、无外部边框的原生规则，正式桌面与重放测试均为 outer 1600×900、inner 1600×844；远程屏幕仍是 1920×1080、DPR 1。

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

可选 `--clipboard-addon` 接受与当前仓库三个脚本完全一致、无 symlink 且不允许其他用户写入的目录，并只读挂载；开启 Files upload，下载按钮仍隐藏。先冻结新的客户端包，不覆盖旧目录：

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

生产独立应用 `camoufox-personal-r4` 仍在此前的静态网络，固定入口未迁移。R4A 的隔离 Guard 结果不能视为 R4B 的 Mac/Trilium、真实站点或生产切换通过。


## 受管理运行时观测

R5C3 的 [一致性策略](../sealskin/lifecycle/runtime-coherence.md) 可在已完整验收的正常 r6 Worker 中启用私有 Marionette，端口仅监听 loopback。控制器以固定有界脚本创建、隐藏并关闭自己的观测标签，读取精确受控 HTTPS 页面；不切换用户焦点、使用键鼠/剪贴板或读取用户页面。没有启用该策略的生产应用保持原行为。

页面值与冻结产物/重建验收基线比较；Intl 原始语言标签由固定 Babel/CLDR 数据规范化，不采信页面自报的匹配结果。国家和时区不同只按显式约束处理，不重新随机化语言、时区、设备参数或 seeds。新 US/en-US/纽约环境已完成两 Home 各 10 次重建和离线/存储恢复，作为 R5C3 独立 QA 产物；没有切换真实 Personal/Work Home，Mac 实机及生产迁移仍归 R4B。
