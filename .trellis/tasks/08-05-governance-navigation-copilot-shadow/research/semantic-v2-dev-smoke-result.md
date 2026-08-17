# Navigation Semantic v2 开发 smoke 结果

## 范围

- 日期：2026-08-17；
- 数据：仓库既有、非密封、完全虚构的消防 medium clean-room Silver 开发集；
- 分母：11条目标存在且当前 Top-8 可见的直接场景；
- 模型：当前百炼配置；
- 输入：权威原始需求、结构意图和最多8个临时候选；隐藏目标和评分 Oracle 未进入模型；
- 输出：只保留本聚合记录，未保存请求、响应或逐项结果。

## 聚合结果

- Retrieval 可执行：11/11；
- 模型合同有效：11/11；
- 正确突出：10/11；
- 错误突出：0/11；
- 安全不突出：1/11；
- Policy 状态：`CANDIDATES_AVAILABLE=10`、`NEED_EVIDENCE=1`；
- Provider/合同失败：0；
- 关系计数：`SEMANTICALLY_EQUIVALENT=11`、`REUSES_CONTRACT=6`、
  `CONTEXTUALLY_RELATED=6`、`NOT_EQUIVALENT=65`。

唯一安全不突出项存在结构合同冲突；即使模型给出等价关系，本地严格 Policy 也没有形成
错误突出。这是预期安全行为，不计为错误推荐。

## 传输修复

首次运行的11条均在模型前返回 `BAILIAN_CONNECTION_FAILED`。无凭据探测证明 endpoint
可达，进一步定位为系统 Python 缺少完整公开 CA 信任链。实现改为只对公开百炼 Provider
显式使用项目锁定的 `certifi` CA bundle；没有关闭 TLS 校验，也没有改变内网 Qwen、
loopback 或其他隔离 opener 的默认信任行为。修复后11/11请求成功完成。

## 结论与限制

该结果支持两个开发结论：v1 缺少原始需求确实是实质合同缺口；补齐输入并定义关系边界后，
当前模型在这组既有 Silver 样本上能够进行有用且无错误突出的候选比较。它不证明生产能力，
也不能将已揭盲资格集重新计分。数据规模小、来源已用于开发，且没有覆盖生产表达分布；未来
若申请生产 Shadow，仍必须使用新的独立密封分母。
