# DEV-014 · 公开 DNS 验收工具未复核完整证据

状态：已解决（工具代码/隔离验证，非公开 DNS 验收）。关联 [R5C2](../work-items/R5C2-2026-09-14-approved-dns-ttl.md)。发现/解决日期：2026-09-14。

## 预期与事实

公开采样器即使只能给出 PARTIAL，也必须用实际委派、全部配置权威、批准解析器及到期前后缓存证据支撑其中的 `delegation_and_recursive_ttl=PASS`。缺失、错配或不自洽的材料应拒绝，不能依赖采样步骤曾经成功这一假设。

复核 `check-public-dns-ttl.py` 发现，`verify` 不检查保存的委派记录，也没有要求权威回答列表非空或覆盖配置中的全部端点；记录中的 DNS wire 没有重解析。缓存 TTL 只要求不大于首次 TTL，间隔十秒后仍返回原完整 TTL 也可被接受。关键校验使用 `assert`，优化执行会跳过这些检查。

14:08 UTC，以纯合成记录复现：空委派、空权威列表、空 DNS wire、缓存 TTL 不递减的三阶段材料，仍产生 `delegation_and_recursive_ttl=PASS`；总结果仍为 PARTIAL。没有发出 DNS 查询或修改 zone。私有证据在 `infra/sealskin/runtime/r5c2-dns-ttl-2026-09-14/public-tool-review/invalid-acceptance-before.json`、`invalid-empty-authority/` 及保存的修复前脚本。

此前公开工具只有 prepare/占位地址拒绝检查，没有真实公开 sample/verify PASS；已完成的控制端、引导 DNS、DIRECT 浏览器和生产保留证据不受此工具缺陷影响。原阶段检查点保留，不改写成已经完成公开验收。

## 处理

已修复验收工具：使用优化模式下仍执行的显式校验；证据版本 2 保存请求、回答和截断报文的 wire，离线重解析并核对事务/问题、记录元数据、端点/阶段/采样来源和完整路径。父区 NS、必要 glue、每个配置权威的地址/SOA/NS/A 均须留证；递归回答须声明 RA 且不是 AA。每个受控权威的 A TTL 须与计划相同，缓存 TTL 根据查询起止时间和一秒取整误差验证共同到期区间，提前采到“新地址”不能算到期后证据。失败采样保存在独立 `.failed.json`，同阶段重试或覆盖既有结果在查询前拒绝。

[36 项工具检查](../../infra/sealskin/checks/test_public_dns_ttl.py) 通过，包含回环 UDP/TCP 的 prepare → sample → verify、受损材料、总超时预算、普通与优化解释器、失败保留和不覆盖。另保存四组修复前后对照：缺失权威、TTL 不递减、记录与 wire 不符、权威端点错配，在旧脚本均获得子结果 PASS，在新脚本均被拒绝。有效夹具仍只返回 PARTIAL。

对照夹具共发出 48 次回环 UDP 和 3 次回环 TCP 交换，TTL 时钟及 DNS 内容为合成数据，没有公网查询、公开委派或真实递归缓存。证据为私有 `public-tool-review/tests-final.log`、`before-after-comparison.json` 和 `synthetic-roundtrip/`。首轮测试的 glue 名称缺少末尾点导致夹具序列化失败，记录在 `tests-1.log`；修正为完整域名后通过，保留该失败记录。14:23 UTC 四个生产容器及四份配置/绑定摘要保持，见 `production-preserved.json`。

已更新 [DNS 说明](../../infra/sealskin/lifecycle/bootstrap-dns.md)、[阶段报告](../../infra/sealskin/approved-dns-ttl-acceptance-2026-09-14.md)、工作项与索引、进度和计划。仍须取得独立 QA 子域及管理方式，完成真实委派、权威日志、批准递归来源和三个实际解析路径的同轮轮换/故障/恢复证据；本次不改变产品 DNS/代次契约或原发布条件。
