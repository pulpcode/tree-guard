# M4.7 Semantic 动作政策 A/B 结果

## 来源与边界

- 数据仍为已揭盲 clean-room Silver，只承担 `CALIBRATION_ONLY`；非 Gold、非门禁、
  非 Patch。
- 分母固定为 M4.6 校准召回 `MATCH` 的 44 个观测；Intent、候选集、排序和 Oracle
  均未修改，只把 Semantic v3 替换为候选 v4。
- 私有请求计划 SHA-256 为
  `e3f5a3d2ee77431c0b81d274cf409056326cc2e4fffbb60ffd4aa2e4f745e55c`，包含
  44 个首发和 704 个可能重试正文，共 748 个；执行前逐字节重建通过。
- 私有结果 SHA-256 为
  `3f8af79b875f2f233448ed4cf76f3a02ad04cd279e9f15f54c3a3214f40b3c4c`。
  计划和结果均为不可覆盖的 `0600` 文件；仓库不保存请求、响应、草案或隐藏 Oracle。

## 聚合结果

| 指标 | v3 基线 | v4 |
| --- | ---: | ---: |
| `PREFERRED_MATCH` | 12 | 11 |
| `SAFE_ALTERNATIVE` | 23 | 30 |
| `UNSAFE_MISMATCH` | 7 | 1 |
| `RUN_FAILED` | 2 | 2 |

- 实际请求 46 次：42 个观测首发完成，2 个观测进入一次完整重试。
- 最终合同合法 42/44；原 7 条 `UNSAFE_MISMATCH` 中 6 条转为
  `SAFE_ALTERNATIVE`，1 条仍为 `UNSAFE_MISMATCH`。
- 原 `PREFERRED_MATCH` / `SAFE_ALTERNATIVE` 到 `UNSAFE_MISMATCH` 的新增回归为 0；
  但 2 条原 `PREFERRED_MATCH` 变为 `RUN_FAILED`，另 1 条变为
  `SAFE_ALTERNATIVE`。
- 原 2 条 `RUN_FAILED` 均转为 `PREFERRED_MATCH`。

## 失败归因

- 一条观测首发和重试均为 `SEMANTIC_MODEL_FIELDS_INVALID`，属于模型输出顶层字段合同
  遵循失败；当前安全 trace 不足以进一步区分缺失字段和额外字段。
- 一条观测首发为 `SEMANTIC_ACTION_POLICY_INVALID`，重试遇到
  `BAILIAN_CONNECTION_FAILED`。该记录是合同错误与传输错误混合，不能解释为模型连续
  两次语义失败，也不能在本轮擅自补记成功。
- Codex 对唯一剩余 `UNSAFE_MISMATCH` 做辅助 Silver 复核：请求的确认事实指向
  “可启闭的防火隔断设施”，候选存在防火门系统的同型时间属性；v4 判断为不同业务
  对象并建议从合同新增，Silver Oracle 要求复用现有防火门节点。该输出有可理解的
  类别歧义，但可能制造重复节点，维持 `UNSAFE_MISMATCH`，不扩宽 Oracle。

## 冻结结论

按执行前标准，本轮为 `NOT_PROMISING`：合同合法 42/44 低于 43/44，且 v4 首选 11
低于 12；尽管总不安全从 7 降到 1并且没有新增不安全回归，不能事后放宽门槛。

这不是“技术路径不可行”的证据。结果支持业务对象优先 Prompt 与结构门禁显著改善
安全性，但同时暴露合同遵循稳定性和领域同义/上下位关系判断仍不足。下一步应先用不
改 Prompt、不改 Oracle的有界重复诊断区分两条失败中的随机传输/格式波动，再决定是
修复通用 JSON 合同可靠性，还是停止该候选政策；不能继续围绕剩余单条语义错误定向
调参。

## M4.7b 失败稳定性诊断预注册

- 只选择 M4.7 主结果中的 2 条 `RUN_FAILED`，不是按语义得分重新抽样；
- 每条独立重复 2 次，每次仍最多一次完整合同重试，总调用上限 8；
- 复用 v4、同一确认 Intent、候选集、排序和 Oracle，不修改任何正文或合同；
- 诊断只回答两条失败是否稳定复现。无论结果如何，M4.7 的 42/44、11 个首选和
  `NOT_PROMISING` 均保持不变；重复输出不得计入主分母或政策晋升。

重复计划 SHA-256 为
`2b892fc388f797872b251c0c1a82d85b3f85c9a18ab2b11a0ec4f2c1c54e267b`，结果
SHA-256 为
`8b32ba3e6e77f5d8636ae50d5fdcc84173f6e376ad56bd0d0d8d7230585dfea0`；两者均为
不可覆盖的 `0600` 私有文件。

实际 4 个诊断观测全部首发得到 `PREFERRED_MATCH`，共 4 次请求、0 次重试、0 次合同
或传输失败。由此可将主实验的两个 `RUN_FAILED` 归为非稳定波动，而不是同一输入下
可重复的语义能力缺陷；其中一个主实验失败已明确包含连接错误，另一个字段合同错误也
未在两次独立重复中复现。

该诊断提高了对 v4 技术路径“安全性改善真实存在、合同失败具有随机性”的信心，但不
改变主结果：正式记录仍为 42/44、11 个首选和 `NOT_PROMISING`。后续若继续，应优先
在 Provider 层研究通用结构化输出稳定性和传输重试策略，并在新密封数据上重新验证；
不应继续围绕这两条或唯一剩余语义错误修改 Prompt。
