# 工作区索引

> 记录本项目中各个非识别性开发者/代理别名的 AI 协作工作。

---

## 目录结构

```text
.trellis/
|-- tasks/                 # 共享活动任务与 archive/YYYY-MM/
+-- workspace/
    |-- index.md           # 开发者概览
    +-- {developer}/
        |-- index.md       # 个人会话索引
        +-- journal-N.md   # 顺序会话日志
```

`{developer}` 必须是不对应受保护环境真实人员的别名，不能保存真实身份或可反向
识别信息。

## 活动开发者

| 别名 | 最近活动 | 会话数 | 活动文件 |
|---|---|---:|---|
| bobot | 2026-07-28 | 0 | `bobot/journal-1.md` |

## 初始化

新别名执行：

```bash
python3 ./.trellis/scripts/init_developer.py <alias>
```

返回工作时：

```bash
python3 ./.trellis/scripts/get_developer.py
cat .trellis/workspace/$(python3 ./.trellis/scripts/get_developer.py)/index.md
```

## 日志规则

- 每个 journal 文件最多 2000 行，达到限制后创建 `journal-{N+1}.md`；
- 新建文件时同步更新个人 `index.md`；
- 必须遵守 `.trellis/spec/backend/development-data-boundary.md`；
- 只记录脱敏结论、公开提交哈希、固定错误码和聚合验证结果；
- 不复制受保护代码/数据、真实字段名、提示词、trace、原始日志或内部路径；
- 从受保护环境获得的材料必须先完成严格脱敏和逐字节人工批准；
- 新增任务说明、项目规范和日志优先使用中文；命令、协议字段、代码标识及已有
  清晰英文无需为形式统一而改写。

## 会话模板

```markdown
## 会话 {N}：{标题}

**日期**：YYYY-MM-DD
**任务**：{task-name}
**分支**：`{branch-name}`

### 摘要

{一行脱敏摘要}

### 主要变更

- {变更 1}
- {变更 2}

### Git 提交

| Hash | Message |
|---|---|
| `abc1234` | {提交信息} |

### 验证

- [通过] {聚合验证结果}

### 状态

[完成] / [进行中] / [阻塞]

### 下一步

- {下一步}
```
