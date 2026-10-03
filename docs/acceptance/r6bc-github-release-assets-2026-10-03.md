# R6BC · GitHub发布安装包验收

日期：2026-10-03。结论：PASS；[工作项](../work-items/R6BC-2026-10-03-github-release-assets.md)约定的安装材料发布与获取迁移完成。

基线：`a961ba5`；固定v1.0标签保持 `d21ca802f5f2e6d54841095f8ec1cf52cf07fd56`，已推送。公开[Release v1.0](https://github.com/scrtou/browser-platform/releases/tag/v1.0)，ID `402636413`；五个附件均为uploaded，发布前核对GitHub记录的大小及SHA-256。

| 附件 | Asset ID | 字节 | SHA-256 |
| --- | --- | --- | --- |
| `browser-platform-1.0-linux-amd64-v4.tar.gz` | 608304480 | 161372631 | `9d7cff919865dfbca8c30feba294e06163e8bbe8ba44c9c7c7682b2ecfb827ce` |
| `controller-managed-startup-image.tar.gz` | 608304659 | 95798408 | `e33bd7c59e5402597006534fb2250b3c883f2cc8c4be041afdeb0f9f983798d1` |
| `v1-exact-images.tar.gz.part-01` | 608319687 | 1992294400 | `e59798ba026caa2bb950c8879ecb9b3602922d797c1f59ac5cde260cafa42228` |
| `v1-exact-images.tar.gz.part-02` | 608345131 | 295326624 | `e9f87cd4328db76ffffbd664a98522e208a86b43f59672c5ff378cc3bdd0c63c` |
| `SHA256SUMS` | 608349816 | 498 | `4f733754293c1572d4b52b7e66792892701528998be950fa781be803e40d6fa8` |

验证结果：独立机三个完整原包摘要再次匹配原发行记录。基础包超过GitHub单附件限制，按1900 MiB分卷；上传流SHA-256与GitHub附件digest逐项一致。发布后从无认证公开下载URL完整流式回读五个附件，大小和摘要全部匹配；两卷按01→02输入同一SHA-256，得到 `3596963339544e6b5705a56d0fe0f62f552dd00c41c45743000469b8ac885329`，与原基础镜像完全相同。未在空间不足的开发机落盘大包。

过程记录：独立机初次完整摘要核对180秒超时，600秒重试通过。最初通过SSH转发基础第一卷，链路缓慢，主动停止并删除本任务草稿中的未完成附件；改为独立机直传，两个已通过附件保留。直传两卷和清单均一次成功。认证通过加密SSH标准输入传入上传进程，仅在内存用于GitHub HTTPS，不写远端文件；本地临时askpass helper已移除。上传进程结束，未删除原发行材料或业务备份。

文档核对：部署指南以Release为获取入口，说明五附件下载、分卷检查、合并和完整检查、临时容量与当前主分支安装器；发行记录、文档/验收/工作项索引、进度和路线图同步。Markdown链接/锚点与 `git diff --check` 检查通过。

证据保存在被忽略的 `infra/sealskin/runtime/r6bc-github-assets-20261003/`：`upload-state.json`、`public-verification.json`、`SHA256SUMS`与传输日志。公开文档不包含认证材料。

范围与恢复：此项只发布原安装包，源码/程序/镜像内容与生产运行未变；需要撤回时按Release ID管理本次附件，原包及标签保留。无需独立机仅指安装取包；未执行机器退役、真实业务灾备迁移或R6BA新入口整机/跨用户/TLS复测，后续验证仍归原计划。设计/规格和组件接口没有变化，无新增设计偏差。
