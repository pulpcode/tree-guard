# H2 本地开源 Embedding 选型研究

## 问题与范围

核对日期：2026-08-05。目标是在不改变 H1 节点字段、R2 lexical leg、Top-40、
RRF 1:1 和安全门的前提下，选择一个能在当前外网开发机和未来内网环境本地运行的
中文 embedding profile。本文只依据公开模型资料和当前仓库依赖，不使用受保护数据。

## 本机与仓库约束

- 当前开发机为 Intel x86_64、6 核、16GB 内存、AMD 4GB 显存；不能依赖 Apple
  Silicon MPS，也不假设 CUDA；
- 仓库默认环境没有 torch、transformers、sentence-transformers、ONNX Runtime、
  MLX 或 llama.cpp；
- H1 已固定 512 维文档/查询表示与纯 Python 余弦/RRF core；H2 应避免同时改维度、
  文档字段、融合和模型；
- 重型本地推理依赖先放在隔离实验环境，不直接升级为默认产品依赖。

## 候选

### A. BAAI/bge-small-zh-v1.5（推荐）

- 官方模型卡声明中文、24M 参数、512 维、MIT license；`model.safetensors` 约
  95.8MB；
- 官方 Transformers 用法为 `[CLS]` pooling 后 L2 normalize；短查询检索建议只给
  query 添加固定中文 instruction，passage 不添加；
- 与 H1 维度一致，CPU 资源最小，允许把主要变量收缩为“本地 embedding profile”。

冻结来源：

- Repository：<https://huggingface.co/BAAI/bge-small-zh-v1.5>
- Revision：`7999e1d3359715c523056ef9478215996d62a620`
- `model.safetensors` SHA-256：
  `354763b9b1357bc9c44f62c6be2276321081ed2567773608c0d0785b61d5a026`

限制：模型较旧且公开 C-MTEB 不能替代本项目信息树召回验证；固定 query instruction
属于该模型 profile，必须在新数据生成前写入合同。

### B. Qwen/Qwen3-Embedding-0.6B

官方模型卡声明 0.6B 参数、最高 1024 维且支持 32–1024 自定义维度、100+语言和
instruction-aware。能力上更现代，但参数量约为 A 的 25 倍；当前 Intel/16GB CPU
环境的时延和运行时复杂度明显更高。它适合作为未来内网 GPU 候选，不适合作为 H2
最小 CPU 变量。

来源：<https://huggingface.co/Qwen/Qwen3-Embedding-0.6B>

### C. H1 节点表示增强或 reranker

这两条可能改善 H1 剩余漏失，但会改变文档语义或增加新的排序模型，无法回答“仅换为
本地 embedding 是否足够”。保留为 H2 失败后的新实验，不并入 H2。

## 决策

H2 选择 A。使用精确 revision 的 safetensors，512 维、float32、CPU、`eval()`、
无梯度、固定 tokenizer truncation、`[CLS]` pooling 和 L2 normalize。query 添加
模型官方固定 instruction，node passage 不添加。

运行时采用隔离、版本固定的实验环境；默认 TreeGuard 安装不新增 torch/transformers。
本地 Provider 保持和 H1 相同的显式批处理接口，但使用独立 H2 模型/profile/index
版本，禁止把 H1 与 H2 索引互相读取或重新标记。

## 限制

- 公开 benchmark 只支持候选筛选，不构成 TreeGuard 能力证据；
- H2 必须使用新的开发分母，不能在 H1 24 条或 R2 密封 28 条上选参数；
- 当前选型只证明 CPU 可验证性，不代表未来内网生产硬件已经冻结。
