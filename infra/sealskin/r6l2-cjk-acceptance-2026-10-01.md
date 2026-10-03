# R6L2 · 中文字体修订验收 · 2026-10-01

状态：修复代码、隔离字体/Worker 验收及生产目录追加通过；现有生产 Chromix 应用新修订和用户中文反馈待完成。

## 版本与范围

原镜像 `sha256:cd521d91037af114833f9df994e3242c4d6078859212909c586b412da660a3ae`；新镜像 `sha256:19f20e6ec641f6240cdc238ae041fc16c93515c83b2da1943871026949d3a2e6` 完整继承原层，只增加固定字体配置、摘要清单与启动校验。Noto CJK `1:20240730+repack1-1build1` 已在原基础层，新版无需联网安装软件。Chromix 154/en-US/UTC/1280×720/DPR1 保持。

新 artifact `chromix-154-en-us-utc-1280-cjk-r2` revision 2；浏览器和显示模板身份不变。原 r1 和所有其他目录条目保留。字体属于环境变更，未覆写旧环境或运行容器。

## 证据

- 旧配置下 `fc-list :lang=zh` 为空，系统配置能列出固定 Noto CJK；旧真实浏览器截图中“输入、测试、汉、显”等字显示缺字方框，繁体样本部分正常。
- 新独立 /init/X11 Worker 的简体、繁体、中英文混排样本显示正常；CDP CSS 字体观测命中 Noto CJK，输入字符串保持。截图经人工查看。仅独立 QA 开启 loopback CDP，正式应用不含调试参数。
- 错误显示认证 401 / 正确显示认证 200，正常关闭、容器退出清理通过。8 项 Python 回归含字体篡改/缺失拒绝、独占 Home 与种子保持。
- 使用当前已部署 Adapter 源码验证新旧合并目录、隔离创建 revision 2、同引擎回退应用通过；状态及控制器替身隔离，不修改真实 Home。精确 r2 产物的镜像启动校验通过。
- 生产两个目录按旧摘要校验后追加，Profile 目录摘要保持，无 Adapter/控制器重启、无既有 Worker 重建。QA 资源已清理。

私有证据在 `runtime/r6l2-cjk-20261001/`：before/after fonts-result.json 与 cjk-rendering.png、after/result.json、font-build-inputs.json、exact-r2-verify.log、catalog-deployment.json、catalog-before、源码诊断测试与 manifest。首个字体 QA 的 CDP 调用分离会话导致 CSS.enable 失败；修复工具为同会话启用 DOM 后复测原实例，未将工具失败记为浏览器失败。

原 R6L 网络、关闭拒绝与数据恢复证据仅作为未改变基础层的继承依据，本次未重新执行全网络/恢复矩阵；未声明全部字体指纹一致性、所有生僻字或 Mac 输入法通过。现有生产 Home 的新修订生效仍需用户在管理页正常关闭/近期确认/应用并重开。

[组件与操作](../chromix/README.md) · [工作项](../../docs/work-items/R6L2-2026-10-01-chromix-cjk.md) · [DEV-093](../../docs/deviations/DEV-2026-10-01-093-chromix-cjk-fontconfig.md)

后续生产复核：用户已确认中文显示正常；生产 Chromix 记录绑定 cjk-r2、revision 6、ready。字体修复已收尾，原待应用描述保留历史范围。
