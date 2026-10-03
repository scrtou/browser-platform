# DEV-079 · 显示模板仍使用底层实现名称

[R7F 工作项](../work-items/R7F-2026-09-23-production-release.md) · [偏差索引](README.md)

状态：已解决（展示目录修正及实际 QA 通过）。发现日期：2026-09-30。

## 预期与实测

[R7 方案](../browser-workspace-plan.md)要求显示模板采用“固定指纹”等效果名称，X11/Wayland 与 Selkies 留在高级详情。当前生产兼容目录唯一 accepted 显示模板的 label 为 `X11 / Selkies / 1920×1080`；`manage.go:templateChoices` 直接拼接该 label 与 screen，真实 1280×800 Chromium 截图确认下拉框仍显示底层名称，旁边帮助文字却称底层信息只在高级详情显示。

9 个页面/尺寸组合的几何、选择和键盘检查通过，仅证明布局及原生控件可用，不能把名称语义偏差记为通过。

## 处理决定

修复 operator-owned 目录的展示元数据：先将 QA 副本的 label 改为“固定指纹”并复验，再以完整旧值比较和原子替换修正生产同一字段，保存匹配备份。`id/revision/screen/scaling/display_server/transport`、兼容组合、artifact、Profile/模板绑定和运行代次全部保持；不增加尚未验收的“清晰适配”选项。

代码核对：`FileTemplateCatalog.Read` 每次读取目录，label 只用于摘要和表单选项；兼容与绑定使用固定 ID/revision/设备/缩放字段。本次不改二进制、网络、浏览器状态或 Home，无需服务重启。目录修改后核对精确字段差异、生产实例身份和健康；Mac/Trilium 实机确认仍单独记录。

私有截图、目录前后快照和核对结果保存在忽略目录 `infra/sealskin/runtime/r7f-client-ui-20260930/`。

## 验证与收尾

QA 修正后 Chromium 151 在三种宽度、三个页面共 9 组重新通过，显示选项为“固定指纹 · 1920x1080@1”。生产目录原子替换前核对完整旧值，仅 label 改变；匹配备份及差异回执保留。15:45 UTC 三个生产浏览器原身份保持且新鲜 healthy，无重启，QA 已清理。详见 [客户端页面验收](../../infra/sealskin/r7f-client-ui-acceptance-2026-09-30.md)。名称契约已恢复；Mac/Trilium 全矩阵仍归 R7F 待验证，不扩展本偏差结论。
