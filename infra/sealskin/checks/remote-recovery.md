# 独立机器恢复验收

[R6AP 工作项](../../../docs/work-items/R6AP-2026-10-02-remote-recovery.md) · [原本机恢复边界](disaster-recovery.md)

当前处于实施与验收中，不能据此声明异机运行已通过。使用独立 Debian 12 / amd64、UID 1000 的 `qa` 用户与 Docker 组；预先检查已有容器、包管理任务和端口，不清理他人资源。依赖为 Docker、Python 3.11+、PyYAML、PyJWT、cryptography、websocket-client、Caddy 和精确 age v1.2.1。控制器/Worker/Relay/探测镜像必须从记录的 image ID 导入并逐一读回，不能用浮动标签代替。

## 输入及边界

- `.2` 程序包、冻结控制器和执行器、完整镜像归档及分块/总 SHA256。
- 单独传输的 age 解密身份；传输脚本从本地受保护凭据文件读取 SSH 密码，不放入命令参数或 Git。
- 合成 Work 检查点：`backup/home.age`、原 receipt、`inputs/MANIFEST.json`、工具/当前二进制、当前受信任账号和撤销 Store、原测试标记与 Worker 身份证据。
- 原生引擎检查点：Camoufox/Chromix 的完整 accepted artifact/report、正常退出的合成 `home-A`、加密归档及 manifest。必须使用相同精确 image ID，不替换为另一候选；QA 标记固定为 `native-home-A`。
- 生产恢复材料：完整 spool、目录、被引用产物挂载、冻结 runner、版本包及历史真实 Home 密文，单独加密保存并仅离线校验。历史 Home 时点和当前目录不是同一事务，**不构成当前业务一致性备份**；不得据此激活真实身份或供应方凭据。

`recovery-materials.py --plan <私有映射> --manifest <新清单>` 按显式绝对路径盘点目录/普通文件/符号链接；不跟随符号链接，不接受特殊节点。`--verify` 拒绝内容、路径集合或模式变更。清单和路径映射属于私有证据。打包前后再次核对清单，传输完成后才发布最终归档；异机解包先完成认证，拒绝越界路径，只在所有普通文件落盘后建立链接，避免写穿链接。

## 实际运行与清理

用匹配 UID 解包 QA 输入到私有 `.../infra/sealskin/runtime/r6ap-<任务>/`。原 source 路径不在目标机器提供，所有配置经既有严格恢复布局器重绑。依次执行：

```bash
python3 infra/sealskin/checks/check-remote-recovery.py restore --root /private/runtime/r6ap-task
python3 infra/sealskin/checks/check-remote-recovery.py verify --root /private/runtime/r6ap-task
python3 infra/sealskin/checks/check-remote-recovery.py rollback --root /private/runtime/r6ap-task
```

`restore` 验证输入与镜像，再解密、核对恢复锁、拒绝缺少当前账号的激活、合并最新撤销，建立全新控制根。`verify` 检查禁用账号拒绝、固定入口/显示授权、Cookie/localStorage/IndexedDB、HTTPS、四类绕过、健康及正常停止。`rollback` 再从同一密文恢复到第二个根，验证检查点读回并退役 QA 服务。不是恢复后新增数据的反向同步。

原生引擎运行器：

```bash
python3 infra/environment-engines/check-remote-recovery.py \
  --inputs /private/native-inputs --identity /private/keys/native-identity.txt \
  --age /private/bin/age --output /private/runtime/r6ap-native
```

逐引擎核对密文、artifact/report 摘要与原观察，使用已验收入口创建独立显示凭据和 Home；恢复、重开、检查点回退均检查三类存储、指纹、显示认证、实际输入、HTTPS 和直接出站拒绝。自动分辨率允许按原契约变化的显示字段，其他原有指纹比较保持。失败保留日志/截图与无法正常关闭的实例，不强制删除浏览器来绕过关闭失败。

最终必须核对本项的容器、网络、进程、socket 与 tmpfs 清零，保留私有验收证据和加密归档。生产侧镜像导出和源文件读取不应修改真实 Home/会话；前后保护快照另行核对。未通过项和尚待执行项保持明确状态。
