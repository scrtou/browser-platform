# R7F 发布前候选静态验收 · 2026-09-23

后续范围：本报告保留发布前各轮事实；当前已发生的 Adapter/目录部署、Personal 绑定和备份、r10 恢复及 Work 新备份见 [2026-09-29 续跑验收](r7f-production-review-acceptance-2026-09-29.md)。下文“未部署/未绑定/未备份”不代表当前状态。

本记录覆盖 R7F 的**生产发布前准备**。截至 2026-09-27 尚未替换生产 Adapter/控制器、启用或启动 Work、停止 Personal、修改真实 Home/账号/Session 或 Trilium Core；为处理 DEV-069，已通过加密管理面新增精确授权的 Secret Store 版本和未绑定的不可变策略。

## 候选固定

- Git 基线：`ab6b1586549ebadae591a5a149d571eba7f56032`。
- 实际发布 payload 以显式文件清单固定，共 32 个代码/配置/测试脚本文件；纯文档、验收报告、runtime 和缓存不计入 payload。
- 私有清单：`infra/sealskin/runtime/r7f-prerelease-2026-09-23/candidate-payload.sha256`（运行目录被 Git 忽略）。
- 清单 SHA-256：`db535e22d789de19d2af424cfcc66e628a3d1f7996963c7f46fd9cfe67666cf5`。
- `infra/work-firefox-managed/__pycache__/` 已从工作区候选中移除；运行材料和缓存不进入候选清单。

## 静态与测试验证

| 检查 | 结果 |
| --- | --- |
| Adapter 固定 `golang:1.27-alpine`、无网络，`go test -count=1 ./...` | PASS |
| Relay 固定 Go 1.27；依赖先装入一次性 module cache，测试阶段无网络，`go test -count=1 ./...` | PASS |
| Adapter / Relay `go vet ./...` | PASS |
| Adapter / Relay `gofmt -l .` | PASS，无输出 |
| `git diff --check` | PASS |
| checks 镜像 + 挂入固定 Go 1.27，Adapter `profile/httpapi/access/control` race | PASS |
| 同一 checks/Go 组合，Relay 全包 race | PASS |
| 适用 lifecycle pytest（secure backup / coherence / legacy / runtime nodes / rollback） | 5 passed，117 skipped；跳过项需要 `age`，因此不声明完整备份回归通过 |

race 使用既有 checks 镜像并覆盖其默认 entrypoint；源码只读挂载，测试阶段无网络。一次性 Go/module-cache volume 均由脚本退出清理。

## 生产只读基线（第一轮）

- Adapter 服务 active，运行二进制 SHA-256 `fe4e13c4676afb8ab7b1f5cef17d6f0514a3a691942c1fe8c7dde1b481ca34fa`。
- 配置/状态/Profile 目录/账号表分别记录脱敏 SHA-256：`dafa9bf8…054ee` / `c8d2e728…a5a12` / `78f2f455…48726` / `92cf7655…b2426`。
- Personal：running，1 Worker、5 resources、1 Relay、1 Guard、2 networks。强制只读 probe 后 freshness=pass，但 proxy=`PROXY_UPSTREAM_UNKNOWN`，overall=unknown；本轮不能宣称 Personal 网络健康。
- Work：stopped，records/workers/orphans/resources/relays/guards/networks 全 0。当前目录/配置没有独立 `enabled` 布尔字段可作为本轮证据，因此不额外宣称 disabled。
- 只执行 inspect/health/probe 和文件摘要读取；没有生命周期写操作、服务重启或生产配置变更。

## 2026-09-27 补充复核

- 在固定 checks 镜像 `sha256:7de36814…` 中挂入固定 `age v1.2.1`，保持无网络、只读根和只读源码，对四个适用备份测试文件执行完整回归，最终结果为 **118 passed**。首次 117 passed / 1 failed 是一次性 `/tmp` 的 `noexec` 阻止测试夹具执行临时 fake Docker CLI；显式允许该一次性 tmpfs 执行后，未修改代码、测试或断言即全部通过。原表中的 5 passed / 117 skipped 保留为 2026-09-23 当时结果，本补充取代其“缺 `age` 未验证”的当前结论。
- 实时只读核对中，生产 Adapter 仍为 `fe4e13c4…`，Personal 与 Work 的资源计数未变。Personal 连续强制样本的代理项为 `PROXY_UPSTREAM_UNKNOWN` / `PROXY_PROBE_TIMEOUT`，其余运行与显示检查通过；宿主机访问探测站点为 200，策略冻结地址与 VPS 系统解析器返回的单地址一致，但宿主机和 Relay 网络到既有外部上游端点的 TCP 建连均连续超时，Relay 日志为脱敏 `UPSTREAM_UNREACHABLE`。Cloudflare `1.1.1.1` 与 Google `8.8.8.8` 随后均对代理主机名返回 `NXDOMAIN`，而控制域名查询为 `NOERROR`；系统解析结果可能来自私有解析或缓存，不能证明代理的公开 DNS 仍有效。
- 因 Personal 当前无法证明原受管理代理可达，本轮没有停止或重建 Personal，也没有生成匹配时点生产 Home 备份、切换 R7 组件或启动 Work。完整生产发布仍保持未通过。
- 用户侧解析得到的当前公开地址已经过两层验证：宿主机使用原有凭据完成 SOCKS5/CONNECT/TLS/HTTP 200；生产控制器使用新导入、仅授权 Personal 当前 Profile/Home/Application 的 Secret Store 版本执行草案探针，返回 `PROXY_PROBE_OK` 和 HTTP 200。随后追加不可变策略 `personal-camoufox-r9-socks5-r2`，摘要 `2ad6aa03…1fed`。Profile 仍绑定旧修订，原 generation、Home、journal 与 Guard 均未改变。

## 当前结论与未完成范围

发布前代码候选的 Go test/vet/gofmt/diff-check 和关键 race 已通过；精确候选文件清单已经固定。固定 checks 镜像挂入固定 `age v1.2.1` 后，四组备份回归最终 118 项全部通过。Personal 新代理草案及不可变策略已准备但未绑定；匹配时点生产恢复材料和实际发布仍未完成。

以下仍属于 R7F 未完成条件：生产维护前脱敏基线和匹配时点恢复材料、R7 Adapter/控制器/目录实际切换、Work 受管理公网与 fail-closed、Personal 保持、目标 Mac/Trilium 1280×800 真实视觉与交互验收。
