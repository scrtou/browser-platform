# 浏览器正常退出层

[文档导航](../../docs/README.md) · [Camoufox](../camoufox/README.md) · [生命周期](../sealskin/lifecycle/README.md)

固定 LinuxServer 桌面的原 `svc-de/finish` 向浏览器及其子进程发送 TERM；这不等于 Firefox/Camoufox 正常退出，刚写入的 localStorage 可丢失。失败与对照证据见 [DEV-008](../../docs/deviations/DEV-2026-09-14-008-resume-storage-observation.md)。本目录为已固定的 Worker 增加独立退出层，不修改浏览器二进制或环境配置。

`browser-shutdown.py` 以桌面用户运行，在 X11 下向可核对进程身份、启动时间及 PID 属性的顶层窗口发送 `WM_DELETE_WINDOW`。它等待浏览器退出及 Camoufox Home 锁释放，不发送终止信号，不确认关闭对话框。等待启动中的 Camoufox 校验器，避免在浏览器启动前错误地报告已关闭。

`PIXELFLUX_WAYLAND=true` 时使用 `wayland_shutdown.py`：核对唯一 Firefox 主进程、`/config/.XDG/wayland-N` socket 的类型/属主及其 labwc peer 身份，再通过 `zwlr_foreign_toplevel_manager_v1` version 3 请求关闭已完成属性更新的 `firefox` 根窗口。每个窗口只请求一次，排除 parent 对话框和其他应用；协议不提供逐窗口 PID，因此仅适用于此固定单浏览器 Worker。未知协议、身份变化和无法确认的窗口状态均拒绝，详见 [DEV-042](../../docs/deviations/DEV-2026-09-15-042-work-wayland-shutdown.md)。

新镜像标签为 `io.browser-platform.browser-shutdown=1`。支持该能力的 SealSkin 在显式 stop 时先执行固定的无输出、非交互退出命令，检查 Docker exec 的容器归属与最终退出码；超时、拒绝关闭、exec 故障均保留 Worker、Home 占用及停止意图，返回可重试失败。确认后才停止并删除容器，再按既有顺序回收 Guard/Relay。

容器自身通过依赖桌面/D-Bus 的 s6-rc oneshot `down` 动作执行同一关闭请求；动作结束前不允许桌面依赖退出，原桌面清理脚本保持原样。不能放在 longrun 的 `finish` 中，因为它不能提供该停止顺序屏障。关闭上限 12 秒，oneshot 上限 15 秒；SealSkin 显式停止使用 30 秒 Docker 超时。固定 Docker SDK 的高层创建接口不接受 `stop_timeout`，容器默认超时未改；维护时直接停止容器须显式使用 `docker stop -t 30`。整机停止窗口仍须在 R2 验证。Docker 强制终止、OOM、主机断电等仍可能丢失尚未提交的数据，不能据此宣称正常退出；显式 API 的失败保护也不能阻止管理员强制结束容器。

## 构建与绑定

```bash
python3 infra/browser-runtime/build-image.py \
  --base-image sha256:8c9aa0a2734625f5963bb12325c62cf973ea42c70b8a23bb7c4f9d0652b20a34 \
  --tag-prefix browser-platform/camoufox:0.5.6-beta.30-r6 \
  --output infra/sealskin/runtime/worker-shutdown-image.json
```

准备器使用源文件及精确基础 image ID 生成内容版本，拒绝覆盖不同输入的标签；构建不用网络，只接受已经审核的原桌面退出脚本。为 BuildKit 创建的基础别名同样按 image ID 命名，构建后核对完整基础层前缀。保留旧镜像供恢复，不向运行容器热替换退出脚本。

Camoufox 的新镜像必须绑定新产物修订和完整验收报告；保留原 BrowserForge 结果、设备配置、seeds、preferences 和版本元数据，仅更新修订身份及 image digest，不重新生成环境。新旧产物及报告不能相互替代。容器内执行产物测试与两 Home 各 10 次重建；部署准备器测试另在宿主机执行，不向 Worker 挂载整个仓库。

用构建输出的完整 image ID 生成候选，再执行完整验收：

```bash
python3 infra/camoufox/rebind-worker.py \
  --artifact infra/camoufox/artifacts/env-tw-camoufox-r4.json \
  --image NEW_WORKER_SHA256_ID --id env-tw-camoufox-r6 --revision 6 \
  --output infra/camoufox/artifacts/env-tw-camoufox-r6.json
python3 infra/camoufox/acceptance.py \
  --artifact infra/camoufox/artifacts/env-tw-camoufox-r6.json \
  --phase all --recreations 10 \
  --output infra/camoufox/evidence/acceptance-r6-2026-09-14.json
```

`rebind-worker.py` 要求新镜像的基础标签和完整基础层与旧产物绑定的精确镜像一致，并在新镜像中校验候选；它只产生候选，不能生成成功验收报告。不同的基础浏览器升级必须使用对应升级流程，不能借此跳过版本校验。

固定 X11 Firefox 家族的 Camoufox r6 完整产物、容器恢复、显式停止失败保留和即时存储恢复已通过，见 [R5A 验收](../sealskin/proxy-protocols-acceptance-2026-09-14.md)。r5 为已保留失败记录的中间候选，不能用于容器正常退出承诺。旧 Worker 不含此能力，不能沿用新版本的正常退出结论。

R4B 的 Work Wayland 候选已通过 10 项协议/身份单元检查、独立真实 Firefox 探测和完整控制器组合验收。实际 stop 在关闭对话框未处理时返回 503 并保留原 Worker/Home，取消后重试正常退出；`docker stop -t 30` 的 s6 顺序退出码为 0，原容器/Session resume 后即时 Cookie、localStorage、IndexedDB 均恢复。固定候选为 `sha256:ec848635e68db2d1c805fcf9972ef4586bcd86a9ed14b2075b0c5a40fbbc503f`，保留原 Work 镜像所有层，再增加退出和显示认证层；私有 App 候选只替换镜像字段，尚未部署。证据和版本边界见 [R4B 阶段验收](../sealskin/target-client-migration-acceptance-2026-09-15.md)。该范围不覆盖其他 compositor、浏览器或跨版本升级；r9 Camoufox 继续绑定此前已验收的退出层。

## X11键盘输入顺序（R6AW，验收中）

`install-keyboard-order.py`只接受固定Selkies输入源码摘要，为三个引擎的X11注入路径安装`keyboard_subprocess.py`。单次键盘子进程最多等待2秒；等待期间不处理后续按键，超时或取消先终止并回收进程，避免孤立进程稍后插入标点。失败文本不被标记为已原子输入，后续keyup仍可释放按键。Wayland和剪贴板流程保持原上游路径。

`build-keyboard-order.py`位于环境引擎目录，按精确基础镜像离线构建薄层；`test_keyboard_subprocess.py`覆盖慢启动、超时、取消、管道排空和退出失败，`check-keyboard-order.py --source <固定上游input_handler.py>`以实际原方法及延迟子进程对照错序/修复结果。真实客户端继续原30毫秒输入和精确断言；该修复不放宽QA门槛。新镜像必须重新完成组合验收，详见[DEV-148](../../docs/deviations/DEV-2026-10-03-148-dynamic-input-order.md)。
