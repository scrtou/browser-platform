# server-2026.10.02.2

2026-10-02 本地已封存。提交 `f0b84fb409d6f78a6b9a911cc1fbd0457b08424e`，独立分支 `release/server-2026.10.02.2`、附注标签 `server-2026.10.02.2`；原开发 HEAD/索引在封存期间保持。本次没有重新部署或推送。

在 `.1` 已部署源码基础上纳入 R6AL 网络列和 R6AM 真实代理名称。Adapter `b9e9832d9c24ed9abf2a4f8fb1d236eb8ba4c2c99562869d8f806d232bfaf288` 与运行进程匹配；控制器 R6W 的 97 个实际文件逐一匹配，R6Z1 runner/目标清单保持。

源码清单 296 文件，SHA256 `0e6573b0ea604d487b455d23502a78575dc4cb495625764d281488e22a8ba930`。R6AM 两套 Go test/vet、7 组名称解析和 24 页面状态、R6AK 精确控制器 554 项测试按未变化范围引用；本项标签逐文件、归档解包/二进制摘要及生产保护核对通过。

| 归档 | SHA256 |
| --- | --- |
| `browser-platform-server-2026.10.02.2-source.tar.gz` | `a990c243ecb242c328fee5cda72824e88138e1bc9844f6dcdae13e0a6ba5675a` |
| `browser-platform-server-2026.10.02.2-linux-amd64.tar.gz` | `783d07f2d7f3c0dac5e6774dff60408d036e03b9ea9f4d181cb9f0a20459c5f8` |

归档位于被忽略的 `infra/sealskin/runtime/r6ao-patch-release-20261002/artifacts/`。解包后执行 `python3 verify-release.py`，服务器包加 `--binary bin/profile-adapter`。原始二进制与源码清单分别验证，重新编译不承诺字节相同。

恢复边界继承 `.1`：此包不含真实 Home、配置/账号、密钥、作业数据或镜像层；程序回退不能覆盖当前目录、journal 或 Home。完整异机恢复属于 R6AP。当前客户端验证已获用户确认，历史精确参数不补造；R7G 未包含在本静态恢复版本，部署已获本轮授权并另项实施。商业供应方自然漂移保持未测。

见 [R6AO 验收](../../infra/sealskin/r6ao-patch-release-acceptance-2026-10-02.md)与[剩余工作](../remaining-work-2026-10-02.md)。
