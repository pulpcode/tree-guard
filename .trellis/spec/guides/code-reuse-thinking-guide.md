# 代码复用思考指南

## 新增前搜索

创建 helper、constant、parser、serializer 或 error code 前：

```bash
rg -n "candidate_name|related_error_code|schema_version" src tests contracts
rg -n "def .*related|class .*Related" src/treeguard tests
```

搜索后判断职责所有者，不复制距离最近的代码。

## TreeGuard 的规范所有者

| 能力 | 所有者 |
|---|---|
| 规范 JSON digest | `treeguard.hashing.canonical_digest()` |
| 递归 JSON freeze/thaw | `treeguard.models.freeze_json()` / `thaw_json()` |
| 安全边界严格 JSON 解析 | `treeguard.json_utils.strict_json_loads()` |
| 源树归一化 | `treeguard.adapter` |
| 模型允许列表投影 | `treeguard.evidence` 或所属 synthesis 边界 |
| 领域状态迁移与回放 | 所属确定性领域模块 |
| CLI 编排与获批准副作用 | 所属 CLI/Provider 边界 |

不得另建 hashing 配方、原始源树遍历、严格 parser 或模型投影捷径。

## 私有 helper

下划线前缀 helper 不是共享 API。当前跨模块私有导入是技术债，不是扩展模式。
出现新的真实消费者时：

1. 比较语义和安全性质是否真正相同；
2. 在正确共享模块提取窄而明确的公共 API；
3. 同时迁移已有消费者；
4. 保留或加强原测试。

不得把安全文件发布或严格输入逻辑复制到新 CLI。

## 何时抽象

多个消费者需要同一个非平凡不变量或安全行为时抽取；一次性编排、或共享抽象
会掩盖领域差异时保持局部。

“出现三次”只是触发检查，不是自动重构规则。Shadow MVP 优先做满足当前 PRD
的最小改动，不做臆测扩展。

## 跨合同变更

持久化字段或枚举变化时，搜索并同步：

- JSON Schema；
- Python 常量、类型和精确字段校验；
- serializer/parser；
- 规范排序与 hash payload；
- 获批准的聚合/模型 projection；
- contract、tamper、determinism、leakage 测试。

## 审查清单

- 搜索是否覆盖 `src`、`tests`、`contracts`？
- 选定所有者是否公共且语义兼容？
- 复用是否保留严格解析、隐私、排序和失败行为？
- 是否增加跨模块私有导入？
- 小型局部函数是否比投机抽象更清楚？
- 新外部投影是否错误复用了内部 `to_dict()` 或真实字段名？
