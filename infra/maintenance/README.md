# 维护工具

`go-cache-retention.py` 只处理显式指定的一个任务 Go 编译缓存；不会搜索后自动删除，也不清理浏览器数据、依赖包、镜像或卷。完整保留规则见 [磁盘政策](../../docs/disk-retention.md)。

先确认对应构建已结束，然后生成清单：

```bash
python3 infra/maintenance/go-cache-retention.py plan \
  --runtime /absolute/project/infra/sealskin/runtime \
  --cache /absolute/project/infra/sealskin/runtime/completed-task/go-cache \
  --out /absolute/private-evidence/cache-plan.json
```

清单保存每个标准缓存文件的 SHA256、大小、修改时间和权限。工具要求 Go 标准 README、哈希目录/文件布局，拒绝符号链接、额外内容、活动 Go 编译，以及运行或停止容器的相交挂载。确认清单在本次维护范围内，再执行：

```bash
python3 infra/maintenance/go-cache-retention.py apply \
  --plan /absolute/private-evidence/cache-plan.json
```

执行前重新检查活动和完整清单；有变化则拒绝删除。成功后保留空缓存根目录，调用方可在确认为空后删除根目录。清理不是与外部构建器共享的事务锁，维护期间不得启动使用该缓存的新构建；发生部分失败保留计划与结果并重新核对，不盲目重跑。

旧测试容器产生的 root 缓存可在单独维护脚本中处理：先在主机重新核对计划和挂载，再运行无网络、只读根文件系统的短期容器，只将该缓存挂载到 `/cache`，工具/计划只读挂载，使用 `apply --plan /plan.json --mapped-cache /cache`。该参数只允许容器内 `/cache`，不能替代主机活动检查。只为所选缓存授予必要的目录访问能力，不挂载 Docker socket 或其他数据目录；容器退出后核对缓存已空及生产保护快照。R6AN 私有执行脚本保存本机精确命令与回执。

测试：`PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s infra/maintenance -v`。

## R6AV指定测试数据清理

[r6av-test-cleanup.go](r6av-test-cleanup.go)与[入口补丁](r6av-operator-entry.patch)只用于本轮已授权对象，编译进经过核对的独立Adapter维护副本；不得加入线上HTTP路由。入口补丁针对R6AS固定源码的维护入口，修正后的业务源码与该维护入口分别核对。必须先具备[R6AU验证恢复点](../sealskin/r6au-consistent-business-backup-acceptance-2026-10-02.md)、停止Adapter/空闲runner和监控，并由原state服务锁排他保护。inspect核对剩余对象，apply调用原Service正常停止/归档/撤销/删除，失败保留目录和操作记录。

它限定4个指定Profile、2个代理修订及已盘点来源模板；组合/结束任务另与维护前私有清单核对。Home仅由Controller原子归档，审计/墓碑/作业证据保留。最后将唯一owner替换为显式等待初始化状态，不留下默认账号。重复执行沿已删除/正在删除记录继续，不恢复旧journal。这个历史专用工具不应被当成通用“清空系统”命令。

入口补丁使用零上下文格式，须先核对固定源码摘要再以`git apply --unidiff-zero`应用；仅适用于本项独立维护副本。
