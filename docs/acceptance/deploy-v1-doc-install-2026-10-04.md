# 按部署说明全新安装验收（2026-10-04）

结果：PASS。对应[工作项](../work-items/DEPLOY-2026-10-04-v1-doc-install.md)，按[部署说明](../deployment-v1.md)实际执行当前主分支安装器和公开1.0材料，无应用源码修改。

## 实际安装

Debian 12 amd64、Python 3.11.2、cryptography 38.0.4、Docker 29.8.0、Compose 5.5.1、Caddy 2.11.4。公开Release程序包、控制器更新包、基础镜像两分卷及完整合并包五项SHA-256均通过。程序包解压到 `/opt/browser-platform-1.0`；私有JSON指定独立根 `/srv/browser-platform`、实例 `bp-main`、系统用户 `bpservice` 和三个默认后台端口。

配置预检返回 `INPUTS_VALID`；实际安装返回 `INSTALLED`、`ready_verified=true`、`web_admin_initialized=true`，发布清单SHA-256为 `ebd8e201b41600edd529c9918b6cf154e036784da38533b1f651c25d7c0ee1d1`。实际使用配置文件初始化首位管理员，账户密码经stdin进入CLI，注册表只保存密码哈希；账户表只有指定管理员。

四个systemd服务均active、enabled；controller为预期的oneshot状态，adapter/jobs/front在bpservice身份下运行。Adapter `/readyz` 为200；直接连接本机入口验证TLS证书和登录页为200。19100、18000、18443仅监听127.0.0.1，公开入口80/443由新实例front负责。

## 公开入口与三引擎

通过实际公网HTTPS入口完成指定管理员登录和管理访问，登录Cookie具有Secure、HttpOnly。初始浏览器为空；4指纹模板、2显示模板、24个内置组合和3个生成目标正确加载。

按照用户追加要求，三种引擎分别以 `https://www.google.com/` 为起始页创建独立QA浏览器，使用固定1920×1080的通用US内置组合及DIRECT网络。通过实际管理页面授权管理员，重新登录后启动；客户端使用官方Google Chrome 154.0.8037.97，经公网显示域名观察真实远程桌面。

| 引擎 | 起始网址及Google标题 | 实际远程Google画面 | 键盘输入 | 正常关闭 | 归档删除 |
| --- | --- | --- | --- | --- | --- |
| Camoufox | PASS | PASS | PASS | PASS | PASS |
| Chromix | PASS | PASS | PASS | PASS | PASS |
| Firefox | PASS | PASS | PASS | PASS | PASS |

起始页面验证使用配置值、浏览器地址栏剪贴板读回、窗口标题和客户端截图共同核对；三者实际网址均为上述Google地址。输入验证在各QA worker的临时textarea页面上，通过公网显示客户端发送独立字符串，再读回worker窗口标题，证明输入实际到达远端。显示Cookie具有Secure、HttpOnly，最终Session URL不携带access_token。停止操作返回stopped；删除后账户授权修订可能导致登录失效，重新登录确认测试浏览器不可见，并由服务端状态确认deleted及worker消失。

## 保留、清理与边界

原 `/etc/caddy/Caddyfile`、autosave及服务覆盖文件的安装前后SHA-256完全一致，原证书保留；原caddy.service保持停用，避免与新实例front竞争端口。原真实storage/config/secrets与私有维护恢复材料保留。最终一个管理员、零未删除浏览器、零QA worker；6条本次QA删除历史作为审计保留。

管理员已从私有安装JSON移除，临时客户端密码和Cookie状态文件删除。已导入且校验的完整基础镜像归档保留，两份重复分卷和仅用于验收的客户端依赖已删除，另外释放约2.73GiB。最终磁盘可用约23.13GiB、使用率77%。

初次验收使用不支持项目H.264配置的Playwright Chromium 140，收到WebSocket二进制但无法解码画面；不能据此认定显示通过。更换官方Chrome后真实Google截图与输入均通过。初次Firefox客户端在窗口初始化前发送导航，未打开fixture；后续等待Google窗口就绪再验证通过。这些为验收环境/脚本修正，未修改发行程序。详细失败和成功证据保留在私有目录 `/home/sshUser/browser-platform-deployment-20261004/`，不公开凭据、Cookie或授权URL。

本项覆盖实际安装、跨用户服务、公网TLS登录管理及三引擎上述生命周期。未执行主机重启、完整24组合矩阵、音频、剪贴板双向权限或Trilium/macOS客户端验收。客户端日志中的音频初始化、无剪贴板权限和首次启动WebSocket重试只留私有诊断，不能据本项声称这些功能通过。
