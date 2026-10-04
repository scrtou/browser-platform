# 按部署说明执行1.0全新安装

状态：已完成。用户授权在清理后的本机按部署说明实际安装，使用既有两个域名和指定的首位管理员，并核实能否正常部署。

范围：按当前主分支install.py、公开Release材料和私有安装JSON，创建独立 /srv/browser-platform、bp-main实例与bpservice用户；保留原Caddy域名配置、证书、真实旧Home和维护备份，不恢复旧业务状态。原始验收阶段使用项目入口服务；随后已将公网入口统一迁移到系统 `caddy.service`，新安装改为写入系统 Caddy 站点片段。密码只写私有安装输入，不进入公开文档或操作参数。

实际入口：docs/deployment-v1.md → infra/deployment/install.py的配置/清单/镜像/端口预检 → 四个systemd服务 → 实际管理员CLI初始化、readyz和TLS登录页。R6BA原记录的真实整机/跨用户/TLS缺口由本项独立核对。

完成条件：公开材料下载/合并/摘要验证、INPUTS_VALID、INSTALLED且ready_verified及web_admin_initialized为true；四服务健康、管理员HTTPS登录/管理、内置数据、至少一项真实浏览器创建/授权/显示输入/正常关闭；原Caddy配置与旧数据保留。遇到安装缺陷先记录偏差并修复或明确阻塞，不用降低条件代替验证。

已有改动：上项维护的operations/progress/roadmap/工作项记录保留；程序源码在开始时无改动。详细敏感证据仅在 /home/sshUser/browser-platform-deployment-20261004/ 和新实例私有日志留存。

收尾更新：本工作项、索引、验收、progress/roadmap/operations及确有必要的部署文档/实现；不启动指纹增强等其他计划，不执行主机重启。后续 Caddy 入口迁移同步更新了安装器、部署说明和验收补充记录。

实际结果：[验收PASS](../acceptance/deploy-v1-doc-install-2026-10-04.md)。五项公开材料摘要、INPUTS_VALID、INSTALLED、四服务active/enabled、跨用户运行、本机证书验证与公网HTTPS管理员登录/管理通过；内置4指纹/2显示/24组合安装正确。用户追加Google起始页核对后，Camoufox/Chromix/Firefox均完成真实Google画面、网址/标题读回、远程键盘输入、正常停止和归档删除。

收尾：原Caddy三份配置摘要未变、原证书及旧数据/恢复材料保留；零未删除浏览器、零QA worker，6条QA删除历史保留。私有安装JSON已移除admin，客户端凭据和Cookie已删除，重复分卷与测试依赖已清除，约23.13GiB可用。文档索引、验收、运维、进度和计划已更新，git diff --check通过。未改应用源码、未执行主机重启或启动其他功能工作；完整组合矩阵、音频与实际Trilium客户端不在本项验收范围。
