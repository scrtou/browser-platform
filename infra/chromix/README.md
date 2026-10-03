# Chromix Worker

[工作项](../../docs/work-items/R6L-2026-10-01-chromix.md) · [验收](../sealskin/r6l-chromix-acceptance-2026-10-01.md)

固定 Linux x64 Chromix 154.0.8037.57，源码与发布包摘要见 [release.lock.json](release.lock.json)。上游 provenance 只证明包/ELF 校验，未完成原生运行及指纹验收；本项目另做实际 Worker、控制器、网络和入口测试。

首个模板提供 Linux、en-US、UTC、1280×720、DPR 1 的 X11/Selkies 浏览器。每个新 Home 生成独立非零种子，保存于 `.chromix/identity.json`，重启、备份恢复后保持；`.chromix/profile` 保存 Chromium 数据。禁止将既有 Firefox/Camoufox Home 直接切换到 Chromix，反向切换同样拒绝。其他语言/时区、任意 GPU/字体组合、完整跨 API 指纹一致性和跨 OS 模拟尚未验收，不通过自定义参数入口开放。

## 运行边界

- 启动器校验固定二进制、严格环境 JSON、摘要、版本、时区和显示尺寸；只构造允许的参数。环境产物的 accepted 状态由受信任服务端目录管理，Worker 不把未读的验收报告当作运行观测。
- 浏览器以桌面用户运行，持有独占 Home 锁；X11 关闭请求核对主进程执行文件、启动时间、窗口 PID 和 WM_DELETE_WINDOW。关闭拒绝/超时保留浏览器及占用，不发送强杀信号。
- 复用已固定桌面和 Session 认证层；专用入口替代旧 Camoufox 校验入口。软件目录必须可供非 root 读取，私有 Home/证据仍使用私有权限。
- 浏览器只连接 `profile-relay:1080`，关闭隐式 loopback 代理绕过并限制本地解析和 WebRTC 非代理 UDP；实际出站仍由 Guard/Relay 强制控制。DIRECT 与 proxy_required 分别验证。
- 保留 Chromium 用户命名空间及 seccomp 沙箱，不使用 `--no-sandbox` 或 privileged。容器的 [seccomp.json](seccomp.json) 来自固定 Moby profile，增加 clone/setns/unshare/chroot；仍保留其余默认限制、no-new-privileges 和平台能力限制。来源见 [seccomp-source.json](seccomp-source.json)，许可证见 [seccomp.LICENSE](seccomp.LICENSE)。生产 Docker API 配置必须使用完整 JSON，而非 CLI 专用的宿主文件路径。
- 正式模板没有 CDP 调试端口；`qa-browser.py` 只在独立 QA 挂载。私有 HTTPS QA 的 SPKI 放行只针对测试叶证书，不写入正式镜像或模板。
- Chromium 默认 UA 使用简化版本 `Chrome/154.0.0.0`，模板仍记录实际二进制版本；兼容检查显式支持相同 major 的简化 UA，不伪造完整版本。

## 准备与构建

```bash
python3 infra/chromix/prepare-release.py --output /private/new-package
python3 infra/chromix/build-image.py --package /private/new-package --output /private/new-build.json
```

准备器拒绝摘要不符、路径穿越、符号链接及执行文件不匹配。构建只使用已安装的精确桌面基础镜像和校验包，网络关闭；输出新的内容摘要标签和文件清单。默认保留 4 GiB 磁盘余量，并预算构建上下文/层空间。保留上游许可证与包内字体来源信息；构建源清单不包含生产凭据。

## 验证与注册

1. `python3 -m unittest discover -s infra/chromix -p 'test_*.py' -v` 检查参数、Home 锁/种子、危险输入和归档拒绝。
2. `check-worker.py --image <完整 image ID> --output <新私有 runtime 目录>` 检查真实 /init、X11、显示认证和正常关闭。
3. 按现有 `prepare-network-qa.py` 流程准备独立 network-qa、固定控制器、工具、显示 tmpfs 与 DIRECT 主机只读证据。随后运行 `check-integration.py --root <qa> --image <ID>`；加 `--proxy --output-name chromix-results-proxy` 检查认证 SOCKS5。只接受新证据目录，失败资源先按原 operation 核对并正常停止后重试。
4. `check-entry.py`、`check-management.py` 和 `check-recovery.py` 验证真实账号/启动确认/Session 交接、管理创建、关闭拒绝和独立解密 Home 激活。脚本保留失败状态，`--verify-only`、`--resume-refusal` 只供核对同一 QA 状态后的继续，不是任意重置。
5. `prepare-catalog.py --help` 列出构建与各项匹配证据；先输出 QA 目录候选，管理/恢复通过后提供对应结果，release gate 才为 passed。注册是向原目录追加，不替换现有浏览器条目；最终应用不携带 QA 脚本、SPKI 参数或调试端口。

