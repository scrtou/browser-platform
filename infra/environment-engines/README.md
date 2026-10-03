# 三引擎环境与受保护内置模板

当前R6AW已于2026-10-03通过24组合、四份固定Camoufox桌面补验、完整包/安装及实际部署，生产可见4/2/24且零账号/零浏览器；精确镜像、失败边界与244文件异机留存见[R6AW验收](../sealskin/r6aw-builtins-acceptance-2026-10-03.md)。后续1.0整理另行推进。以下早期版本段落保留对应范围。

2026-10-01修复已部署：[R6Z1](../../docs/work-items/R6Z1-2026-10-01-chromix-window-geometry.md) 承接 [DEV-119](../../docs/deviations/DEV-2026-10-01-119-chromix-fullscreen-sized-window.md)。旧镜像固定screen/window均1920×1080时，非最大化窗口实际outer为1919×1079；新策略对同屏尺寸窗口使用最大化，保留小窗口非最大化与auto最大化。精确尺寸门槛和原失败报告保留，隔离及线上原组合完整验收通过，新任务job-ab3a8747c0384642已accepted可选；[R6Z1验收](../sealskin/r6z1-chromix-window-acceptance-2026-10-01.md)记录版本及范围。

[工作项](../../docs/work-items/R6S-2026-10-01-shared-display-templates.md) · [管理契约](../../docs/specs/proxy-environment/management.md#r6s-三引擎共用显示模板)

通用指纹模板保存语言列表和 IANA 时区，显示模板分为自定义固定尺寸/DPR1与系统内置自动分辨率/DPR随UI Scaling变化，两类均供三个引擎使用。组合时可选 Camoufox 152.0、Chromix 154.0.8037.57 或原生 Firefox 155.0.1，均为 Linux x86_64。列表同时检查 accepted 浏览器目录及固定生成能力。旧 Camoufox 源和 v1/v2 作业保持原限制。

| 目标 | 设备特征 | 网络策略 | 显示能力 |
| --- | --- | --- | --- |
| Camoufox 152 | 原 BrowserForge/冻结配置流程 | WebRTC 禁用，经平台代理 | 自定义 fixed/DPR1；内置 auto/system |
| Chromix 154 | 来源/目标固定种子；原生 GPU/屏幕，显式标量 | WebRTC proxy-only，Guard 阻止绕过 | 自定义 fixed/DPR1；内置 auto/system |
| Firefox 155 | 原生 Linux 设备特征，无随机设备伪装 | WebRTC 禁用，经平台代理 | 自定义 fixed/DPR1；内置 auto/system |

Firefox 使用已有 r10 桌面基础镜像中的 `/usr/lib/firefox/firefox` 155.0.1；真实 UA 为 `Firefox/155.0`。它与旧 Work 的 `firefox_legacy` 分开登记，不转换旧 Home。Chromix UA 为 `Chrome/154.0.0.0`。当前固定环境中语音列表原生为空、Chromix WebGL 为 null；不伪造语音/GPU，不宣称跨 OS 或每个 Firefox 来源都有不同设备身份。Firefox 关闭缺少语音服务时的提示条，避免异步改变 viewport，语音 API 仍返回真实结果。

`native_jobs.py` 在既有 spool 锁内执行，按指纹来源 ID 和完整 generation 目标摘要缓存 device.json；缓存绑定来源 SHA、目标和镜像。Chromix 种子属于来源/目标，不属于显示或 Home；同来源不同显示使用相同种子。旧 Chromix v1/v2 的每 Home identity 及自动分辨率/UI scaling 模板保持原行为。原生 Firefox `.firefox/profile` 与 `.firefox/worker.lock` 独立，跨引擎修改既有 Home 双向拒绝。

R6Z1 为同版本 Worker 修复提供显式缓存升级：维护发布核对旧/新镜像和来源后，在原缓存下追加 `runtimes/<新镜像SHA256>/device.json`。原 device.json 和旧产物不改；新记录除 image 外必须与原记录完全相同（含 seed、generation、source_sha256），否则生成仍拒绝。没有预先登记的精确镜像修订继续返回 NATIVE_CACHE_CHANGED，不能自动换镜像或重抽种子。新镜像组合仍须新作业完整验收才能发布。

原生产 launcher 只接收校验过的 artifact 和 HTTP(S)/about:blank URL，拒绝任意 flags；Worker 核对完整镜像/版本/产物/环境摘要。语言偏好在 Home 独占锁内原子更新且保留其他字段。受管理网络、显示认证、剪贴板和正常退出继续使用固定基础组件，正式应用不包含 QA 的 CDP/BiDi 或证书放行参数。

## 构建与验收

`python3 infra/environment-engines/build-images.py --output <新的私有runtime目录>` 在精确已有基础镜像上离线构建三份薄镜像；相同输入复用已核对标签，不能覆盖历史镜像。生成器通过私有 version 1 `native-targets.json` 映射三个固定目标到完整镜像 ID；不接受请求提供镜像。

只修订某个引擎时可加 `--engine chromix`（可重复）构建该引擎，其余目标继续引用原已验收镜像；新镜像必须重新完成对应组合验收。Chromix 的实际 X11 WM_CLASS 为 `Chromium-browser`，新窗口策略按该值匹配，固定模式不会被基础桌面的通配最大化规则覆盖。

每个组合生成后运行 `acceptance.py`：正常 X11 桌面、两个独立 Home、每 Home 初次启动加十次重建、三类存储及离线恢复、HTTPS 经隔离 Relay、IPv4/IPv6 直连拒绝、显示认证和真实鼠标/键盘输入。固定显示匹配屏幕与独立窗口；自动显示允许screen/window/DPR变化，非显示字段在重建中精确匹配。真实Selkies客户端覆盖100/150/200%与复位、尺寸变化、DPR1/2重连、3840×2160上限和实际点击输入；画布按相同DPR比较。仅 `phase=all`、至少十次重建/22份观察且匹配产物/镜像的 PASS 报告能发布。`diagnose.py` 的零重建诊断永远不能通过发布门槛。

报告一旦存在即不覆盖；failed 报告阻止重试发布，修订 Worker 后须建立新作业。发布中断或目录写入失败可在核对后 `--retry-job <原ID>`，复用原 accepted 产物/报告，幂等补齐兼容目录。来源/目标/镜像漂移拒绝，不能用新随机值代替。`check-publication.py`、`check-negative.py`、`check-display-switch.py` 验证恢复、真实入口拒绝和同 Home 显示 A→B→A。

## 部署与回退

`deploy-shared-displays.py --root <R6S私有目录>` 准备可核对材料；`--apply` 检查最终源码清单、六组合QA、原二进制/目录/作业摘要，短暂停止管理进程和空闲runner完成替换，保留所有浏览器Worker和Home。向目录追加三引擎各固定/自动默认组合，复制对应通用来源及精确缓存，不复制QA Home、队列或状态。发布定义使用生产用户、入口和剪贴板依赖。发布状态以工作项和验收记录为准。

动态验收客户端缓存通过 `--client-browsers` 显式传入；冻结源码、registry、不可变镜像、来源/缓存、正式产物/报告、客户端缓存都是备份依赖。最终默认产物保存在私有release根，不依赖QA Home。
失败自动回退只在所有受保护输入和作业未变化时恢复保存文件；发现用户新操作则保留并记录待核对，不覆盖新条目。已有原生 Firefox 目标/产物后不能直接降级到不识别 `firefox` 的旧 Adapter；必须先核对全部新引用及历史，不删除 Home/作业来换取回退。

## 显示来源与运行契约

内置来源ID为`display-0000000000000001`，只读revision1、`mode=auto`、`dpr_mode=system`；来源中的DPR0表示按系统计算，并非网页返回0。v3组合screen省略deviceScaleFactor，显式mode=auto/dprMode=system。自定义来源只允许fixed/DPR1，可设置小于屏幕的合法窗口。旧Chromix auto@1继续按原引擎范围读取。

新产物为Camoufox v2（auto，fixed保持v1）、Chromix v4、Firefox v3。自动模式移除固定屏幕/窗口和强制DPR覆盖，使用原生显示与系统DPI；固定模式保留显式尺寸。启动前按精确窗口类配置Openbox位置、去边框和自动最大化。Camoufox首次设备来源生成用1920×1080参考尺寸，再组合显示策略；参考尺寸只用于设备数据生成，不代替实际屏幕。BrowserForge来源保留，设备参数按来源/目标缓存，换显示不重抽。

“指纹模板”页的独立组合区域始终显示引擎，空来源时提示先保存；“显示模板”页分系统内置和自定义。新增浏览器仅显示实际accepted兼容组合，因此默认Firefox需要完整环境、显示及兼容关系，不能仅登记目标。UI Scaling不同于网页缩放，百分比仍由Selkies客户端设置；不自动切换现有浏览器，不改变Firefox原生设备能力。

Chromix v4显式禁用字体子像素定位，避免DPI与窗口联动刷新字体缓存后，同DPR的文字度量变化；固定与自动使用相同策略。旧Chromix版本不改。新镜像需要新来源/目标缓存，不改写旧缓存收据。

R6S已于2026-10-01完成服务器验收并限定部署。六组合共132份观察及恢复、动态显示/输入、同Home切换和拒绝/发布恢复全部通过；默认发布仅复制六组合引用的来源及当前镜像缓存，失败/被替代来源留在私有QA证据。最终版本与边界见[验收](../sealskin/r6s-shared-display-acceptance-2026-10-01.md)。

## 1.0 受保护种子（R6AW已部署）

[R6AW](../../docs/work-items/R6AW-2026-10-02-protected-builtins.md)补齐US/TW/JP/CN四指纹、自动及1920×1080/DPR1两显示；[管理契约](../../docs/specs/proxy-environment/management.md#r6aw10-内置数据契约)定义保留ID、不可删除和安装边界。24个组合必须逐个通过原完整门槛才能安装，后续普通生成任务不会自动标为内置。`native_jobs.py`沿用精确来源/目标/镜像缓存，Python与Go来源读者同步接受受保护种子；实际设备与检测限制未扩大。24组合已按最终v6镜像完整验收并部署，精确证据见页首验收。

R6AW独立机增量：自动显示验收的Playwright客户端现在使用单独的私有容器/cgroup，经受测Worker的loopback访问显示/BiDi，避免客户端解码与Worker共享1.5CPU/1536MiB预算。Worker预算与隔离网络、原输入速率/精确文本断言、显示矩阵和重建次数不变。客户端仅挂只读QA脚本/浏览器缓存和独立证据输出，认证材料经stdin传入；超时先关闭客户端，再正常关闭Worker。失败输入额外记录实际文本/焦点/DPR，不能用补发文本或更宽松断言掩盖重复键问题。见[DEV-143](../../docs/deviations/DEV-2026-10-02-143-remote-reconnect-input.md)，完整矩阵及部署已通过，见页首验收。

R6AW发现并修复实际客户端的初连逐轴4080截断和窗口变化时重复DPR（[DEV-145](../../docs/deviations/DEV-2026-10-02-145-client-dpr-resolution-clamp.md)）。`build-client-resolution.py --targets <原固定目标表> --output <新私有目录>`在三个精确本地镜像上离线建立薄层；`../browser-runtime/install-client-resolution.py`要求固定JS摘要和唯一替换锚点，不接受未知上游。初连与resize统一以CSS尺寸输入，发送时只乘一次DPR，服务器在帧缓冲分配前保持3840×2160按比例上限。固定/手动路径和画布输入映射保持原语义。`check-client-resolution.py`用镜像内Node执行实际JS片段及完整语法核对，旧代码需复现回归；新镜像仍必须完整组合验收，构建成功不等于发布。

`package-builtins.py`仅从完整24项accepted矩阵导出精确来源、12个当前来源/目标缓存、产物/报告及摘要清单，不复制账号、Home或队列。`prepare-builtin-install.py`验证包/报告/矩阵及本机镜像，在新私有路径重新构造主机应用定义和候选目录；它不写运行中的目录，不启动浏览器。实际激活须由维护部署在runner锁内、写者停止时完成，并保留旧目录/新增文件清单以回退。工具、24矩阵及受控部署已通过R6AW验收。

自动显示的合成客户端预算为2CPU/3GiB内存、512MiB共享内存和1GiB临时目录，以容纳高DPR解码与完整截图；`client-probe.py`在退出时记录cgroup峰值/事件及临时空间。该预算只用于QA客户端，受测Worker仍为1.5CPU/1536MiB。R6AW自动/固定两组可以在不同机器执行，但必须先校验相同的12份来源/引擎缓存及精确镜像，最终仍逐组合核对24份完整报告。

固定Camoufox的历史完整报告使用无头浏览器；R6AW还用`check-fixed-camoufox-desktop.py`对相同四份产物补齐正常桌面完整重建、显示认证/输入及离线恢复，写入独立的`desktop-acceptance.json`。内置包必须包含原报告和桌面补验报告；不能从无头accepted推定桌面通过。普通自定义固定Camoufox仍沿原生成门槛，内置交付额外门槛不扩称所有历史任务已做桌面补验。

`builtin_bundle.py`在导出及安装准备两处逐项验证规定来源、完整24矩阵、唯一ID/兼容三元组、镜像、显示、缓存设备及完整报告。`check-builtin-package.py`仅用真实完成的包验证正常准备、重算摘要后的混配拒绝、已有冲突和重复目标目录拒绝；结果不代表生产安装。`deploy-builtins.py`按R6AW固定范围准备/激活已验证包，停止空闲写者并持spool锁，记录新增文件与前后输入；只有原输入未发生独立变更才自动恢复旧文件并删除本次精确新增文件。具体部署事实以R6AW验收为准。

R6AW键盘顺序修订：`build-keyboard-order.py --targets <固定目标表> --output <新私有目录>`为三个引擎安装有界的X11键盘进程回收，防止超时后标点迟到。来源/设备缓存只在新的QA根按已核对的镜像派生关系重绑定，种子/设备值保持；旧缓存、失败任务和旧镜像报告保留。新镜像24组合与四份固定Camoufox桌面补验须重新通过，原16项accepted不移植。见[输入运行契约](../browser-runtime/README.md#x11键盘输入顺序r6aw已部署)。

固定桌面补验可用重复的`--environment-id`明确选择当前独立QA分片中的已accepted固定Camoufox产物；省略时仍要求四项。每份原门槛保持，最终`verify_bundle`逐地区要求四份完整桌面报告。多分片通过`assemble-builtin-qa.py`合并原报告字节与来源缓存，不能由局部成功推定完整24项。

收集分片时按请求spec ID定位原作业目录，再核对application中的实际mount；Camoufox自动产物ID带`-artifact-1`，不能直接当作原目录名。汇总可把文件放入按目录环境ID规范化的新目录，但必须保持原产物/报告字节，包校验仍按固定/自动生成器各自的身份契约核对。DEV-151记录真实材料验证及旧工具的安全拒绝。

独立机Firefox首次IndexedDB初始化在原15秒QA响应窗口发生超时，诊断观察到慢盘同步写入影响。R6AW对应US/TW自动Firefox改由本机按原条件完整通过，异机原失败保留；不据此承诺任意存储延迟下都能通过生成验收。镜像归档/冷导入与浏览器QA须串行，避免共享磁盘竞争；超时失败继续保留证据，不能放宽报告或改写accepted。
