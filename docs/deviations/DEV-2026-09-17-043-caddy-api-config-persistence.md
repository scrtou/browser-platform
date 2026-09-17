# DEV-2026-09-17-043 · Caddy API 发布配置缺少重启持久化

状态：已解决（正式 Caddy/Docker/VPS 重启均通过）。发现日期：2026-09-17。关联工作项：[R4B](../work-items/R4B-2026-09-14-target-client-migration.md)。

## 设计预期

[入口登录说明](../../infra/sealskin/entry-auth/README.md#发布候选与维护顺序)要求两个公开域名在发布后都经 Adapter 登录与 Session 授权网关；[R2](../work-items/R2-2026-09-13-boot-recovery.md)要求服务和 VPS 重启后恢复的仍是同一安全边界。R4B 维护包以 Caddy 本机管理 API 原子加载维护/候选 JSON，失败时保留 503。

## 实际事实与证据

- 主机 `caddy.service` 的 `ExecStart` 为 `caddy run --config /etc/caddy/Caddyfile`，单元注释明确说明 API 改动在服务重启后会被该磁盘文件覆盖；未使用 `--resume`。
- 运行态 Caddy JSON 已包含当前维护路由，公开 Work 返回 200、Personal 返回 503；R4B 候选 JSON 会把两个域名都转发到 Adapter。
- `/etc/caddy/Caddyfile` 仍包含旧的 `mysession` 直达控制器路由。若只加载候选 JSON，Caddy/主机重启会恢复旧路由，绕过入口授权，故生产切换和 R2 重启不能判定通过。
- 脱敏检查记录写入 R4B 私有发布/部署证据；本记录不保存账号、Cookie、Session URL 或私钥。

## 影响与处理决定

- 影响：运行时切换可以暂时生效，但重启后入口认证边界不持久，阻止 R4B 上线和 R2 重启验收。
- 处理方式：修复实现。发布包增加 Caddy systemd drop-in，启动时使用 `--resume` 优先恢复 API autosave，reload 读取同一 autosave JSON；主机安装器原子安装并 `daemon-reload`，不在前置阶段重启 Caddy。
- 现有 R4B 生产维护授权覆盖该必要持久化修复；主机文件仍由管理员运行已记录的前置安装命令。
- 在主机前置复核、候选加载、公开认证检查和正式 Caddy/Docker/VPS 重启通过前，R4B/R2 对应条件保持未完成。

## 实施、验证与文档同步

| 材料 | 更新 / 结果 |
| --- | --- |
| 实现 | `prepare-release.py` 生成 `caddy-api-resume.conf`；主机安装器安装并核对 `ExecStart`/`ExecReload` |
| 验收与证据 | `release-ready-2` 39 文件独立复核、主机安装和生产候选加载通过；14:01 UTC Caddy 与 14:05 UTC Docker 正式重启后候选/公网边界保持，两 Profile 同代次恢复并通过健康/认证；14:16 UTC VPS 重启后新 boot 的 Caddy 以 `--resume` 启动，`recovered-live-check`（14:21 UTC）与 `live-check-3`（15:15 UTC）核对运行 JSON 与候选精确一致、公网/本机边界 200/303/303/404 及精确 Session 无 Cookie 401 |
| 设计 / 规格 / 组件说明 | 入口登录说明补充 API autosave 的重启契约 |
| 进度 / 计划 / 工作项 | 已同步：R4B 收尾、R2 正式重启条件完成、进度/计划/索引更新 |

## 最终复核

主机 drop-in 已安装，`ExecStart` 使用 `--resume`，`ExecReload` 读取 autosave；生产候选已通过 API 加载。2026-09-17 14:01 UTC 执行正式 `caddy.service` 重启，新 Invocation 启动后运行 JSON 仍与候选精确一致；登录页 200、两个固定入口未登录 303、Session 根 404、精确 Session 无 Cookie 401，Work/Personal 运行数量、镜像、能力、Home 和秘密权限均通过 `after-caddy-restart-1` 复核。14:05 UTC Docker 正式重启后 Caddy 边界继续保持，四个 Profile 容器以同 ID/镜像休眠并由 Adapter 按序恢复，两 Profile healthy、Personal `PROXY_OK`、认证 Session 200。14:16 UTC 正式 VPS 重启后，新 boot 的 `caddy.service` Invocation 以 `--resume` 启动并恢复 autosave，14:21 UTC 与 15:15 UTC 两次只读复核均确认运行 JSON 与候选精确一致、旧磁盘直达路由未恢复、两个域名继续经 Adapter 网关；偏差已解决。