只选已实际验收的模板。旧 Camoufox 自定义生成作业仍归其原引擎，不会生成 Chromix 产物。当前选定 Home 加密恢复已测，整机/异机灾备继续归 R6K 后续。

## 更新与回退

更新 Adapter 仅包含 Chromix 引擎兼容和 Home 保护；控制器、旧浏览器及 R7G/R6I 发布范围独立。发布前备份原 Adapter 二进制与两个目录，核对摘要后原子替换并重启 Adapter；现有 Worker/Home 不重建。

回退须先禁用 Chromix 新建，并正常停止所有新建 Chromix 浏览器、保留其 Home 与数据；确认目录无仍需新引擎解释的条目后恢复原目录和 Adapter。若发布后尚未创建 Chromix，可直接恢复保存的两个目录与二进制并重启 Adapter。不能恢复旧目录覆盖发布后用户新增或修改的条目。

## 当前部署与首次使用

2026-10-01 固定 Worker 已安装，最小 Adapter 和两个追加目录已部署；[deploy.py](deploy.py) 校验前后摘要并提供受控回退，readiness 使用 public_base_url 的正式 Host。Personal/Work 健康且原容器/绑定保持。没有创建生产 Chromix Home。

进入 https://mybrowser.azhen.de/manage/ ，登录并完成页面要求的近期密码确认，新建浏览器时选择 **Chromix 154**，选网络/代理后打开。目标 Mac 客户端首次使用仍待验证。

后续用户反馈（2026-10-01）：已重新提交、创建并打开首个生产 Chromix 浏览器，网络为受管理 DIRECT。此前“未创建”是部署完成时状态；历史创建失败原因未确定，详见 [R6L1](../../docs/work-items/R6L1-2026-10-01-chromix-create-form.md)。

## 中文字体修订 cjk-r2（2026-10-01）

旧版专用 FONTCONFIG_FILE 仅扫描包内字体，导致部分简体汉字缺字，虽然系统层已有 Noto CJK。修订增加固定系统字体目录，保留 en-US/UTC、原浏览器版本和种子。四个 Noto CJK 字体文件及配置摘要见 [fonts.lock.json](fonts.lock.json)；启动时校验，缺失/变更即拒绝，不读取主机字体。字体许可证仍在镜像 `/usr/share/doc/fonts-noto-cjk/copyright`。

[Dockerfile.fonts](Dockerfile.fonts) 可在精确 R6L 基础镜像上离线构建增量（上下文含 launcher.py、fonts.lock.json、fonts.conf.template）；基础层 ID 必须为 `sha256:cd521d91037af114833f9df994e3242c4d6078859212909c586b412da660a3ae`。完整构建器也包含相同字体输入。[prepare-font-revision.py](prepare-font-revision.py) 从原目录和真实字体/Worker QA 准备新目录，不直接部署；先验证当前目录摘要，再追加新修订，保留旧条目供回退。

新镜像为 `sha256:19f20e6ec641f6240cdc238ae041fc16c93515c83b2da1943871026949d3a2e6`，已登记指纹 `chromix-154-en-us-utc-1280-cjk-r2`，浏览器和显示选择保持 Chromix 154 / Chromix 1280×720。已运行实例需在管理页正常停止、近期认证并应用新修订后重新打开；不能仅刷新网页。旧 Home/种子保持，回退使用原 r1 模板及旧镜像。

实际简繁/混排输入、字体归属、截图、显示认证及正常退出通过；不是所有 Unicode 字符、Mac 输入法、网络/恢复全矩阵重新验收。详见 [R6L2 验收](../sealskin/r6l2-cjk-acceptance-2026-10-01.md)。

## 自动分辨率（R6N，已部署）

启动器接受 screen.mode=auto；width/height 为初始窗口尺寸。禁止 SELKIES_MANUAL_WIDTH/HEIGHT，要求 MAX_RES=3840x2160，DPR 1。公开 fingerprint 参数会补固定屏幕，候选改为显式持久种子及硬件/存储默认值、native GPU，不使用 fingerprint=off。独立环境验收已通过并追加到生产目录；现有浏览器需停止后主动应用。

