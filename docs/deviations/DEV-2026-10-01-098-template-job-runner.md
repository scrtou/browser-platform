# DEV-098 · 模板作业执行器与当前目录不一致

状态：已解决并部署，关联 R6P。原问题：代码要求 --browser-template-id，但已安装的 environment-job.service 缺此参数；service 的 --catalog 仍指向 R6F 历史路径，当前 Adapter 读取 config/browser-platform/environment-catalog.json。旧完整作业即使生成，也不能按新三元兼容目录自动供选择。

处理：R6P 保留原队列/状态，在独立 QA 验证后对执行器启动参数和组合发布流程一起修复；生产待处理作业不删除或重置。新组合只在完整验收后登记兼容，部分发布可幂等继续，禁止绕过验收。敏感日志保存在 ignored runtime。

续作发现旧服务还固定 r9，而当前新 Camoufox 桌面修复为 r10。新独立模板从 r10 生成并重新验证两个组合，避免继续生成含旧系统 Firefox 入口的桌面；旧 r9 完整产物、已完成作业与生产绑定保持。已有 r9 隔离报告只作为历史/恢复路径证据，不代替最终 r10 生成验收。执行器同时固定完整源码依赖快照，不再运行可变工作区文件。

最终：冻结 20 文件执行器、明确浏览器模板 ID、当前双目录和 r10 精确镜像已安装。最终两组合完整验收、桌面/输入、最小 Adapter 实际目录解析和旧 spool/生产保持通过，见 [R6P 验收](../../infra/sealskin/r6p-template-separation-acceptance-2026-10-01.md)。
