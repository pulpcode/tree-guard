# Retrieval 角色模型 v1 安全差异诊断预注册

## 目的

首次冻结 v1 已判定 FAIL。本诊断只解释 Silver 差异的形状，不重新判定资格、不覆盖
首次结果，也不修改 Prompt、R1、合同、Oracle、数据、分母或门槛。

## 唯一新增输出

对18条请求在进程内比较模型与 Silver span，只公开聚合计数：

- missing/extra span 按 TARGET、SCOPE、EXCLUSION 分组；
- exact、only-extra、only-missing、missing-and-extra 的 case 数；
- 漏失 Silver span 与模型额外 span 的关系：同文本错角色、模型同角色 super-span、
  模型同角色 sub-span、其他；
- missing TARGET 的 case 数。

不公开或持久化场景身份、请求正文、span 文本、位置、树/节点、hash、请求或响应。

## 运行与解释

- 使用相同 `qwen3.6-35b-a3b`、v1 Prompt、温度0与18条虚构请求；
- 首发18次，合同失败最多重试一次；
- 本次只标记 `DIAGNOSTIC_REPEAT`，不参与原资格门槛；
- 若 Recall、Silver aggregate 或差异类别与首次结果漂移，先归因重复性，不据此调参；
- 若稳定，诊断类别只能用于预注册一个通用 v2 语义规则，不能修改 Silver 或 R1。
