# R6AW · 内置模板与24组合验收

状态：进行中，尚未部署。本记录不能作为1.0发行证明。工作项见[R6AW](../../docs/work-items/R6AW-2026-10-02-protected-builtins.md)。

## 范围与历史v5输入（已被v6取代）

US/TW/JP/CN四个受保护通用指纹，自动/DPR随系统缩放和1920×1080/DPR1两个受保护显示；Camoufox152.0、Chromix154.0.8037.57、Firefox155.0.1共24个真实组合。仅这24个安装组合标为内置，普通后续自定义任务不自动取得内置属性。

候选Adapter为 f0526e3a6950b28528055aea5d9e24bd36d049709c773009c26269883f5d232d。190文件v5候选在独立机逐文件验证；精确源码审阅提交 ca94e448c59b0b5dc731d74c523c4ede0c80b677，不包含尚待真实包验证的后续打包工具。测试运行使用冻结源码，工作树变化不改变正在执行的任务。

| 引擎 | R6AW精确镜像 |
| --- | --- |
| Camoufox | sha256:533e422d60de428a859d1ef76c0a45eaaa9bc18b4385483cd4bda679746738d1 |
| Chromix | sha256:6079ee94bcdbb3c5e2ed6ae303b9e5d35233d814073c98e1443cf26c44f927c9 |
| Firefox | sha256:cd56ef1b359df329f7e101e6211d1a269640a945a8440abf986363212c4c8a32 |

12份来源/引擎设备缓存（16文件）先由正常生成器冻结，两机校验同一清单后复用。缓存生成不等于accepted。独立Debian12机器承担12个自动组合，本机独立QA承担12个固定组合；受测Worker保持1.5CPU/1536MiB，自动显示的合成客户端另用2CPU/3GiB、1GiB临时目录。

## v6键盘运行时修订（验收中）

2026-10-03 01:24 UTC：DEV-148已在真实浏览器故障注入中复现；有界等待/终止回收修复及6项进程检查、固定上游方法对照通过。三引擎修订镜像和195文件v6候选已两机核对，源码提交review/r6aw-matrix-v6的6bffe240452d8b0e1016ee7844d016cb702bdc92。新矩阵已启动固定部分，自动部分待真实客户端延迟对照通过后启动。v5的16项accepted及4份桌面报告仅保留为旧镜像证据，不能计入新镜像的24项。尚未部署。

| 引擎 | v6精确镜像 |
| --- | --- |
| camoufox-linux-v152 | sha256:be475a9fbe6cfc9c1768c95ebd8f8d83da22b05297498abb7c82f70e6ceea2c1 |
| chromix-linux-154 | sha256:cf0e51426b6f59769af7486f9e09340387ed69b3ccc33d5a47c792280bdcc730 |
| firefox-linux-155 | sha256:d9c8c8737dc19f110eac9b7b3676faf01eac2a6925ae3c5aa27f696ad83fca2e |

## 历史检查点与前置证据

2026-10-03 01:10 UTC：16/24原完整报告accepted（固定12项、自动4项），固定Camoufox的4份正常桌面补验全部通过。TW自动Chromix保留1份输入乱序failed，自动驱动已停止；见DEV-148。尚无24组合完成结论。

已通过的前置检查包括候选Go test/vet、内置与删除并发/race、11项Python来源和17项作业检查、4项初始文档就绪检查；实际客户端旧JS的8项回归已复现，新JS的12项尺寸换算场景通过。完整矩阵不重复利用旧镜像的accepted报告。不完整矩阵已实测拒绝导出，未创建输出目录。

生产425个保护文件摘要保持；R6AV零账号/零可见浏览器与待初始化入口没有改变。已通过且无任何容器挂载的合成QA Home可按磁盘阈值清理，报告/日志和清理清单保留；失败Home、旧失败矩阵及R6AU真实离线恢复根不清理。

## 待完成的门槛

- 24份完整报告：每Home十次重建、两个独立Home、真实观察、存储及离线恢复；自动显示还须通过实际Selkies尺寸/重连/缩放/截图/输入。
- 固定Camoufox保留历史无头完整报告，并另有四份同产物正常桌面完整报告，验证显示认证、输入和离线恢复；不以无头accepted代替。
- 真实包导出与来源/缓存/镜像/兼容关联校验；重算摘要后的混配、缺失桌面报告、已有冲突和重复目标目录拒绝；24个实际新建可选项及删除保护。
- 保留旧删除标记的安装目录复核、受控部署、实际进程/就绪/待初始化页面及旧数据保护、异机完整材料留存。
- 最终文档、偏差收尾、工作项/计划/验收索引及Git提交。

相关偏差：[DEV-142](../../docs/deviations/DEV-2026-10-02-142-remote-qa-runtime-user.md)、[143](../../docs/deviations/DEV-2026-10-02-143-remote-reconnect-input.md)、[144](../../docs/deviations/DEV-2026-10-02-144-bidi-initial-document-readiness.md)、[145](../../docs/deviations/DEV-2026-10-02-145-client-dpr-resolution-clamp.md)、[146](../../docs/deviations/DEV-2026-10-02-146-builtin-package-binding.md)、[147](../../docs/deviations/DEV-2026-10-02-147-fixed-camoufox-desktop-evidence.md)、[148](../../docs/deviations/DEV-2026-10-03-148-dynamic-input-order.md)。

私有证据：本机 infra/sealskin/runtime/r6aw-protected-builtins-20261002/，独立机 /srv/r6aw-protected-builtins-20261002/；实时检查点为前者的 live-matrix.json。此前薄镜像传输依赖异机已有精确基础层，不算冷导入；完整三镜像归档已保存在独立机（2,145,164,634字节）；初版校验器混淆OCI索引与配置摘要，修正后96个文件/93个OCI引用/77个Docker层摘要和关联检查通过；仍未宣称冷导入通过，且该归档对应v5。供应商自然动态漂移继续未测，静态代理恢复不替代该项。

2026-10-03 02:00 UTC检查点：v6已9/24组合accepted、1/4固定Camoufox桌面补验通过，零新增失败。此前v5成功/失败记录保持。v6完整三镜像归档及逐blob/OCI引用检查已通过，独立空Docker存储冷导入正在执行；尚未部署。

2026-10-03 02:34 UTC检查点：v6已13/24组合accepted、4/4固定Camoufox桌面补验通过。v6完整三镜像已从完整归档冷导入空Docker存储，三镜像内部键盘补丁及异机原停止容器保持检查通过。DEV-149独立关闭诊断通过但新完整Chromix任务仍排队；US自动Firefox首次存储探针超时另见[DEV-150](../../docs/deviations/DEV-2026-10-03-150-firefox-storage-probe-timeout.md)，零观察failed保留。本机JP/CN自动部分已启动。尚无24组合完成/部署结论。

2026-10-03 02:58 UTC：v6为17/24 accepted，四份桌面补验保持通过。DEV-150在独立机复现Firefox首次IndexedDB建库超时，较长诊断只说明最终可读写，不计accepted；正式条件保持，US/TW Firefox两项由本机隔离QA接续。最终五份分片仍核对24个唯一组合。DEV-151的派生产物ID目录假设已修复，16个实际组合的32份文件绑定及路径混配/父目录拒绝通过；未部署。
