# Cybersoul MVP 项目结构设计

本文档当前只保留项目结构设计，用于明确 `Cybersoul` 的代码仓库组织方式。

---

## 1. 一级、二级目录总览

```text
cybersoul/
├── frontend/                                   # 前端展示层
├── agents/                                     # 陪伴体智能体系统
├── world/                                      # 赛博世界系统
├── backend/                                    # 后端服务入口层
├── config/                                     # 顶层全局配置
├── infra/                                      # 基础设施
├── tests/                                      # 测试
└── docs/                                       # 文档
```

---

## 2. frontend 模块

```text
frontend/
├── user-app/                                   # 用户前台
│   ├── app/                                    # 路由与页面入口
│   ├── components/                             # 页面组件
│   ├── features/                               # 状态页/对话页/动态页/关系页
│   ├── stores/                                 # 前端状态管理
│   └── services/                               # 前端 API 请求封装
│
├── admin-app/                                  # 内部观测台
│   ├── app/                                    # 路由与页面入口
│   ├── components/                             # 页面组件
│   ├── features/                               # 世界状态/记忆/日志/轨迹观测
│   ├── stores/                                 # 前端状态管理
│   └── services/                               # 前端 API 请求封装
│
└── design-system/                              # 设计系统
    ├── tokens/                                 # 颜色/字体/间距/动效变量
    ├── primitives/                             # Button/Card/Input 等基础组件
    ├── patterns/                               # 状态卡/动态卡/分享卡模式
    ├── assets/                                 # 图标/插画/静态资源
    └── docs/                                   # UI 规范说明
```

---

## 3. agents 模块

```text
agents/
├── core/                                       # 核心框架层
│   ├── base/                                   # BaseAgent/BaseMode/BaseTool
│   ├── llm/                                    # 统一 LLM 接口与模型适配
│   ├── messaging/                              # Message/Event/ModeResult
│   ├── config/                                 # Agent 配置体系
│   └── exceptions/                             # Agent 异常体系
│
├── runtime/                                    # 运行时层
│   ├── companion/                              # 陪伴体主运行时
│   ├── routing/                                # mode_router/event_router
│   ├── policies/                               # 频控/边界/安全守卫
│   ├── execution/                              # step 执行/结果应用/重试
│   └── scheduling/                             # 主动触达/反思/规划调度
│
├── roles/                                      # 具体 Agent 角色
│   ├── companion/                              # 主陪伴体 Agent
│   ├── planner/                                # 每日规划 Agent
│   ├── reflection/                             # 反思 Agent
│   ├── trace/                                  # 痕迹生成 Agent
│   └── internet/                               # 互联网会话 Agent
│
├── modes/                                      # 范式实现层
│   ├── react/                                  # ReAct
│   ├── plan_solve/                             # Plan-and-Solve
│   ├── reflection/                             # Reflection
│   ├── scoring/                                # 行为评分/概率校准
│   └── shared_logic/                           # 范式共享逻辑
│
├── tools/                                      # 工具系统层
│   ├── base/                                   # Tool 基类
│   ├── registry/                               # 工具注册机制
│   ├── chain/                                  # 工具链管理
│   ├── executor/                               # 同步/异步执行器
│   └── builtin/                                # 内置工具集
│
├── memory/                                     # 记忆系统模块
│   ├── infrastructure/                         # manager/base/config/item
│   ├── types/                                  # working/episodic/relationship/self/internet
│   ├── storage/                                # vector/document/graph store
│   ├── embedding/                              # DashScope/Local/TFIDF
│   └── rag/                                    # RAG 系统
│
├── context/                                    # 上下文工程层
│   ├── builder/                                # ContextBuilder
│   ├── packets/                                # ContextPacket 等结构
│   ├── compression/                            # 压缩与摘要
│   ├── notes/                                  # 结构化笔记
│   └── templates/                              # 上下文模板
│
├── protocols/                                  # 通信协议层
│   ├── mcp/                                    # MCP 风格协议
│   ├── a2a/                                    # A2A 风格协议
│   ├── contracts/                              # 请求/响应契约
│   └── adapters/                               # 协议适配器
│
└── prompts/                                    # Prompt 资产层
    ├── system/                                 # 系统提示
    ├── roles/                                  # 角色提示
    ├── modes/                                  # 范式提示
    ├── tasks/                                  # 任务提示
    └── evals/                                  # 评测/对齐提示
```

---

## 4. world 模块

