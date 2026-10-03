# DEV-152 · 1.0源码核对发现候选遗留临时维护入口

状态：已解决（R6AX范围）。关联[R6AX](../work-items/R6AX-2026-10-03-v1-release.md)。

R6AW精确候选与工作区逐文件比较发现，生产候选`cmd/profile-adapter/main.go`仍包含早期限定Profile名称的`maintenance-start`/`maintenance-stop`与`R6J1_PRIVATE_ERROR_FILE`诊断出口；当前工作区已经移除。其余差异为显示测试格式、R6AW目录验证辅助测试与候选独有的缩放目录QA文件。不能把工作区、冻结候选和已部署二进制默认为同一源码。

这些临时入口服务于旧维护授权，包含已删除的具体Profile名称，不属于1.0通用部署/运维接口。选择以工作区清理后的入口建立1.0候选，保留正常运行服务的stop/reconcile/inspect等运维命令和原生命周期保护。旧候选、二进制与维护证据不覆盖；新程序重新构建、完整Go回归、CLI边界与实际部署验证后才可取代旧版本。不恢复已由用户/前序工作移除的临时入口。

私有源比较见R6AX根`source-preflight.json`。后续发布清单必须明确最终源码与新二进制，不沿用R6AW的二进制摘要作为1.0构建结果。

最终核对：R6AX最终包新安装、相同最终程序三引擎输入/关闭、服务与主机重启及保护生产部署已通过；本记录原失败与处理过程保留。具体适用证据见[R6AX最终验收](../../infra/sealskin/r6ax-v1-install-acceptance-2026-10-03.md)。
