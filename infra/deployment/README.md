# 1.0 全新安装入口

当前为 [R6AX](../../docs/work-items/R6AX-2026-10-03-v1-release.md) 发布候选，实际独立安装/重启验收仍进行中；不得把候选材料当作已发布的 1.0。完整操作见[部署说明](../../docs/deployment-v1.md)。

`install.py` 只处理全新应用目录，安装固定镜像控制器、Adapter、环境任务执行器和双域名 HTTPS 入口。默认空账号/浏览器，安装已验收的 4/2/24 内置数据。使用独立非 root 系统用户，控制身份与网页管理员分离，后者由部署者通过 `profile-accounts init` 初始化。失败目录、密钥和日志保留，不自动删除或重试覆盖。

`package.py` 对显式准备的发布目录生成完整文件/权限清单与确定性归档。它不是秘密扫描器，不能对生产根运行；候选来源及敏感材料排除须在发布验收记录中核对。镜像单独归档并验证。安装器验证每个文件摘要、模式、文件集合以及 Docker 镜像 ID/平台，拒绝符号链接和特殊文件。归档摘要必须通过可信发布记录取得；归档内自带清单本身不能证明发布者身份。

入口参数只接受新目录、新用户、`bp-` 前缀实例名、两个独立 HTTPS 域名及无冲突端口。`--check-only` 只验证输入/文件，不修改主机，也不声称镜像、端口和系统依赖已通过。实际安装另行检查主机依赖、既有服务/用户/目录/容器和监听端口。

依赖：Linux amd64、systemd、Docker Engine/Compose v2、支持 `format filter` 的 Caddy、Python 3.11+、python3-cryptography；需 root 安装。`--private-tls` 仅用于隔离 QA，生成私有证书并只监听回环。生产使用两个真实 DNS 名称和 Caddy 自动 HTTPS。控制后端使用独立私有 CA，Adapter 固定验证该 CA 与 Session DNS 名。后端证书有效期一年，运维必须在到期前安排证书更新。

验证：`PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s infra/deployment -p 'test_*.py' -v`。真实安装、登录、三引擎及重启结果归 R6AX 验收；源文件校验不替代运行验收。
