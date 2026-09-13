# 可靠停止与状态对账验收 — 2026-09-13

已完成独立故障验收并于 **2026-09-13 10:01 UTC** 上线。当前 Personal/Work 的 Session、Worker、浏览器、桌面和 Selkies 进程均保留；只重启了 Adapter 和 SealSkin 控制服务。自动空闲回收未启用。

## 固定版本

| 项目 | 值 |
| --- | --- |
| 上游 commit | `2b13a42483c1dc7d367d5c340437bdc8ecd84bb4` |
| 官方基础镜像 | `lscr.io/linuxserver/sealskin:0.3.2-ls58@sha256:d52c155eb78882b27c7780e77df335939d46cd06a514c9fa310039307542ee6a` |
| 当前发布 | `0.3.2-lifecycle-v1-682611bf1eb61d78` |
| 版本化镜像 | `browser-platform/sealskin:0.3.2-lifecycle-v1-682611bf1eb61d78` |
| 本机镜像 ID | `sha256:72e26bd040b09cd3b4eedabddbd12bc43469ffc2dfc200d2128705e5bdaada28` |
| Patch SHA-256 | `3daef0b5d98d86d4c26f393b6f83dacc0d77526ace0f4076da2133993b056495` |
| Adapter SHA-256 | `2eb0e0583da2e4fb658b0ad511148ba09215fa859eddd47bb71856aca1e7a084` |

安装器核对 9 个原始源码文件及修改后的 10 个文件，拒绝未知漂移。当前 SealSkin 容器保留原 ID/基础镜像身份，运行目录内安装与版本化镜像相同的 payload；Compose 已指向版本化镜像供后续重建。没有重建当前 SealSkin 容器或任何 Worker。

## 自动测试

| 验证 | 结果 |
| --- | --- |
| Python 3.14，上游 29 项 + 新增 30 项 | 59 项通过 |
| Go `go test ./...`、`go vet ./...` | 通过 |
| Go 全包 race、补充生命周期加密协议测试的 race | 通过；在带 C 编译器的检查镜像中运行 |
| Python lint / patch 应用校验 | 通过 |
| 安装器 check、重复 apply、漂移拒绝且无部分写入、rollback、重复 rollback、重新 apply | 通过 |

Python 测试包括 Docker 各状态、假成功、删除失败、停止意图/提交落盘失败、重启加载、部分 registry、应用记录已删除、标签归属、旧会话标记、跨用户路径、20 路 Home 竞争、启动/停止竞争、保留字段不可覆盖、Home 挂载不可遮挡及主网络选择。Python 3.14 测试出现第三方弃用与只读 pytest cache 警告，未影响结果。

## 独立真实容器验收

使用新账号 `lifecycle-qa`、新 Home `lifecycle-qa-home`、独立 SealSkin/Adapter 配置和密钥，端口仅绑定 `127.0.0.1:28100`、`28443`、`29100`。真实 Firefox 镜像固定为 `sha256:7e3dbebd9e730952648b8c902ce90fa72c0e2be3e786ab17026c38e0909b47f7`，只打开 `about:blank`。QA Docker socket 代理限制容器修改范围，未向生产 Session 注入任何故障。

| 场景 | 结果 |
| --- | --- |
| 20 路并发启动 | 一个有标签的真实 Worker，全部复用同一 Session |
| 运行第二个同 journal 的 Adapter | lifetime flock 拒绝 |
| Docker stop 返回假 204，容器仍 running | Adapter 返回待停止，保留记录/占用，入口拒绝重复启动 |
| Docker stop 返回 500，再次 stop | 保持 `stopping`，复用原 operation 和停止幂等键 |
| Docker inventory 返回 500 | 不将查询失败解释为空 Home，拒绝释放占用 |
| 待停止时 SIGKILL Adapter，解除故障后重启 | 启动对账自动继续停止，确认容器和记录均消失 |
| 重复停止两次 | 成功且无额外实例；Home sentinel 保留 |
| 同 Home 启动新 generation，再提交旧 generation 的停止 | 旧请求返回 409，新 Worker 保持运行 |
| 停 QA SealSkin 控制服务、删除该 QA 记录、重启服务 | Worker 容器启动时间不变；对账报告 orphan/unknown，入口不重复启动；明确 stop 按标签清理 |
| 无标签、无记录容器挂载 QA Home | 拒绝自动停止和重复启动，由 QA harness 精确清理 |
| 增加排序更靠前的第二网络，再重启控制服务 | 保留 Docker 主网络，新 Worker 仍在指定 QA 网络，完整故障回归通过 |

最终 Home sentinel SHA-256 为 `9b5834796fc34a4c5253f4ca66303d2dd1f64ddd7b4d9e58680dd8e51db0b4f0`，停止与重建期间保持一致。验收后清理测试容器、两个测试网络、socket 代理、临时账号密钥及 QA Home，只保留报告和无秘密测试日志。

## 上线与原会话保持

上线前备份 Adapter 二进制、配置和状态，记录四个原容器的 ID、StartedAt、镜像、Config/HostConfig 摘要、挂载和网络，以及两个 Worker 的关键进程 PID/start ticks。配置启用 `sealskin.lifecycle_enabled: true`，本机 control socket 为 `adapter-control.sock`，权限 `0600`。

第一轮上线的公网探针使用 Python 默认 User-Agent，被 Cloudflare 返回 403，脚本自动恢复原控制服务。核对原版本也对该 User-Agent 返回 403、浏览器 User-Agent 返回 200 后，修正探针并重新上线；没有修改 Cloudflare/Caddy 的安全配置。期间所有原容器、进程和绑定均与基线一致。

最终确认：

- Personal/Work 各有 1 条原 Session 记录、1 个原 Worker、0 个 orphan，明确对账均为 `running`。
- 本机入口 POST 均返回 303 并复用原 Session；HTTPS 授权跳转后的 Session 页面均为 200，URL 已移除 access token。
- 公网 Work、Personal 固定入口及 Session 根入口均返回 200，TLS 校验保持启用。
- 两个 Worker、SealSkin、Personal Relay 的 ID、StartedAt、镜像、配置、挂载和网络均未变化。
- Work 的 Selkies/labwc/Xwayland/Firefox PID 为 `123424/123465/123485/140975`；Personal 为 `320/382/396/387`，每个进程的 start ticks 均与部署前一致。
- 安装后的全部 10 个源码文件与最终 manifest 一致；Work 后续启动保留 `sealskin_default` 主网络，Personal 应用仍显式指定 Personal 内网。

现有两个 Worker 仍为原 Firefox Wayland。Personal 的代理 X11 与独立 Camoufox 配置未在此次切换到现有会话。

## 证据与边界

可审查实现见 [补丁与运维](lifecycle/README.md)、[Adapter](../../adapter/README.md)。本机私有证据目录为 `runtime/lifecycle-2026-09-13/`，主要文件为 `python-image-tests-v2.log`、`go-race.log`、`go-lifecycle-protocol-race.log`、`installer-checks.log`、`live-results-final.json`、`deployment-result.json`、`containers.before/after.json`、`processes.before/after.json` 和 `qa-cleanup.json`。密钥、完整授权 URL 和 Session token 不进入本记录或 Git。

本次完成可靠停止与对账，不代表完整网络故障矩阵或整体版本验收通过。动态 Relay/网络生命周期、自动空闲回收、浏览器进程健康、create 前完整持久化日志、Docker/VPS 重启窗口、活跃 Home 删除保护仍需继续实现。没有可见实例且未获 Session ID 的模糊启动保持未知；无标签且无记录的容器需要人工确认归属。
