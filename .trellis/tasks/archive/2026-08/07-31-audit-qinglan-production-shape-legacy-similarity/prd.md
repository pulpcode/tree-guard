# 冻结后审计青岚生产形状候选与旧回归集相似度

## Goal

对已冻结的 `qinglan-library-production-shape-v1-run-003` 执行独立只读相似度
审计，只判断候选是否与旧消防回归集存在明显结构、命名、文本或模板雷同。

## Confirmed Decisions

- 生成与人工审核阶段已经结束，13 个候选工件由
  `freeze-manifest.json` 逐字节绑定。
- 复用既有固定算法与阈值，不根据本次结果调整。
- 旧数据只在审计进程内读取；输出只能包含聚合计数、比例、阈值、finding code
  和 `ACCEPT`／`REJECT`。
- 审计结果不得反馈给 Blueprint 或生成器；`REJECT` 只会拒绝冻结候选。

## Requirements

- 先验证冻结清单中的全部 13 个条目，任一字节变化都在读取旧 fixture 前失败。
- 使用既有 Unicode NFKC、2/3/4 字符 n-gram Jaccard、分支/路径/child vector、
  subject/facet 与模板指纹算法。
- 拒绝阈值与既有审计任务完全一致。
- 不输出旧节点名称、路径、场景正文、组合文本、逐对命中或低熵摘要。
- 保持 `source_class=CLEANROOM_SYNTHETIC`、`fictional=true`、
  `derived_from_real=false`、`gold_eligible=false`、`patch_eligible=false`。
- 不调用 Web、外部模型、真实仓库或受保护环境。

## Acceptance Criteria

- [x] 13 个冻结工件的逐字节验证通过后才加载旧 fixture。
- [x] 七类拒绝指标和两个结构诊断指标确定性生成。
- [x] 输出不含旧语义正文或逐对结果。
- [x] 审计只接受或拒绝，不修改冻结候选或生成器。
- [x] 聚焦审计测试、生产形状数据测试和 `git diff --check` 通过。

## Result

审计结论为 `ACCEPT`，`finding_codes=[]`。结果仅保留聚合指标，没有输出旧节点
名称、路径、场景正文或逐对命中。

本结论不授予 Gold、不证明生产准确率，也不会指导生成器修改。

验证结果：25 项聚焦测试、291 项完整后端测试、6 项 Trellis 测试、13 项前端
测试、前端生产构建和 `git diff --check` 均通过。

## File Ownership

- `.trellis/tasks/07-31-audit-qinglan-production-shape-legacy-similarity/`
- `artifacts/fictional-validation/qinglan-library-production-shape-v1-run-003/legacy-similarity-audit.json`
- 冻结候选的 `promotion-checklist.json` 仅在审计完成后记录聚合结论。

既有审计脚本与测试不需要修改。不得修改冻结清单列出的 13 个工件、生成器、
Blueprint、树、场景、正式 fixture、数据集注册表或 Agent 实现。

## Out of Scope

- 不在审计任务内修改生成器规避结果。
- 不读取旧生成器源码；只读旧 fixture。
- 不 stage、commit、push、merge、rebase 或归档。
