# DEV-066 · 网络 QA 清理器只接受完整矩阵证据名

状态：已解决（清理器修复与 R7B 实际清理通过）。日期：2026-09-21。
关联：[R7B](../work-items/R7B-2026-09-21-managed-work-egress.md)。

R7B 的独立 QA 复用网络控制器夹具，但执行的是面向 Work Firefox/Wayland 的聚焦 DIRECT 验收，成功摘要位于独立 attempt 目录。既有 `cleanup-network-qa.py` 虽已支持“浏览器专用 QA 不启动 Adapter”，却仍硬编码要求 `qa/live-results.json` 存在；该文件名属于完整网络矩阵运行，R7B 没有执行也不应伪造。

决定：清理器新增可选 `--completed-evidence`，默认仍保持旧路径；显式证据必须是 QA 根的同级证据树内、非符号链接、普通 JSON 文件且顶层 `result=PASS`。其余清理门槛不变：Session、generation 容器/网络、reservation 必须先归零，只接受精确 QA 标签、名称和挂载，控制器和 Docker 代理按记录身份停止，临时凭据删除。R7B 用第六轮成功摘要执行并复核后标为已解决。

最终结果：清理器接受第六轮 `PASS` 摘要并完成 generation resources、QA containers、QA networks 全部归零；控制器/代理停止，临时凭据、证书和显示材料删除。生产 Personal/Work 随后只读复核保持。