```text
world/
├── core/                                       # 世界核心层
│   ├── world/                                  # World 聚合根
│   ├── manager/                                # WorldManager
│   ├── clock/                                  # 世界时钟/共时机制
│   ├── state/                                  # WorldState/Snapshot
│   └── config/                                 # 世界配置
│
├── engine/                                     # 世界运行引擎
│   ├── tick/                                   # 世界 tick 推进
│   ├── scheduler/                              # 活动块与时段调度
│   ├── transitions/                            # 状态转移
│   ├── action_space/                           # 动作空间生成
│   └── projection/                             # 面向用户的结果投射
│
├── entities/                                   # 世界实体抽象
│   ├── locations/                              # 地点实体
│   ├── world_agents/                           # world agent 实体
│   ├── incidents/                              # 世界事件实体
│   ├── activities/                             # 活动块实体
│   └── routines/                               # 日程/节律实体
│
├── definitions/                                # 具体内容定义
│   ├── locations/                              # 公寓/咖啡馆/公园...
│   ├── world_agents/                           # 朋友/店员/同事/网友...
│   ├── incidents/                              # 天气/节日/热点/压力事件...
│   └── activities/                             # 睡觉/通勤/工作/独处/刷手机...
│
├── rules/                                      # 世界规则层
│   ├── location_rules/                         # 地点进入和可用规则
│   ├── activity_rules/                         # 活动块规则
│   ├── incident_rules/                         # 事件触发规则
│   ├── transition_rules/                       # 状态转移规则
│   └── interruption_rules/                     # 中断/插入规则
│
├── generators/                                 # 世界内容生成层
│   ├── routines/                               # 日常节律生成
│   ├── incidents/                              # 事件生成
│   ├── ambience/                               # 场景氛围生成
│   └── internet_triggers/                      # 互联网会话触发器
│
├── projections/                                # 用户可见投射层
│   ├── state_cards/                            # 状态卡投射
│   ├── traces/                                 # 动态流投射
│   ├── dialogue_hints/                         # 对话自然提及素材
│   └── summaries/                              # 今日摘要/阶段摘要
│
├── storage/                                    # 世界存储层
│   ├── repositories/                           # 世界读写仓储
│   ├── models/                                 # 持久化模型
│   ├── snapshots/                              # 快照存储
│   └── serializers/                            # 序列化
│
└── adapters/                                   # 外部世界适配
    ├── weather/                                # 天气
    ├── calendar/                               # 节日/日期
    ├── trends/                                 # 热点/趋势
    └── feeds/                                  # 可接入的内容源
```

---

## 5. backend 模块

```text
backend/
├── api/                                        # FastAPI / BFF
│   ├── routes/                                 # 路由
│   ├── schemas/                                # API 输入输出 DTO
│   ├── dependencies/                           # 依赖注入
│   ├── middleware/                             # 中间件
│   └── controllers/                            # 接口编排
│
├── app/                                        # 启动与装配
│   ├── bootstrap/                              # 应用初始化
│   ├── containers/                             # 服务装配
│   ├── lifecycle/                              # 启停生命周期
│   └── settings/                               # 服务配置
│
├── workers/                                    # 后台任务
│   ├── scheduler/                              # 定时任务入口
│   ├── jobs/                                   # tick/reflection/proactive jobs
│   ├── queues/                                 # 队列消费
│   └── handlers/                               # 任务处理器
│
└── observability/                              # 观测与运维
    ├── logging/                                # 日志
    ├── tracing/                                # trace/run 追踪
    ├── metrics/                                # 指标
    └── dashboards/                             # 观测面板配置
```

---

## 6. config 模块

```text
config/
├── env/                                        # 环境变量定义
│   ├── local/                                  # 本地开发环境
│   ├── staging/                                # 测试环境
│   ├── production/                             # 生产环境
│   └── examples/                               # 示例配置
│
├── constants/                                  # 全局常量
│   ├── agent/                                  # agent 常量
│   ├── world/                                  # world 常量
│   ├── api/                                    # api 常量
│   └── product/                                # 产品常量
│
└── feature_flags/                              # 功能开关
    ├── frontend/                               # 前端功能开关
    ├── agents/                                 # agent 功能开关
    ├── world/                                  # world 功能开关
    └── backend/                                # backend 功能开关
```

---

## 7. infra 模块

```text
infra/
├── docker/
│   ├── local/                                  # 本地开发容器
│   ├── staging/                                # 测试环境容器
│   ├── production/                             # 生产环境容器
│   └── base/                                   # 基础镜像
│
├── migrations/
│   ├── postgres/                               # PostgreSQL 迁移
│   ├── qdrant/                                 # 向量索引初始化
│   ├── neo4j/                                  # 图数据库初始化
│   └── seeds/                                  # 初始种子数据
│
└── scripts/
    ├── dev/                                    # 本地开发脚本
    ├── ops/                                    # 运维脚本
    ├── deploy/                                 # 部署脚本
    └── data/                                   # 数据处理脚本
```

---

## 8. tests 模块

```text
tests/
├── frontend/
│   ├── user-app/                               # 用户前台测试
│   ├── admin-app/                              # 观测台测试
│   └── design-system/                          # 设计系统测试
│
├── agents/
│   ├── modes/                                  # ReAct/Plan/Reflection 测试
│   ├── memory/                                 # 记忆测试
│   ├── tools/                                  # 工具测试
│   └── runtime/                                # 运行时测试
│
├── world/
│   ├── engine/                                 # 世界引擎测试
│   ├── rules/                                  # 规则测试
│   ├── projections/                            # 投射测试
│   └── storage/                                # 存储测试
│
└── backend/
    ├── api/                                    # API 测试
    ├── workers/                                # worker 测试
    ├── observability/                          # 观测测试
    └── e2e/                                    # 端到端测试
```

---

## 9. docs 模块

```text
docs/
├── product/
│   ├── prd/                                    # 产品需求
│   ├── prototype/                              # 原型说明
│   ├── mvp/                                    # MVP 方案
│   └── roadmap/                                # 路线图
│
├── architecture/
│   ├── agents/                                 # Agent 架构说明
│   ├── world/                                  # World 架构说明
│   ├── frontend/                               # 前端架构说明
│   └── backend/                                # 后端架构说明
│
└── api/
    ├── public/                                 # 前台 API
    ├── internal/                               # 内部 API
    ├── events/                                 # 事件契约
    └── examples/                               # 接口示例
```

