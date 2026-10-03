# DEV-126 · 控制器测试目录与发布源码不同

状态：已解决。[工作项](../work-items/R6AK-2026-10-02-release-organization.md)。

事实：R6AK逐文件核对时，线上控制器97文件完全匹配R6W controller-source-audit.json；但R6W controller/app测试目录缺bounded_logs.py，network_runtime.py与providers/docker_provider.py不同。R6AJ的554项使用该测试目录，不能直接声明覆盖当前生产精确源码。原日志和目录保留。

处理：依据已核对审计清单，只读提取线上97个代码文件形成独立快照；在此完整源码上重跑原控制器套件，不修改线上。版本只纳入通过核对的完整快照。R6AJ报告增加来源修正与精确源码验证引用，R6AK补充此验收后再收尾。不降低验收条件、不把历史目录静默覆盖成正确来源。

验证：线上97文件与原发布审计一致，独立完整快照重跑554项通过；版本树采用此精确快照。当前控制器未改动，R6AJ增加此来源修正与最终补测引用。[R6AK验收](../../infra/sealskin/r6ak-release-acceptance-2026-10-02.md)。
