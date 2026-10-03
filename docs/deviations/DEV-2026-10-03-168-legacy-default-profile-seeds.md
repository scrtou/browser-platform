# DEV-168 · 默认 Adapter 示例仍导入旧浏览器

状态：已解决（主分支示例/文档）。关联 [R6AZ](../work-items/R6AZ-2026-10-03-empty-config-example.md)。

1.0要求新部署默认空浏览器；`adapter/config.example.json` 却仍包含 personal/work 及相应应用/Home。Adapter README和SealSkin PoC步骤仍指导复制该文件。配置中的 profiles 是实际导入种子：目录不存在时 `directory.open` 会写入这两条记录，不能解释为完全不生效的注释。

正式 `infra/deployment/install.py` 独立生成 profiles=[] 和显式空目录，`infra/sealskin/adapter-config.example.json` 也已为空，因此此漏项不否定正式安装器的空初始化验收，也不证明线上旧浏览器重新出现。

处理选择：清空默认示例的 profiles，说明空种子必须配合显式空目录、待初始化账号表和控制身份；全新1.0使用正式安装器。旧兼容种子机制、真实目录和历史证据保留。v1.0标签/归档固定不覆盖，修复以主分支后续提交交付。

验证：两份示例实际Load/Validate、12项配置及6项目录/初始化已有回归通过，初始化说明已补齐显式状态与权限，见[验收](../acceptance/r6az-empty-config-example-2026-10-03.md)。旧v1.0归档未被改写；本项不需要程序部署。
