# DEV-2026-09-17-045 · R6A 管理列表对任意登录账号开放，与两级访问设计不符

状态：已解决（R6B 候选，2026-09-18；未部署生产）。发现日期：2026-09-17。关联工作项：[R6A](../work-items/R6A-2026-09-17-environment-list.md)、[R6](../work-items/R6-2026-09-16-environment-management.md)。

## 设计预期

用户 2026-09-17 明确：登录管理面板需要管理员账号密码，登录单个远程浏览器入口也需要账号密码。[管理面规格第 2 版](../specs/proxy-environment/management.md#访问账号与登录-url两级访问)据此规定：`/manage/*` 只对 `role=admin` 的账号开放，`role=user` 的账号只能登录被分配的浏览器固定入口，访问 `/manage/*` 返回 403；账号表升级为 version 2 增加 `role`。

## 实际事实与证据

- R6A 候选（提交 `90e1019`）按 2026-09-16 的第 1 版设计实现：网关 `serveEntry` 对任何有效登录放行 `GET /manage/` 与 `GET /manage/environments`，并附加该账号的 `view`/`start` 授权（`adapter/internal/access/gateway.go`、`manage_test.go`、[R6A 验收](../../infra/sealskin/environment-list-acceptance-2026-09-17.md)）。
- 账号表仍为 version 1，没有角色字段；生产 Adapter（candidate-4）没有 `/manage/` 路径，生产不受影响。
- 第 1 版设计当时没有“面板仅管理员”的要求；本偏差来自 2026-09-17 的需求补充，不是实现违反当时设计。

## 影响与处理决定

- 影响：只涉及未部署的 R6A 候选。若按现状部署，普通账号能看到自己被授权浏览器的只读摘要（不含他人、不含后端能力），但不满足用户要求的“面板仅管理员”。
- 处理方式：修复实现，归入 R6B——账号表 version 2 增加 `role`；网关 `ManagePath` 分支只对 `admin` 放行，非管理员返回 403；R6A 的授权测试相应改为角色测试；version 1 账号迁移一律视为 `user`，管理员由主机 CLI 显式创建。设计文档已先按第 2 版同步。
- 不需要用户额外决定；R6A 候选在修复并通过 R6B 验收前不进入发布包，生产不变。

## 实施、验证与文档同步

| 材料 | 更新 / 结果 |
| --- | --- |
| 实现 | R6B：`access.Account.Role` 与 version 2 注册表（无角色仍写 version 1）、`AccountStore` 最后管理员保护、`serveEntry` 对 `/manage/*` 按 `admin` 放行且 `user` 得 403、`/auth/reauth`、`/auth/password`、按账号撤销 |
| 验收与证据 | [R6B 验收](../../infra/sealskin/environment-directory-acceptance-2026-09-17.md)：`access/manage_test.go`、`accounts_test.go`、`httpapi/manage_gateway_test.go` 覆盖 user 403、admin 全量列表、version 1 默认 user、最后管理员保护；收尾修复 DEV-046 后共 147 项测试、vet、race 通过 |
| 设计 / 规格 / 组件说明 | 规格第 2 版“访问账号与登录 URL（两级访问）”已更新；Adapter/入口登录说明已注明 R6A 候选的差异 |
| 进度 / 计划 / 工作项 | R6/R6A/R6B 工作项、进度、计划、偏差索引已同步为已解决 |

## 最终复核

2026-09-18：R6B 候选中入口账号访问 `/manage/*` 得到 403 页面且不含浏览器信息，管理员看到全部浏览器；R6A 的 `view`/`start` 双能力授权被管理员的 `view`/`manage`/`stop`（被分配另有 `start`）取代。剩余边界：候选未部署，真实客户端归 R6F；解决日期 2026-09-18。
