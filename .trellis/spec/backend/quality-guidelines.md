# 质量规范

## 当前工具链

- Python 3.10+；
- 确定性核心继续优先使用标准库；Workbench 应用边界使用 FastAPI/Uvicorn；
- setuptools + `src` 布局；
- 标准库 `unittest`；
- React 19 + TypeScript + Vite + Ant Design 的 `web/` 前端，使用 Vitest 做聚焦
  纯函数测试；
- 提交的 `uv.lock` 提供可复现开发环境。
- `web/package-lock.json` 提供可复现前端环境。

当前没有 Ruff、Black、mypy、pytest、coverage、pre-commit、CI 或第三方 JSON
Schema validator，不得报告为已通过。新增运行时依赖必须有具体需求、内网/离线
影响分析、lock 更新和聚焦测试。

Ruff、mypy、coverage、pre-commit 和 CI 在 Shadow MVP 最小可行性验证后建立
独立任务，根据实际维护成本引入；延期不等于已经通过这些检查。

## 实施模式

### 确定性逻辑保持纯净

diff、evidence mining、review state、validation、replay 接收显式对象并返回显式
对象。文件、环境、时钟、随机 ID 和 HTTP 留在应用边界，并以值传入核心。

### 持久化工件不可变

公共/持久化工件使用 `@dataclass(frozen=True, slots=True)`；嵌套 JSON 通过
`freeze_json()` 脱离输入，通过 `thaw_json()` 返回副本。私有短期 builder
可以可变。

### 构造与摄取时校验

持久化类型校验自己的版本、字段、规范顺序、summary、引用和 digest。读取
不可信存储工件时，重建可信规范实例，不直接赋值 decoded dict。

### 排序与哈希显式

影响序列化、哈希或比较的序列使用 sorted ID 或命名等级表；不依赖 dict/set
迭代。所有内容摘要使用 `hashing.canonical_digest()`，并测试包含/排除字段。

### 不同输出独立允许列表

内部完整 `to_dict()`、聚合诊断、模型视图和外网导出是不同产品；每个投影都从
独立正向允许列表构造。真实字段名不得因删除 `VALUE` 就进入外部投影。

### 产品旁路与开发自修分离

- 产品 Shadow MVP 只写 sidecar/overlay，不修改生产信息树或生产数据；
- Codex 主代理或 `trellis-check` 可在当前外网仓库和任务范围内修改代码、执行
  Bash 和测试以修复发现；
- 开发代理不得访问/修改生产环境、受保护数据或受保护源码，不得改动无关用户
  工作；
- 审查代理不执行 commit、push、merge、reset 或破坏性清理。

## 测试组织

测试与所属模块对应：

```text
tests/test_adapter.py
tests/test_diff.py
tests/test_history.py
tests/test_business_review.py
tests/test_evidence.py
tests/test_ai_review.py
tests/test_expert_review.py
tests/test_change_intent.py
tests/test_retrieval.py
tests/test_semantic_recommendation.py
tests/test_ai_cli.py
tests/test_expert_cli.py
tests/test_governance_cli.py
tests/test_demo_cli.py
tests/test_contract.py
```

复用输入只放 `tests/fixtures/fictional/`。通常 deep-copy 虚构树后做一个聚焦变更。
fixture 可以使用消防主题，但必须从批准 Schema 与公开高层概念独立构造，并使用
明显虚构的组织、设施、字段和层级。不得复制真实消防树、字段清单、业务结构或
工程参数；真实数据改名、删除 `VALUE` 或一致伪名化仍不合格。

推荐：

- `unittest.TestCase` 组织行为；
- `subTest` 表达有界矩阵；
- `dataclasses.replace` 攻击 frozen artifact 不变量；
- `tempfile.TemporaryDirectory` 测文件工作流；
- `unittest.mock.patch` 测 transport、环境、时钟和文件失败；
- canary + `assertNotIn` 测泄漏。

unit suite 不发 live network。清空环境配置的测试必须在临时目录运行，避免加载
开发者真实 `.env`。

## 最低测试矩阵

### 每个行为变更

- 预期成功；
- 非法类型/枚举/字段/引用；
- 空值和边界；
- 无关输入重排后的确定性结果；
- 拒绝时精确稳定错误码。

### 合同/工件变更

- JSON Schema 必填字段一致性；
- 精确运行时字段集与版本；
- 序列化 round trip 或可信重建；
- 输入/输出容器不可变；
- summary/派生字段一致；
- 域内变化使 digest 改变，明确排除变化保持 digest；
- 篡改、错误来源和 replay 拒绝。

### 安全输入/输出

- 重复、畸形、超大输入；
- 适用时测试 symlink、FIFO、公开权限和覆盖；
- 部分写入/发布失败清理；
- 缺少 approval 时在网络前失败；
- 聚合输出不含 secret/source/path/真实字段名/text/hash canary；
- 外部请求只含允许列表投影。

### 模型 Provider

- request 字段、JSON-object mode、timeout、尝试上限；
- 不继承 proxy、不跟随 redirect；
- token 只在 header；
- 有界 response 和 envelope/content 严格解析；
- 非法输出重试后 fail-closed；
- 本地跨字段策略和 source/reference binding；
- `ai.called` 与 exit 2/3 分类。

## 必跑验证

从仓库根目录执行：

```bash
UV_CACHE_DIR=/tmp/treeguard-uv-cache uv sync --frozen
UV_CACHE_DIR=/tmp/treeguard-uv-cache uv run --frozen \
  python -B -m unittest discover -s tests -v
cd web && npm ci
cd web && npm test
cd web && npm run build
git diff --check
```

纯文档改动完成前仍运行 unit suite。报告准确命令和真实结果。

## 禁止模式

- 测试/文档含真实、敏感或一致伪名化业务数据；
- 为标准库已能完成的小 helper 增加运行时依赖；
- 第二套临时 JSON hashing；
- frozen 持久化工件保留可变 `dict`/`list`；
- 只改 Schema、serializer、parser、hash 或测试中的一层；
- 不从可信来源重算就信任外层 hash；
- 依赖偶然 object/set 顺序；
- 在已有严格边界使用普通 `json.loads()`；
- 直接把内部 `to_dict()` 发给模型；
- debug print、原始异常、response body、原始日志或敏感工件 dump；
- Shadow MVP 中直接生产/数据库写入或自动 Patch 发布；
- 扩大跨模块下划线私有 helper 导入；
- 把领域策略塞入 CLI。

## 审查清单

- 规则属于永久边界、MVP 限制还是当前事实，是否标注正确？
- 职责是否位于正确模块并遵守依赖方向？
- 确定性代码与不可信 AI 是否分离？
- 合同表示和版本是否同步？
- 排序与哈希域是否显式？
- 内部、聚合、模型和外网投影是否分别允许列表化？
- 失败是否无部分状态并使用正确 code？
- 安全声明是否仅覆盖代码真正检查的内容？
- 测试是否包含负例、篡改、确定性和泄漏？
- 改动及验证是否完全遵守开发数据边界？
