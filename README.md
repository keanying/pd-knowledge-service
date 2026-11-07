# pd_knowledge_service
PDK 知识服务：知识库 · 检索 · 知识更新（Python）

所有知识类文档经 MinerU 解析、切片，存入 Milvus 向量库，通过 PDA（hermes-agent，对应客户架构中的 PAP 智能体平台）对外提供问答；权限由 PDS 统一控制。

## 文档

| 文档 | 说明 |
|---|---|
| [00-总体架构与PDA接入方案](docs/00-总体架构与PDA接入方案.md) | PDK / PDS / PDA 总体架构、与客户架构的对应关系、身份透传、权限点目录 |
| [01-PDK产品功能文档](docs/01-PDK产品功能文档.md) | 功能清单、问答门户、PDA 管理、数据模型、接口清单、验收要点 |
| [02-PDK技术方案](docs/02-PDK技术方案.md) | 技术选型、接入流水线、Milvus 设计、检索与权限过滤、hermes 插件、POC 清单、里程碑 |

相关仓库：[pd_centralized_permission](https://github.com/keanying/pd_centralized_permission)（PDS 统一权限）
