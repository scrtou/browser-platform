# DEV-029 · 恢复等待一致性就绪时误报 Worker 停止

状态：已解决（候选 6 配套 Adapter 与实际恢复；未部署）。工作项：[R5C3](../work-items/R5C3-2026-09-14-runtime-coherence.md)。

预期：恢复可以先恢复容器、再等待新的浏览器观测；未通过门槛不发放会话，并保留 Home/代次。操作结果应区分未就绪与已经确认停止，重试沿用原恢复操作或复核已恢复代次。

实测：候选 6 `resume-1/` 经正常 Adapter resume 后，控制器因新的观测尚未就绪返回 `COHERENCE_SESSION_NOT_READY`。三类容器已正常运行，后续后台观测为 DEGRADED / allowed=true；Adapter 仍保留 unknown 绑定和恢复幂等键。私有控制接口对所有 ErrResumeFailed 使用“Worker remains stopped”文本，与实际状态不符；QA 工具又将合法的首次 503 当作整个恢复失败。原结果和 `core-regressions-1/` 部分结果保留，未伪造 PASS。

处理：不放宽严格门槛、不更改生命周期所有权。私有错误改为“尚未达到已验证的就绪状态，Home 保留”；一致性阻断单独给 503/Retry-After。QA 对正常 resume 接口的 503 作有界、10 秒间隔重试，最后必须获得接口成功、新鲜放行、原容器/Home/Session/operation/产物和 marker 保持。其他 HTTP 错误直接失败，超过次数仍失败。未验证时不把数据标成已就绪。

验证计划：控制错误分类与既有 Go/race/vet；只重建 QA Adapter、保留旧二进制及当前代次；新输出目录重验真实恢复并记录首次响应/重试次数。控制器固定候选 6 不变，文档记录初次待验证的时序，生产保持。

验证结果：更新后的 Adapter 在带编译器的固定 checks 镜像中通过完整 race/vet，见 `go-race-checks-5/`；Relay 源码与 `go-race-checks-3/` 的已通过输入逐一相同。初次本机 race 因无 C 编译器/CGO 未运行测试，记录在 `go-race-checks-4/`。QA 新二进制 SHA256 为 `31b3c57395ae054491ad7baaa14f1e2c57f40b01f3f607fb3c9cc7da58467b72`，替换前后原绑定和 Worker 保持；`candidate-6/adapter-build-3/recover-existing.json` 经正常 resume 成功接回首次 503 留下的实例。`resume-2/` 再次正常停止并恢复原三容器，接口首轮成功（1 次），新 nonce/开始时间及 Home marker 保持；没有把该轮写成实际触发了多次重试。
