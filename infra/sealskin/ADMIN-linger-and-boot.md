# 管理员参考：加密备份与开机持续运行

[运维与恢复](../../docs/operations.md) · [R2 工作项](../../docs/work-items/R2-2026-09-13-boot-recovery.md) · [R2A 准备验收](legacy-backup-acceptance-2026-09-15.md)

Adapter 目前以 **systemd 用户服务** `profile-adapter.service` 运行（`~/.config/systemd/user/`）。没有 linger 时，用户服务不具备退出全部登录后持续运行及开机自动启动的保证。2026-09-15 只读核对时主机为 Debian 12、`Linger=no`；R2C 后续已启用并确认 `Linger=yes`，2026-09-17 正式 VPS 重启证明用户管理器与 Adapter 在首个 SSH 登录前启动。用户于 2026-09-20 决定不再执行“退出全部登录”行为验证，因此下述方案与步骤只作运维参考，不是当前待办，也不能写成该场景已经通过。

## 维护前的具体准备

R2A 已生成 Personal/Work 的只读运行快照并核对所需身份文件，未停止生产、读取 Home 内容或生成真实 Home 备份。私有材料在 `infra/sealskin/runtime/r2a-legacy-backup-2026-09-15/production-snapshots-3/`，快照仅在同一 operation 和配置摘要下有效，维护前重新核对或生成新的文件。Personal 实际镜像与当前应用定义不同，Work 相同；两者均为旧的自动删除 Worker，停止后原 Session 不会复活。

按以下顺序准备维护，不把示例命令直接当作已完成的备份：

