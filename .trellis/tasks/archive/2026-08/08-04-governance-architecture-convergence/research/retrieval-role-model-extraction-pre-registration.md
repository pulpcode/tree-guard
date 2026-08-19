# Retrieval 小模型角色抽取首次实验预注册合同

## 单一问题

本实验只回答：默认百炼小模型能否仅依据原始需求正文，输出本地合同可接受的
`TARGET / SCOPE / EXCLUSION` 原文 span，并让冻结 R1 保持已注册的召回门槛。

它不评价完整 Intent、Semantic、动作选择、跨树泛化或生产资格，也不允许根据运行
结果修改 R1、Oracle、Silver 标注、分母或门槛。

## 数据与模型输入边界

- 分母固定为已暴露 M5 clean-room 虚构校准集的 18 个 `PROCEED` 请求；
- 每个不同 requirement text 只调用一次模型，再把通过合同的同一 span 结果确定性
  绑定到五种请求视图；
- 模型输入只包含 requirement text、允许角色和输出合同；
- 不包含树、节点、路径、候选、parent、Intent 自由文本、Oracle、答案、hash 或稳定 ID；
- 使用 `BailianConfig.from_env()` 的默认百炼 endpoint 与配置模型；
- `source_class=CLEANROOM_SYNTHETIC`、`fictional=true`、
  `derived_from_real=false`，按项目已冻结规则无需逐请求外发许可；
- 完整请求和响应只在进程内使用，不写入仓库、Trellis research、日志或公开报告。

## 模型输出合同

模型只允许返回一个 JSON object：

```json
{
  "schema_version": "retrieval-role-model-output.v1",
  "spans": [
    {"role": "TARGET", "text": "原文连续片段"}
  ]
}
```

- 顶层和 span 都拒绝额外或缺失字段；
- `role` 只允许 `TARGET`、`SCOPE`、`EXCLUSION`；
- 模型不输出字符位置，也不承担 Unicode 计数或排序；
- `text` 必须在 requirement text 中逐字唯一出现；本地计算 Python Unicode
  code-point 半开区间 `start/end`；缺失或重复出现均 fail closed；
- 至少一个 TARGET，最多 8 个 span，空文本、重复 span 和非法范围 fail closed；
- 本地按 `(start,end,role,text)` 确定性规范化；
- 输出通过后由本地补充 request hash、provenance 和 evidence hash；
- 不自动修补字段、文本、范围、角色或 JSON。

## 调用与重试

- 温度 0、thinking 关闭、JSON Object mode、非流式；
- 18 次首发；仅在本地合同失败后允许一次完整重试，最多 36 次实际调用；
- 重试只携带固定的 `ROLE_MODEL_*` 错误码，不回传上次模型正文；
- 传输失败不伪装成合同失败，也不执行本实验范围外的连接重试；
- 每次外发前用同进程确定性重建的可能请求体 SHA allowlist 校验；
- 请求正文、响应正文、span 文本、场景身份和 hash 不进入聚合报告。

## 固定指标与门槛

### 抽取层

- 最终合同通过：18/18；
- 首次合同通过：至少 16/18；
- 传输失败：0；
- 实际调用数：18–20；
- 与 Codex/Silver 的 exact-case agreement、span precision/recall 只作诊断，
  Silver 非 Gold，不作为单独否决门槛。

### 冻结 R1 下游

复用五种视图和 Oracle v2：

- `V_REQUIREMENT_ONLY` 与 `V_FREE_TEXT_DROPPED` Recall@8=16/16；
- 两个主视图 MRR 至少 0.90；
- `V_CANONICAL` Recall@8=16/16；
- 全部视图 explicit-empty=2/2；
- `V_PARENT_ABSENT` Recall@8 至少 15/16；
- `V_PARENT_WRONG_BRANCH` Recall@20 至少 15/16；
- 全部视图确定性重放18/18。

## 决策规则

- 全部门槛通过：角色抽取 + 冻结 R1 在暴露校准集上形成候选主链路，下一步只做
  新未见树确认，不再用本集合调 Prompt、角色合同或召回；
- 仅首次合同通过率失败、重试后其余门槛通过：总体仍 FAIL，说明接口脆弱；允许下一
  Prompt 版本仅针对聚合错误码重新预注册，不修改 R1；
- 最终合同或传输失败：归因模型/Provider 边界，不运行该单元下游；
- 合同通过但下游失败：归因角色语义选择，不归因 R1 格式或传输；保持 R1 不变；
- 下游 Recall/空目标通过但 MRR 失败：保持 FAIL，进入 Semantic Top-K 重排职责，
  不降低门槛；
- 首次冻结结果产生后不得覆盖版本或现场调参。

## 结论限制

本数据已经暴露且 Silver 标注参与架构校准。即使 PASS，也只证明默认模型在这 18 条
虚构需求上的可行性；必须使用新领域或新树、此前未进入 Prompt 调试的请求做独立确认，
才能讨论生产试验资格。
