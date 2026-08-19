# Retrieval 角色模型 v1 安全差异诊断结果

## 重放结果

诊断重放使用相同模型、v1 Prompt、18条虚构请求和冻结 R1：

- 合同首次通过18/18，实际调用18，传输失败0；
- Recall@8/20仍为14/16，MRR仍为0.875，空目标仍为2/2；
- Silver exact case 从首次12/18变为13/18；
- 模型 span 从33变为32，匹配仍为27/29；
- 漏失保持2个，全部为 TARGET，且都由同角色模型 super-span 替代；
- 额外 span 为5个：TARGET 2、SCOPE 1、EXCLUSION 2；
- case 分布：exact 13、only-extra 3、missing-and-extra 2。

## 解释

资格失败具有重复性：相同两个关键目标再次因模型选择过长 TARGET span 而无法命中
冻结 R1。非必要额外 span 有轻微波动，因此 v1 并非字节确定，但不影响根因。

这不是 TARGET/SCOPE 角色互换，也不是模型合同错误。模型识别了 TARGET 角色，却没有
把外围限定语与最小完整信息项名称分开；R1 的完整 target gate 因而产生两个额外
`NO_CANDIDATES`。

诊断不判断 Silver 必然正确，也不证明现实请求都能仅靠 span 边界解决。它只允许预
注册一个不含数据例子的通用 v2 边界规则；若 v2 仍不通过，停止继续调 Prompt，转向
能容忍目标边界或非字面表达的检索表示。
