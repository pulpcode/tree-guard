# Value Owner / Instance Boundary Retrospective

## Bug Analysis：字段所有者语义反复不清

### 1. Root Cause Category

- **Category**：A（Missing Spec）+ E（Implicit Assumption）
- **Specific Cause**：Blueprint 过去只约束节点 kind、value type 和 cardinality，
  没有声明“标量值属于当前资源单例、某条重复记录，还是仅用于组织的类别”。
  生成器因此把看似自然的主体名统一当作 CONCEPT，Schema 合法但业务指代不完整。

### 2. Why Fixes Failed

1. 只改场景措辞：没有改变树内字段所有者，审核时仍无法回答值属于谁。
2. 把全部 CONCEPT 判为不可带属性：修复过度，忽略了整棵树描述单一资源时，
   单例章节可以合理拥有资源级标量。
3. 把主体统一转为 class：实例边界得到表达，但旧场景提示未同步，QS-C04 因而
   同时产生类型、值类型和基数冲突。

### 3. Prevention Mechanisms

| Priority | Mechanism | Specific Action | Status |
|---|---|---|---|
| P0 | Contract | 每个节点声明 `semantic_role` 与 `value_owner_scope` | DONE |
| P0 | Deterministic validation | 组织概念直接带标量、class 基数与 owner scope 不一致时固定失败 | DONE |
| P0 | Test coverage | 同时覆盖重复 class、单例 class、单例 CONCEPT 和非法组织 CONCEPT | DONE |
| P0 | Scenario review | 树结构变化后逐条复核 primary risk，不允许引入次生冲突 | DONE |
| P0 | Tree-scope review | 场景审核之外必填整树单例/记录边界决定，并写入导出 | DONE |
| P1 | Review UI | 显示“组织分类／单例章节／重复记录／单例记录”和字段归属 | DONE |

### 4. Systematic Expansion

- **Similar Issues**：类别默认规则与单条实例状态、集合汇总与实例字段、物理区域
  单例与区域记录集合、嵌套重复记录。
- **Design Improvement**：把 kind 与语义角色分开；`CONCEPT` 不是“绝不带属性”，
  `PROPERTY` 也不只代表标量。
- **Process Improvement**：先做完整值所有者预审，再做场景预审和独立的
  tree-scope 人工决定；任一结构修订都重跑“主要风险单一性”检查，失败则创建
  新 run，不能原地清洗。场景全部接受不再等价于整树结构已获批准。

### 5. Knowledge Capture

- [x] Dataset Charter 增加值所有者停线规则。
- [x] Semantic Blueprint 固化四类合法边界。
- [x] 生成器与单元测试固化确定性校验。
- [x] 当前任务记录根因与失败修复。
- [x] 审核界面展示实例边界并完成渲染测试。

本复盘只使用当前 clean-room 虚构数据与聚合合同，不包含真实树、受保护字段、
模型流量或生产诊断。
