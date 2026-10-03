# DEV-078 · Work 运行探针的 DNS 拒绝证据不足

[R7F 工作项](../work-items/R7F-2026-09-23-production-release.md) · [偏差索引](README.md)

状态：已解决（私有探针与共享 QA 工具均已验证）。发现日期：2026-09-30。

## 预期与事实

Work 生产运行验收须区分受管 Relay 的域名 HTTPS 成功与 Worker 绕过出口的请求被拒绝。12:47 UTC 的私有 `check-work-live.py` 已验证精确镜像、Guard 归属、健康和 Relay HTTPS；但两个直接 UDP DNS 检查只发送一个零字节，并把任意 `OSError`（包括超时）都当作 blocked。无效报文可能被解析器丢弃，因此原结果中的 DNS blocked 布尔值不足以单独证明网络拒绝。

## 处理决定与验证

在同一 R7F 内修正验收工具：发送完整有效 DNS 查询，分别记录 connect/send/receive 阶段及错误类别，只有明确本地拒绝才记为拒绝；单纯超时保持未定。保留原结果，另存有界只读复测证据。不启停生产浏览器、不改 Home 或防火墙，不以降低验收条件替代复测。

补测后同步本记录、偏差索引、迁移验收、进度、计划和工作项；浏览器 GUI、数据恢复及故障注入仍按原范围分别验收。

## 补测结果

12:51:49 UTC：两个完整的 29 字节 `example.com A` 查询分别在 Docker DNS send 阶段得到 `EPERM`、公网 DNS connect 阶段得到 `ENETUNREACH`。前者 Guard output drop 计数增加 1，后者在本地路由阶段即拒绝、计数未增加；两个检查前后的有效 nft 规则摘要均不变。最终分类只接受明确本地权限/路由拒绝，超时不计通过。

首轮观察命令使用了当前 Guard 不具备的 `--inspect`，改为直接只读查询 nft；临时表名错误和最初要求错误必须发生在 receive 阶段的 INCOMPLETE 结果均保留。后者不符合实际内核在 connect/send 即拒绝的行为，按既定“明确本地拒绝”条件修正分类后通过，没有放宽网络验收为超时成功。

证据在忽略目录 `infra/sealskin/runtime/r7f-migration-20260930/`：原始 `work-live-result.json`、补测工具 `check-work-dns-v2.py`、首轮 `work-dns-verified-result.json`、最终 `work-dns-verified-final-result.json` 及命令失败材料。没有改产品代码、部署、Home 或网络规则。范围见 [9 月 30 日验收](../../infra/sealskin/r7f-legacy-migration-acceptance-2026-09-30.md)。

## 共享 QA 工具续修

后续 R7F 恢复/回退准备发现 `infra/sealskin/checks/check-work-direct.py:raw_bypass` 仍有相同单字节 DNS 与宽泛异常分类。本轮把有效请求与明确拒绝规则落实到共享探针，覆盖超时不能通过、有效 DNS 报文和真正连通应失败的检查，再用于当前发布组合的独立故障/恢复验收。此前 R7B 的原结果保持历史范围，不改写为已使用新探针。

共享修正已完成：`worker-bypass.py` 构造有效 DNS 查询并细分 connect/send/receive 结果，仅明确本地权限/路由拒绝计通过；`check-work-direct.py` 调用此探针。3 项回归及当前线上组合的独立正常/网关故障运行检查均通过，干净复跑与 QA 清理完成，详见 [恢复与回退验收](../../infra/sealskin/r7f-work-recovery-acceptance-2026-09-30.md)。生产规则和镜像未改，超时仍保持未定。
