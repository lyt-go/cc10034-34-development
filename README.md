# 数据安全计算与隐私保护平台

面向数据脱敏、差分隐私、安全聚合与访问审计的数据安全计算与隐私保护平台。

这是一个前后端分离的管理平台：前端 Vue 3 + Vite + TypeScript，后端 FastAPI（Python）。
两边各自独立启动，前端 dev server 已关掉自动打开页面，启动后按终端打印的地址手工打开。

## 目录结构

```text
.
├── frontend/                 Vue 3 + Vite + TypeScript 前端
│   ├── src/views/WorkbenchView.vue|tsx  全部模块共享工作台
│   ├── src/data/modules.ts              18个业务模块配置
│   ├── src/api/              统一请求封装
│   └── vite.config.ts        dev server 配置（open: false）
├── backend/                  FastAPI（Python） 后端
│   ├── app/routers/resource.py  通用查询/导出/登记/动作接口
│   ├── app/services/<key>.py    每个模块独立领域逻辑
│   ├── app/services/base.py     共享服务骨架
│   └── app/store.py          内存数据仓库与示例数据
├── .gitignore
└── docker-compose.yml
```

## 启动

### 后端

```bash
cd backend
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
./run.sh
```

健康检查：`curl http://127.0.0.1:8000/api/health`

### 前端

```bash
cd frontend
npm ci
npm run dev
```

前端默认监听 `http://127.0.0.1:5173/`，dev server 不会自动打开浏览器，
需要自己访问。`/api` 由 vite 代理到后端 `http://127.0.0.1:8000`。

## 业务模块

| 模块 | 目录 | 业务对象 | 主要字段 |
| --- | --- | --- | --- |
| 脱敏规则 | `mask_rule` | 脱敏规则 | 规则编号、目标字段、脱敏算法 |
| 隐私预算 | `privacy_budget` | 隐私预算 | 预算编号、数据集名称、总预算Epsilon |
| 噪声引擎 | `noise_engine` | 噪声配置 | 配置编号、噪声机制、Epsilon值 |
| 安全聚合 | `secure_agg` | 聚合任务 | 任务编号、数据源列表、聚合函数 |
| 访问审计 | `access_audit` | 审计记录 | 记录编号、访问主体、目标资源 |
| 授权审批 | `grant_approval` | 授权申请 | 申请编号、申请人、目标数据 |
| 分级分类 | `classify_tag` | 分级标签 | 标签编号、数据资源、安全等级 |
| 联邦训练 | `federated_train` | 训练任务 | 任务编号、参与节点、模型类型 |
| 梯度加密 | `gradient_encrypt` | 加密配置 | 配置编号、加密方案、密钥长度 |
| 假名化 | `pseudonym` | 假名映射 | 映射编号、原始标识、假名标识 |
| K匿名检查 | `k_anonymity` | 匿名检查 | 检查编号、数据集名称、准标识符列 |
| 差分查询 | `differential_sql` | 查询记录 | 查询编号、查询语句、查询用户 |
| 密文索引 | `encrypt_index` | 索引条目 | 条目编号、加密域、索引类型 |
| 数据水印 | `watermark` | 水印记录 | 水印编号、目标数据集、水印算法 |
| 同意登记 | `consent_registry` | 同意记录 | 记录编号、数据主体、处理目的 |
| 风险扫描 | `risk_scan` | 扫描任务 | 任务编号、扫描范围、扫描规则 |
| 策略下发 | `deploy_policy` | 策略分发 | 分发编号、策略内容、目标节点 |
| 异常检测 | `anomaly_detect` | 异常规则 | 规则编号、检测维度、检测算法 |

## 约定

- 全部模块共享`frontend/src/views/WorkbenchView.vue|tsx`和一套资源路由。
- 每个模块仍保留独立`backend/app/services/<模块>.py`；纯前端保留
  `frontend/src/domain/<模块>.ts`，用于承载真实业务差异并维持36题位容量。
- 列表接口统一返回 `{ items, total, page, size }`，动作接口统一返回 `{ ok, message }`。
- 状态流转只允许在 `app/services` 里改，路由层不做业务判断。

## 预算告警核查（告警 → 预算核查回执 → 纠正受理）

异常检测工作台右上角「告警核查」进入独立的告警核查页（路由 `/alert_check`，
侧栏「告警核查」同样可达）。值班员把预算告警与真实`预算流水`对照，服务端生成
**预算核查回执**；在回执上填写核实应退金额并提交**纠正请求**，再到
**隐私预算页 → 详情/纠正受理**（或核查页的深链）接受/拒绝。

三条服务端铁律（`backend/app/services/alert_review.py`，带进程内结算锁）：

1. **重复上报只计一次扣款**：同`告警指纹/关联凭证号`的多张告警合并为一组，
   回执给出上报笔数、重复笔数；同凭证的重复扣费流水也按凭证去重。
2. **数据集隔离**：只有同数据集流水可核销；同金额但异数据集的流水进
   「排除流水」，绝不计入认定扣费。
3. **同一原因只退一次**：退款以`业务凭证号 + 退款原因`幂等。原查询入口
   （差分查询行内「申请退款」或 `/api/alert-check/refunds`）送来的通常是
   `待定退款`，不动余额；隐私预算页接受纠正时优先把这笔待定退款核准为最终
   支付流水（`disposition_code=merged_existing_pending`）。若退款已被直接核准，
   后接受的纠正标记`already_paid`且本次余额变动为 0；若纠正先支付，迟到的同因
   退款会被记为`重复退款已拦截`。`balance_event` 时间线记录究竟是哪次操作改变了余额。

接口前缀 `/api/alert-check`：

- `GET  /board` 聚合看板；`GET /budgets/{id}/detail` 预算详情（流水/纠正/事件）
- `POST /scenario` 构造演练：0.30 扣费 + 2 张重复告警 + 异数据集诱饵 + 可选 0.10 待定退款
- `POST /alerts/{id}/receipt` 生成预算核查回执
- `POST /receipts/{id}/correction` 提交纠正请求
- `POST /corrections/{id}/accept|reject` 隐私预算页受理
- `POST /refunds` 原查询入口退款；`POST /txns/{id}/approve|reject` 直接核准/驳回退款

新资源 `budget_alert / budget_txn / verification_receipt / correction_request`
也都挂在通用 `/api/{module}` 资源路由下（含中文动作名，如
`POST /api/correction_request/{id}/actions {"action":"接受纠正"}`）。
种子数据内置一组完整场景：`CHG-2611-030` 扣费 0.30、两张重复告警
`BALM-2611-030-A/B`、异数据集诱饵 `TXN-2611-031-C`、迟到的 0.10 待定退款
`RFD-2611-010-Q`（挂在隐私预算 `PRIV-ALERT-01` / id=4 下）。


领域：数据工程
子方向：数据分析与数据应用
