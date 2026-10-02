# 当前真实业务一致性备份

[R6AU 工作项](../../../docs/work-items/R6AU-2026-10-02-consistent-business-backup.md)。工具：[consistent-business-backup.py](consistent-business-backup.py)。本流程独立于已完成的合成Home异机验收；开始记录不等于真实备份已经完成。

## 停止时点与维护前置

先核对当前固定版本、所有Profile状态、Home挂载、网络/Session占用、未完成操作、作业状态及足够的磁盘/tmpfs。正常停止前必须调用 `-inspect-capacity`，核对实时磁盘、内存预算、活动数量及并发，并计入归档/传输占用；仅查看df或代理探测不构成完整预检。归档应预留传输失败时仍能恢复生产的空间。确认每个原活动Profile的恢复启动条件；代理上游不可用时，新代次可能无法通过强制探测，不应直接停止后再发现无法恢复。用户主动停用的实例保持停用，目录中的删除记录与墓碑保留。

整体备份的私有plan显式映射归档前缀到绝对源路径：完整storage（含历史Home和共享文件）、controller-config、Adapter配置/journal/当前账号与密钥、所有管理目录、Store主密钥、完整spool/accepted产物/缓存、所有引用资产、冻结runner/native targets、作业客户端依赖、服务单元、Caddy配置/证书状态及程序身份。镜像层和age解密身份单独保存与核对；不会将SSH密码作为备份输入。

在恢复路径与维护范围明确后暂停入口新写入、停止空闲runner，通过原生命周期正常停止活动Profile并逐个确认零Worker/网络资源、Home没有写入者。然后停止Adapter/控制器等业务写入者，记录`QUIESCED`检查点。需要完整独占时持有原Adapter的service lock，维护操作器同样须取得该锁。控制器重启保留原镜像、secret/display tmpfs和所有Compose依赖，不重建真实Home、不清空journal。

`checkpoint.json`中的`all_profiles_stopped`和`writers_stopped`必须来自维护程序的实际检查。备份工具本身不停止服务、不能用调用者填入两个布尔值代替运行证据。

## 加密与核验

只在0700私有目录工作，设置umask 077。示意命令中的路径和公钥来自本项私有记录：

```bash
python3 infra/sealskin/checks/consistent-business-backup.py create \
  --plan /private/backup-plan.json --checkpoint /private/checkpoint.json \
  --output /private/business.tar.gz.age --receipt /private/receipt.json \
  --age /private/tools/age --recipient age1_PUBLIC_RECIPIENT

python3 infra/sealskin/checks/consistent-business-backup.py verify \
  --archive /private/business.tar.gz.age --receipt /private/receipt.json \
  --identity /private/keys/age-identity.txt --scratch-root /dev/shm/private-backup \
  --age /private/tools/age
```

工具在加密前后核对完整名称/类型/权限/UID/GID/文件内容/链接文本，源发生变化则保留partial诊断，不发布最终归档。只排除`storage/<owner>/<home>/.XDG/wayland-<数字>`下无持久载荷的停止后Wayland socket，明确记录且不删除源节点；其他特殊节点拒绝。链接不跟随，已知Home/资产中的链接最后恢复，拒绝链接作为归档成员的父路径。

收据和独立保存的归档/manifest摘要共同作为传输核验输入。新目录解密身份必须单独传输；真实凭据、Home路径、文件清单、数据库结果等保存在被忽略的私有证据目录，不进入公开报告。

## 独立恢复及后续启动

在独立机器核对精确镜像ID、工具/归档摘要和文件集。解密必须在tmpfs完成age认证，认证或任一成员校验失败时不创建目标目录。`restore`参数同`verify`，额外传入`--target /private/new-restored-root`；已存在的路径拒绝覆盖。

恢复保存原文件/链接及权限，root执行时保留UID/GID，并写入`RECOVERY_PENDING`。这个文件不等于Controller自动恢复锁；在人工/维护程序完成当前撤销和账号审查、全部路径重绑、端口/网络隔离前，禁止启动恢复的业务服务。原始恢复目录保持只读用途，服务演练使用独立副本。

真实浏览器副本先限制外网，避免第三方账号或站点产生写入。分别记录逐文件一致性、实际数据库/授权可读性、控制服务与浏览器启动的证据范围；没有真实登录验证时不声明第三方登录会话通过。恢复不得覆盖生产当前目录、账号、Home、journal或墓碑。

生产恢复只重开本项原活动且满足恢复条件的Profile，或遵循用户明确接受的例外范围。保留原Home/应用/网络/环境定义，新操作和新Session按正常流程生成，不把旧journal回放覆盖新状态。最后核对生产状态、暂停/恢复服务、独立QA清理和备份留存。

## 工具验证

`test_consistent_business_backup.py`使用真实age和独立合成数据验证：往返/权限/链接/恢复标记与拒绝覆盖、未静止拒绝、篡改密文、错误密钥、错误manifest pin、精确socket排除及其他特殊节点拒绝、源别名/越界/重复前缀拒绝。本机及独立机各7项通过。Python3.11的流式tar不接受compresslevel参数，压缩层使用显式GzipFile；首次失败保留在R6AU私有记录。
