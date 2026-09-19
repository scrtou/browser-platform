# DEV-2026-09-19-054 · R6F 组合运行器仍绑定旧 R5E QA 根

状态：已解决（现有环境范围；自动运行器改造另列后续）。关联工作项：[R6F](../work-items/R6F-2026-09-19-release-combination.md)。

## 预期

按用户后续决定，R6F 组合验收直接使用当前项目测试环境和现有控制器，不再建立专用 QA 根或新入口；仍须保证现有 Personal/Work、Home、Session 和运行中的容器不被破坏。

## 实际事实

- 现有 `infra/sealskin/checks/run-release-combination.py` 的协调器硬编码 R5E 的 `network-qa` Profile、旧资源注册表、旧监听地址和旧组合根校验。
- 按现有环境推进后，已用当前控制器基镜像叠加 R6C/R6D 四个控制器文件，构建 `r6f-existing-overlay-20260919`，并在无网络 checks 镜像中通过 11 项管理/Home 归档测试。
- 接入当前运行控制器前核对发现：运行中的管理员公钥 `/config/.config/sealskin/keys/admins/admin` 与仓库 `config/admin.json` 保存的私钥不匹配；现有目录中未找到对应私钥。不能在不验证身份的情况下调用管理员接口，也不能替换管理员密钥来绕过该门槛。
- 当前已完成的 R6C–R6E 隔离验收、r9 artifact unit、Adapter 回归和生产安全子集保持性检查仍然有效，但不覆盖同版本完整组合。

2026-09-19 后续只读复核：当前本机运行的 `sealskin` 容器仍挂载 `infra/sealskin/config/.config/sealskin/keys/admins/admin`；该公钥与仓库 `admin.json` 私钥推导出的公钥一致，使用同一身份对本机控制器执行管理员握手及 `GET /api/admin/apps/installed` 成功（返回 5 个现有应用）。随后安装 `r6f-existing-overlay-recheck` 并重启 `sealskin`；此前发现的不匹配作为历史事实保留，未替换管理员密钥。

## 影响

完整 R6F 组合发布门槛尚未满足。当前控制器补丁和现有环境受控组合已验证创建/删除、代理探测和自定义 artifact 启动，组合控制根也已完成隔离加密恢复；但真实生产 Home 备份、真实 Mac 自定义 artifact、Profile 生命周期写操作和实际回退仍未完成，不能把手工验证扩大为自动运行器或完整发布通过。

## 处理与后续

按用户授权改为现有环境受控手工组合。当前管理员身份复核通过后，`r6f-existing-overlay-recheck` 已安装并重启 `sealskin`；固化指纹和自定义指纹 Profile 均完成创建、启动、健康/代理探测、删除清理，临时记录保留为 `deleted` 审计状态。未替换管理员密钥，现有 Personal/Work 运行代次未重建；组合控制根已在隔离旧 QA Home 上完成加密归档、verify 和离线 restore，Profile 停启/关闭、真实生产 Home 备份和实际回退仍未执行。原 `run-release-combination.py` 继续绑定旧 R5E QA 根，后续若需要自动化组合应另建工作项，不把本次手工证据写成自动运行器通过。