`check-worker.py --auto-resolution` 验证镜像内已安装启动器及真实 X11 resize；加 `--client-resize` 在隔离 Worker 内运行实际 Selkies 客户端。`--native-screen-probe` 是保留的早期诊断旁路，只用于独立 QA，不能作为正式启动验收。早期挂载探测不作为镜像验收；不替代网络、恢复与发布门槛。

`Dockerfile.auto` 在固定 cjk-r2 上复制启动器和 `install-resolution-limit.py`，离线构建；构建前核对基线 tag 的 image ID。安装器拒绝 Selkies/前端摘要变化，仅修订有 MAX_RES 的 X11 布局及自动画面通知/坐标。`prepare-auto-revision.py` 根据匹配镜像的客户端、网络、入口、管理和恢复结果准备目录；`--release` 要求最终门槛，`deploy-auto-revision.py` 要求审阅的输入摘要并保护用户后续写入。


## R6O · UI scaling 修订（服务器已部署，2026-10-01）

Chromix 新增 v2 环境规格：screen.mode=auto、screen.dpr=system，目录 screen=auto@system；移除强制 scale=1，保留 R6N 自动尺寸、最大物理像素 3840×2160、显式种子、字体、网络与正常退出层。网页的 CSS screen/窗口尺寸随系统 DPI 改变，DPR 跟随 UI Scaling；客户端 DPR 2 的 Selkies 默认缩放也可为 200%。旧 v1 auto@1/固定产物保持原契约。

自动模式仍由 Profile 模板绑定保存。UI Scaling 的具体百分比沿用 Selkies 自身客户端设置，并非新增的跨客户端共享 Profile 字段；新客户端可按自身像素密度初始化。跨客户端统一百分比、并发客户端冲突处理不在本修复中冒称完成。新修订需正常停止后应用，不能热改旧环境。

本次增量只改 launcher 的版本化 DPR 契约及目录兼容/UI说明；网络、账号、存储与退出层引用 R6N 已通过基础镜像证据，不冒称完整重跑。新镜像必须通过真实 UI 控件、尺寸/点击/输入和正常关闭验收后才发布。工作项：[R6O](../../docs/work-items/R6O-2026-10-01-ui-scaling.md)。

构建使用 Dockerfile.scaling，并核对 base tag 为 e7e71db 镜像；prepare-scaling-revision.py 严格要求新镜像真实 UI 及 resize 结果，继承证据明确单列。deploy-scaling-revision.py 校验最小二进制/目录摘要、只追加并保持运行实例。新模板：chromix-154-en-us-utc-scaling-r1 / chromix-x11-scaling-r1。

R6P 将管理页的指纹源和显示策略独立保存，但当前自定义生成器只支持 Camoufox 152.0、固定 DPR1。Chromix 继续选择已有验收过的固定/自动/系统 DPI 组合；R6Q 的新通用指纹源虽不绑定引擎，当前仍没有 Chromix 自定义生成器，组合表单不会提供该目标，既有 Home 和显示偏好保持。见 [R6P 工作项](../../docs/work-items/R6P-2026-10-01-fingerprint-display-separation.md)。


## R6R 自定义生成

新增 v3 产物支持通用语言列表/时区及固定显示组合，复用已固定154.0.8037.57二进制与字体。种子改由通用来源/目标缓存冻结，同来源跨显示复用；旧v1/v2仍保持每Home种子及已有自动/UI scaling契约。自定义模式采用显式种子、原生GPU/屏幕、受管理语言Preferences（保留其他Home字段），不使用会覆盖多语言的fingerprint-locale。窗口须等于屏幕，DPR1，WebRTC仅代理。完整API样本、十次重建与恢复的范围见[多引擎组件](../environment-engines/README.md)，不宣称跨OS模拟或虚构GPU。

R6R已限定部署并收尾，完整范围和未验证项见[三引擎验收](../sealskin/r6r-multi-engine-acceptance-2026-10-01.md)。

R6S自定义生成使用Chromix v4产物，同时支持共享fixed/DPR1与auto/system；来源/目标种子固定，允许独立小窗口。旧v1/v2/v3产物按原契约读取，不自动修改已有Home。见[共同显示契约](../environment-engines/README.md)。

R6Z1 修复同屏尺寸固定窗口：Chromix v4 的 window与screen相同时使用最大化几何，避免非最大化窗口1919×1079偏差；其他固定窗口仍按独立尺寸，auto策略保持。原产物/镜像/种子保留，新镜像组合须重新验收。[验收与当前发布范围](../sealskin/r6z1-chromix-window-acceptance-2026-10-01.md)。
