# DEV-012 · DNS 依赖安装器引入未固定系统包

状态：已解决（代码/隔离 QA，未部署）。关联 [R5C2](../work-items/R5C2-2026-09-14-approved-dns-ttl.md)。发现/解决日期：2026-09-14。

## 预期与事实

控制 Runtime 应从固定上游镜像和可校验构建输入得到，新增 DNS 依赖不能依赖浮动的系统仓库结果。R5C2 `build-1` 已固定 dnspython wheel，但基础镜像没有 pip，首版 Dockerfile 用 `apk add --no-cache py3-pip` 补齐；该步骤没有固定版本，可能同时改变 Runtime 系统包。55 个准备文件重现一致，只能证明输入目录一致，不能据此证明未来系统仓库相同。

证据在私有 `infra/sealskin/runtime/r5c2-dns-ttl-2026-09-14/build-1/Dockerfile`、`build-1-runtime.log` 及 `build-reproduction.json`。该候选的代码/QA 结果保留，未部署生产。

## 处理

选择修复构建实现。固定 pip 25.3 wheel 与 SHA-256，将 wheel 作为临时 `PYTHONPATH` 执行安装器；Runtime 不执行 apk，也不把 pip 安装到系统包目录。dnspython 继续由本地 wheel 以 `--no-index --no-deps --require-hashes` 安装。准备器、依赖锁和安装输入进入包装摘要。编译/测试工具仍仅在 checks 层安装，不改变 Runtime。

最终 Runtime 为 `0.3.2-dns-v1-742b67ce9ba53575-pkg-ba7da090ed8a`（image ID `sha256:e801c2b869943d8367fc1cc8c0e78b45b2a14fbfc06ffe048689240728b16cb6`）。实测系统 APK 数据库摘要和 Python 版本与固定基础镜像一致，系统未安装 pip，dnspython 为 2.8.0；两个 wheel 的错误散列均在构建前拒绝。339 项控制端、3 项安装检查、11 项引导 DNS 和 7 项 DIRECT 核心检查通过，56 个准备文件逐字节重现。实际 QA 控制容器内 20 个 payload 文件再次逐项核对。

证据为 `runtime-dependencies-final.json`、`pip-hash-rejection.json`、`build-reproduction-final.json`、`final-installed-payload.json` 及 [阶段报告](../../infra/sealskin/approved-dns-ttl-acceptance-2026-09-14.md)。首版结果保留，公开 DNS/TTL 条件仍未完成。
