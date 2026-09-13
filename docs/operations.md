# 运维、开机与恢复

[文档导航](README.md) · [当前进度](progress.md) · [开发计划](roadmap.md) · [Trilium 使用](trilium-client.md)

本页提供日常检查和恢复的阅读入口。具体构建、安装、参数与回滚命令保留在组件 README；当前开机完成情况统一见 [开机与重启恢复进度](progress.md#startup)。

## 日常只读检查

以下命令适用于当前主机，从仓库根目录执行。其他部署需替换用户、二进制和配置路径。

```bash
systemctl --user is-active profile-adapter.service
systemctl --user is-enabled profile-adapter.service
loginctl show-user sshUser -p Linger
docker ps --format '{{.Names}}\t{{.Status}}'
curl -fsS http://127.0.0.1:9100/healthz
curl -fsS http://127.0.0.1:9100/readyz
~/.local/lib/browser-platform/profile-adapter \
  -config infra/sealskin/adapter-config.json -inspect-profile personal
~/.local/lib/browser-platform/profile-adapter \
  -config infra/sealskin/adapter-config.json -inspect-profile work
```

`healthz` 检查 Adapter 进程，`readyz` 发起 SealSkin 加密会话列表请求，`inspect` 查看绑定与实际资源。三者都不能替代浏览器页面或实时代理健康检查；`network_phase` 是持久化操作阶段。

检查结果记录时间、发布版本和适用 Profile。避免把完整 Docker inspect、私有配置或原始授权响应贴入文档；它们可能包含不应公开的运行信息。

## 启动与开机

| 需要执行的工作 | 操作入口 |
| --- | --- |
| 新环境部署 SealSkin、Caddy 与证书 | [SealSkin 部署](../infra/sealskin/README.md) |
| 构建或安装生命周期补丁 | [补丁构建与安装](../infra/sealskin/lifecycle/README.md#构建与安装) |
| 安装 Adapter 用户服务 | [Profile 准备与服务安装](../infra/sealskin/README.md#profile-poc-准备) |
| 配置受管理 Personal 网络 | [generation 策略](../infra/sealskin/lifecycle/README.md#按-generation-分配代理与网络) |
| 保留的静态 Relay / 独立 Camoufox | [Relay](../relay/README.md)、[Camoufox 应用](../infra/camoufox/README.md#独立-sealskin-应用) |

当前生产自动开机编排尚未完成，不能把安装命令当作已经验收的整机恢复脚本。启用 Adapter 用户服务与允许它在退出登录/开机后运行是两件事；`Linger=no` 的处理和正式重启验收属于 [R2](roadmap.md#r2)。

受管理 Personal 的恢复流程必须先确认状态与资源归属，再准备 Guard 规则、Relay 和探测，最后启动 Worker。规则或探测失败时保留阻断；不得先让浏览器联网后补规则。独立 daemon 验证所用的显式重启步骤不应直接应用到仍有存活 Worker 的生产 Guard。

## 常见情况与恢复入口

| 现象 | 处理 |
| --- | --- |
| 刷新后看到黑框，桌面仍有响应 | 浏览器可能已退出；远程桌面空白处右键 → **FireFox**。详见 [误关恢复](trilium-client.md#关闭远程-firefox-后出现黑框) |
| 需要找回原标签页 | Firefox 的 **History → Restore Previous Session**；是否恢复完整以实际结果为准 |
| 页面还在但网站无法访问 | 先查看对应 Profile 资源与 Relay/上游；保持原网络策略，不切换到 VPS 直连 |
| Guard 已丢失或停止 | 经 Profile stop 清理原 generation，确认资源消失后新建；不单独重启 Guard 接管旧 Worker |
| `unknown`、停止失败或残留网络 | 使用本机 inspect，再按实际停止意图执行 stop/reconcile；保留 journal 与 Home，不能手动删除占用解锁 |
| 控制服务重建后显示失联 | 核对旧控制器是否退出、地址/归属/配置是否冲突；按 [生命周期恢复](../infra/sealskin/lifecycle/README.md#身份与恢复) 处理，不强接异属资源 |
| Trilium 复制粘贴或上传不符合预期 | 按 [客户端指南](trilium-client.md) 区分 ⌘ 与 Control、侧栏与原生事件、文字与图片 |

## 停止、对账与数据保护

通过正在运行的 Adapter 的本机 `0600` socket 操作，命令见 [Adapter 停止与恢复](../adapter/README.md#停止与未知状态恢复)。`inspect` 只读；`reconcile` 可能继续已保存的停止；`stop` 明确停止当前代次，因此操作前要核对 Profile。

停止成功要求 Session 记录、Worker、Guard、Relay、网络和占用全部清理到预期状态；Home 数据继续保留。受管理模式禁止 `reset-profile`，不能以删除 journal 或切换旧配置代替实际资源确认。

Home 删除接口的活跃挂载保护尚未实现。备份、删除或迁移 Home 前，需要确认浏览器与占用已经退出；日常重开浏览器和刷新页面都不需要删除 Home。

## 备份、升级与回滚

备份范围包括 Home、Adapter 配置/状态、SealSkin 必需状态、固定镜像、环境产物、成功验收报告以及恢复所需密钥。含浏览器数据或密钥的材料单独加密保存；公开仓库只记录脱敏清单。备份 Home 前停止对应浏览器，不能只复制运行中 SQLite 的主文件。

Camoufox 的现有离线恢复证据使用 QA Home 和同一固定版本。真实 Home 备份恢复、跨引擎迁移和跨版本回退依照 [R2](roadmap.md#r2)、[R4](roadmap.md#r4)、[R6](roadmap.md#r6) 分别验收。

当前控制服务的安装、旧 payload 位置和回滚限制见 [生命周期安装与回滚](../infra/sealskin/lifecycle/README.md#构建与安装)，精确发布摘要见 [v2 发布记录](../infra/sealskin/network-isolation-acceptance-2026-09-13.md#发布身份)。若新版本已创建受管理代次，应先由对应版本确认其资源清空，再评估回退；不能恢复旧 journal 强行释放 Home。

## 运维后如何更新文档

先保留脱敏验收记录，再更新 [验收索引](acceptance/README.md) 与 [开发进度](progress.md)。操作步骤变化时修改相应组件 README；范围或优先级变化时更新 [开发计划](roadmap.md)。不要在历史报告中覆盖旧版本的结果。