1. 确定要停止的 Profile、窗口及真实站点数据验证范围，暂停对应入口的新启动；保存当前镜像、控制 payload、Adapter/客户端发布材料及回退配置。保留最新 journal，不用准备时的旧 journal 覆盖后续操作。
2. 为 age v1.2.1 准备恢复 identity 和对应公开 recipient，私有 identity 单独受控保存；先用 QA 文件确认可解密。当前磁盘约 60.85 GiB、`/dev/shm` 约 2.89 GiB 可用（2026-09-15 采样），不是实际 Home 容量证明。验证/恢复需要足够 tmpfs 容纳完整未压缩归档，工具上限 8 GiB。
3. 旧生产按 [旧部署加密步骤](lifecycle/secret-store.md#旧部署的加密备份) 先快照，再用原配置经 Adapter 正常停止并确认清单全空，执行 `create-legacy`、`verify` 和新私有目录 `restore`。生产旧 Worker 不具备 r6/r7 的正常退出保证，窗口内须确认浏览器写入已保存；失败保留占用，不强杀。
4. 在隔离环境核对数据、服务身份、凭据和实际镜像，记录站点登录结果后才继续重启或迁移。旧恢复标记只作离线提示，不能把恢复包直接交给旧控制器启动；每个包只含目标 Home。
5. 若维护同时发布 R5D，采用 [匹配的发布与回退顺序](entry-auth/README.md#发布候选与维护顺序)，另核对 r7 应用/策略、账号、tmpfs、目标客户端及组合验收。已启用 Store/入口登录/密封状态的部署必须用完整 `create` 格式及最新撤销/账号恢复流程。

明文 `backup-home.py` / `control-state` 只保留历史 QA 范围，不能代替上述加密备份及恢复验证。真实 Home 演练（R2C）与整机重启（2026-09-17，见 R2 工作项）已执行；退出全部登录后的持续运行验证未执行，并已移出当前交付范围。

## 方案 A：启用 linger（改动最小，推荐）

```bash
sudo loginctl enable-linger sshUser
loginctl show-user sshUser -p Linger        # 期望 Linger=yes
```

启用后 `user@1000.service` 在开机时自动启动，进而拉起已 `enable` 的 `profile-adapter.service`。不需要修改仓库中的任何文件。

## 方案 B：改为系统服务

使用仓库提供的模板 [profile-adapter-system.service](profile-adapter-system.service)：

```bash
systemctl --user disable --now profile-adapter.service
sudo install -m 0644 infra/sealskin/profile-adapter-system.service /etc/systemd/system/profile-adapter.service
sudo systemctl daemon-reload
sudo systemctl enable --now profile-adapter.service
```

模板以部署账号运行（`User=sshUser`，附加 `docker` 组）、`After=docker.service`，并把可写路径限制在 `infra/sealskin`（状态文件与控制 socket 所在目录）。二进制、配置与密钥路径与用户服务相同；如部署路径不同需同步修改 `ReadWritePaths`、`ExecStart` 与 `EnvironmentFile`。切换前先确认没有未完成的停止操作（`-inspect-profile` 两个 Profile 均为 running 或 stopped）。

## 可选验证（若未来重新纳入范围）

1. `systemctl --user is-active profile-adapter.service`（方案 A）或 `systemctl is-active profile-adapter.service`（方案 B）。
2. 退出全部 SSH 会话后从另一台机器检查固定入口及 `https://mybrowser.azhen.de/browser/work/health`，确认 Adapter 仍可达并读取健康分项。当前旧部署直接检查；发布 R5D 后须先以有 Work 权限的账号登录，匿名登录跳转不是故障，HTTP 200 本身也不代表健康全项通过。重新登录主机后另用运维 socket `-health-profile work` 核对。
3. 重新登录后 `journalctl --user -u profile-adapter.service --since -1h`（或系统级 `journalctl -u`）没有重启记录。
4. 把命令输出（脱敏）记入 `docs/work-items/R2-2026-09-13-boot-recovery.md` 的验收表，并更新 `docs/progress.md#startup` 的“用户退出登录后持续运行”一行。

2026-09-17 VPS 重启中 `user@1000.service` 与 Adapter 在 14:16:44 UTC 启动，早于 14:16:55 UTC 的首个 SSH 登录；这证明开机自动启动，但不替代未执行的退出全部登录验证。

## 开机顺序（供整机重启维护窗口使用）

1. 先满足部署版本的宿主路径前置条件。当前旧部署没有 Store/显示 tmpfs；R5D 发布包提供显示根的 tmpfiles 规则及 Docker 顺序配置，采用 Secret Store 时还须按其组件说明补充凭据根和挂载。确保所需目录在主机 tmpfs 上、Docker 启动前创建且 UID/权限正确。显式 bind 禁止自动补建磁盘目录，缺目录时应保持失败；还需核对私钥、私有 TLS CA 和 DIRECT 地址证据等挂载。只启用 linger 不会完成这些配置。
2. `docker.service` 启动；`sealskin`、`profile-relay-personal` 容器为 `unless-stopped`，随 daemon 自动启动。采用新生命周期的 Worker、Guard、Relay 代次容器为 `restart=no`，保持停止。R4B 之前的旧 Work/Personal 自动删除容器不具备此保留能力；当前生产代次已为新生命周期容器，并于 2026-09-17 VPS 重启中按序恢复。
3. SealSkin API 启动时对每个受管理占用核对归属；在 R5D 先认证密封库并重建对应显示材料，恢复仍须精确匹配原代次。单独控制器恢复不代表已通过主机重启验证。
4. Adapter 启动：最多等待 `startup.control_wait_seconds`（默认 120 秒）直到 SealSkin 会话列表可读，然后逐 Profile 对账。识别为休眠代次时按序恢复：Relay → Guard（规则就绪）→ 控制器接回内网 → 一次性探测（代理 TLS 通过且直连阻断）→ Worker → 显示端点。任一步失败占用保留、绑定不放行；规则/探测失败时 Worker 不启动。运维可 `-resume-profile` 重试或按原生命周期 `-stop-profile` 清理。启用 coherence 的候选还须取得新鲜报告/门槛，恢复旧报告不能放行。
5. 无策略且仍保留完整休眠清单的代次：启动 Worker → 刷新会话记录中的地址 → 显示端点就绪。已经被自动删除的 Worker 不能走此恢复路径。
6. 验证两个 Profile 的 `-health-profile`、授权入口、Home/operation/Session、数据与网络证据；整个窗口不应出现 Worker 在 Guard 就绪前联网的时段。R5D 登录、显示与 coherence 组合及正式 VPS 重启分别记录；Debian 13 未执行且已移出当前范围，不能由 Debian 12 证据推定。

整机重启前保留本次加密备份的验证/恢复结果，以及容器、两个 Profile 的 `inspect`/`health` 基线。完整配置、原始 Docker inspect、密钥与 Session 响应只存私有目录；公开报告只写版本、摘要和分项结论。
