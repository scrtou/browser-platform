# DEV-2026-09-27-069 · Personal 代理私有解析与冻结地址漂移

[R7F 工作项](../work-items/R7F-2026-09-23-production-release.md) · [偏差索引](README.md)

状态：已解决（本次生产代理恢复、文件保持与 Mac 实际访问）。发现日期：2026-09-27，更新日期：2026-09-30。

## 预期

Personal 的受管理代理策略冻结一个经解析确认的公开 IPv4；Guard 只允许 Relay 到该地址和端口。发布维护前，新鲜上游探针应返回 `PROXY_OK`，停止后使用同一策略或已验证的新不可变修订健康重建。

## 实际事实

- 生产 generation 冻结地址与 VPS 系统解析器当前返回的单个地址一致，但宿主机和受控 Relay 网络到该地址均在 TCP 建连阶段连续超时；Personal 报告为 `PROXY_UPSTREAM_UNKNOWN` / `PROXY_PROBE_TIMEOUT`。
- Cloudflare `1.1.1.1` 与 Google `8.8.8.8` 均对代理主机名返回 `NXDOMAIN`，控制域名查询为 `NOERROR`。VPS 系统结果可能来自私有解析或缓存，不能证明公开记录正常。
- 用户在实际可用客户端的运营商解析器上得到另一个公开 IPv4。该地址不等于冻结地址或 VPS 系统解析结果；从 VPS 使用现有受管凭据访问该数值地址，SOCKS5 认证、到 `example.com:443` 的 CONNECT、TLS 和 HTTP 200 均通过。
- 2026-09-27 已经由生产控制器管理员加密接口导入一个新的 Secret Store 版本，只授权给 Personal 的既有 Profile/Home/Application；控制器隔离探针返回 `PROXY_PROBE_OK` 和 HTTP 200。随后追加不可变策略 `personal-camoufox-r9-socks5-r2`，摘要 `2ad6aa03…1fed`。Profile 仍绑定旧策略，运行中的 generation、Home 和 journal 均未切换。
- 后续启动复核发现该修订冻结的 `114.37.194.203` 已不可达；当前公开解析为 `114.37.227.46`，宿主机及普通 Docker egress 网络到新地址的 TCP/60011 可达，而旧地址超时。失败代次已通过正式 `stop-profile personal` 清理至 records/workers/resources/relays/guards/networks 全部为 0，Home 保留。
- 凭据、完整代理 URL 和私有地址证据不进入公开文档；用户已在会话中暴露凭据，发布完成后应轮换。

## 影响

当前 generation 的 Guard 正确拒绝向未冻结的新地址出站，不能热改规则或把浏览器临时接入 VPS 直连。直接停止 Personal 后仍绑定旧策略会无法健康重建，因此 R7F 的匹配时点备份和生产切换不能沿用旧修订继续。

## 处理决定

1. 保留当前 generation、Home、journal 和旧不可变策略，不热改、不删除占用。
2. 已通过现有管理员加密接口把同一凭据导入 Secret Store 的新版本，只授予 Personal 的精确 Profile/Home/Application，并对用户侧解析出的数值地址完成隔离探针。
3. 已生成新的不可变 Personal policy；只有在正常停止且 records/workers/resources 为 0、完成匹配时点加密备份后，才更新应用/Profile 绑定并创建新 generation。
4. 新 generation 必须取得 `PROXY_OK`，并复核 Guard/Relay、无直连、Home 数据和入口；失败时保留 Home 与旧材料，不放宽 Guard。R7 目录中把本次地址保存为明确修订，不把已公开 `NXDOMAIN` 的主机名重新解析成旧地址。

## 验证与收尾条件

- 新 Secret Store 引用及控制器侧探针通过，返回材料不含凭据。
- Personal 停止、备份、绑定、重建和新鲜健康均按 R7F 留证；旧策略和回退材料保留。
- 更新 R7F、验收、进度、计划和代理目录适用范围后，将本记录标为已解决；若供应方无法维持新地址，则保持待外部条件。

## 2026-09-30 续跑

Personal 原 `personal-tw-socks` r1 的当前探针仍超时；已存在、明确授权 Personal 的域名代理 `tw` r1 在精确 grant 下通过 SOCKS5/TLS/HTTPS，见 [本轮验收](../../infra/sealskin/r7f-personal-recovery-acceptance-2026-09-30.md)。完成新停止时点 1,204 条目加密 create/verify/独立 restore、1,035 个 Home 文件一致性核对后，用户经管理页完成绑定；14:55 UTC Personal revision 10、独立 `personal-tw-r1` 与完整 App 只改 policy 核对通过，原 Home/应用/镜像保留。当前仍 stopped/0 resources，待新代次 PROXY_OK 及数据验收后再关闭本记录。当前域名探针成功不等于 R7G 动态切换已部署，也不保证供应方后续地址不漂移。

随后用户打开 Personal，14:58 UTC revision 12 的新代次 `overall=healthy`、`PROXY_OK`、浏览器/显示/新鲜度均通过；Worker 实际域名/TLS/HTTPS 与有效四类绕过拒绝通过。此前停止状态为绑定时点事实，当前已恢复运行。浏览器对原有数据的读取和目标客户端尚待确认，偏差保留部分处理；未来域名端点漂移的自动热切换仍由 R7G 承接。

最终用户反馈：当前为 Mac 浏览器，Personal/Work 公网页面访问正常；原有书签/登录确认项为“不适用”。本项停止/备份/授权绑定/新代次健康/实际入口及文件保留均已留证，原数据确认如实记为不适用，故本次恢复问题关闭。旧失败策略保留，不承诺外部域名永久稳定；后续端点自动轮换仍由未部署的 R7G 承接，R7F 的 Trilium、完整管理 UI 和 Work 三类存储/回退条件未因本记录关闭而完成。
