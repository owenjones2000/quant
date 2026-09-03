# A股量化交易系统

基于通达信指标体系的量化交易系统，支持自动选股、信号预警、策略回测。

## 系统架构

```
┌─────────────────────────────────────────────────────────┐
│                    FastAPI (app.py)                      │
│  行情接口 │ 自选股管理 │ 选股 │ 信号 │ 回测 │ 配置      │
├─────────────────────────────────────────────────────────┤
│  调度器 scheduler.py                                     │
│  盘中: 每3分钟信号扫描  │  15:10: 每日选股管道           │
├──────────┬──────────┬──────────┬──────────┬──────────────┤
│ 数据层   │ 指标库   │ 选股引擎 │ 信号引擎 │ 回测引擎     │
│ AKShare  │ MyTT     │ screener │ signals  │ backtest     │
│ +Ashare  │          │ scanner  │          │              │
├──────────┴──────────┴──────────┴──────────┴──────────────┤
│  通知: 飞书Webhook + 邮件SMTP                            │
└─────────────────────────────────────────────────────────┘
```

## 目录结构

```
backend/
├── app.py                      # FastAPI 入口，所有REST API
├── config.py                   # 配置管理
├── config.json                 # 运行时配置（扫描间隔、通知等）
├── scheduler.py                # 定时任务调度器
├── MyTT.py                     # 通达信指标库（MA/MACD/KDJ/BOLL等）
├── MyTT_plus.py                # MyTT高级函数扩展
│
├── data/                       # 数据层
│   ├── provider.py             # AKShare数据接口（新浪源）
│   ├── Ashare.py               # Ashare行情接口（备用）
│   ├── cache.py                # 行情缓存 + 并发批量拉取
│   └── watchlist.json          # 自选股持久化存储
│
├── tdx_parser/                 # 选股引擎
│   ├── screener.py             # 通达信选股公式（MA金叉/MACD/KDJ/放量）
│   ├── daily_scanner.py        # 每日自动选股管道（突破压力线扫描+踢出）
│   └── watchlist.py            # 自选股管理（auto/manual分组）
│
├── strategies/                 # 交易策略
│   └── ma_kdj_strategy.py      # 多周期均线+KDJ压力支撑策略
│
├── signals/                    # 信号引擎
│   └── engine.py               # 信号扫描（MACD金叉/死叉/布林下轨）
│
├── backtest/                   # 回测引擎
│   └── engine.py               # 轻量回测（收益率/回撤/夏普/胜率）
│
├── notify/                     # 通知服务
│   └── sender.py               # 飞书Webhook + 邮件SMTP
│
└── docs/                       # 文档
    └── STRATEGY-CONTEXT.md     # 策略决策文档
```

## 快速开始

### 安装依赖

```bash
cd backend
pip install -r requirements.txt
```

核心依赖：
- `akshare` — A股行情数据
- `pandas` / `numpy` — 数据处理
- `fastapi` / `uvicorn` — Web API
- `apscheduler` — 定时任务
- `baostock` — 股票列表补充数据源
- `requests` — 飞书通知

### 启动服务

```bash
cd backend
uvicorn app:app --reload --port 8000
```

启动后自动开启：
- 盘中每3分钟扫描自选股信号
- 每日15:10运行选股管道

### 配置通知

编辑 `config.json`：

```json
{
  "scan_interval_minutes": 3,
  "notify": {
    "feishu_webhook": "https://open.feishu.cn/open-apis/bot/v2/hook/xxx",
    "email": {
      "smtp_host": "smtp.qq.com",
      "smtp_port": 465,
      "user": "your@qq.com",
      "password": "授权码",
      "to": "target@example.com"
    }
  }
}
```

## 数据源

| 数据源 | 用途 | 接口 |
|--------|------|------|
| AKShare (新浪) | 日K线、分钟线 | `stock_zh_a_daily` |
| AKShare (新浪) | 全A股票列表 | `stock_zh_a_spot` |
| Ashare (新浪+腾讯) | 备用行情 | `get_price()` |
| baostock | 股票列表降级 | `query_stock_basic` |

行情缓存机制：
- 缓存有效期 2.5 分钟
- 同一轮扫描每只股票只拉取一次
- 支持 10 线程并发批量拉取
- 500只股票约 15-35 秒完成

## 核心模块

### 1. 指标库 (MyTT)

直接使用通达信函数名，零学习成本：

```python
from MyTT import *

MA(CLOSE, 5)           # 5日均线
EMA(CLOSE, 12)         # 指数移动平均
MACD(CLOSE)            # → DIF, DEA, MACD
KDJ(CLOSE, HIGH, LOW)  # → K, D, J
BOLL(CLOSE)            # → UPPER, MID, LOWER
CROSS(MA(C,5), MA(C,20))  # MA5上穿MA20
RSI(CLOSE, 24)         # RSI指标
ATR(CLOSE, HIGH, LOW)  # 真实波动
```

补充实现的函数：
```python
VALUEWHEN(condition, X)  # 条件成立时取X值并保持
```

### 2. 选股引擎

#### 预置选股公式

| 公式 | 说明 |
|------|------|
| `ma_cross` | MA5上穿MA20 |
| `volume_break` | 放量突破（成交量>10日最高量且收阳） |
| `macd_golden` | MACD金叉 |
| `kdj_oversold` | KDJ超卖金叉（J<20后J上穿K） |

#### 每日自动选股管道

每日15:10自动运行：

1. 扫描范围：沪深主板 + 中小板 + 创业板（约4592只，排除北交所）
2. 入选条件：
   - 当日涨幅 ≥ 8%
   - 连续2天收盘价 > 压力线 × 1.03
   - 涨停(主板≥10%/创业板≥20%)标记为重点
3. 自动加入自选股（auto分组）
4. 踢出条件：跌破MA100 且 10天内未重新突破压力位
5. 手动添加的股票（manual分组）不会被自动踢出

#### 自选股分组

| 分组 | 来源 | 自动踢出 |
|------|------|---------|
| `auto` | 每日扫描自动选入 | ✅ 符合踢出条件时移除 |
| `manual` | 手动添加 | ❌ 不受影响 |

### 3. 信号引擎

对自选股运行信号检测，触发时推送通知：

| 信号 | 类型 | 说明 |
|------|------|------|
| MACD金叉 | 买入 | DIF上穿DEA |
| MACD死叉 | 卖出 | DEA上穿DIF |
| 触及布林下轨 | 买入 | 收盘价≤BOLL下轨 |

去重机制：同一天同一股票同一信号只通知一次。

### 4. 交易策略

#### 多周期均线+KDJ压力支撑策略

核心指标：
- KDJ双周期(5日/55日)交叉产生压力线和支撑线
- 7条均线：MA5/10/15/30/50/120/240

买入条件（优先级）：
1. P1：突破压力线后回调到MA10/MA15附近，站上确认
2. P2：新压力线形成后回调到MA10/MA15附近，站上确认
3. P3：回调到MA50/120/240附近获支撑，站上确认

站上确认 = 收盘 > MA15 且 MA5已上穿MA10

卖出条件：
1. 上涨到压力线附近(±2%)止盈
2. 突破压力线则持有
3. 反弹未能突破压力线则出局
4. 跌破MA50清仓

详见 [docs/STRATEGY-CONTEXT.md](docs/STRATEGY-CONTEXT.md)

### 5. 回测引擎

特性：
- 次日开盘价成交（避免未来函数）
- A股100股整数倍
- 佣金万2.5 + 印花税千1
- 输出：总收益率、年化收益率、最大回撤、夏普比率、胜率、盈亏比
- 对比基准（买入持有）
- 权益曲线

预置回测策略：

| 策略 | 说明 |
|------|------|
| `ma_kdj_pressure` | 多周期均线+KDJ压力支撑（自研） |
| `macd` | MACD金叉死叉 |
| `ma_cross` | MA5/MA20金叉死叉 |
| `kdj` | KDJ超卖买入超买卖出 |
| `boll` | 布林带下轨买上轨卖 |

## API 接口

### 行情
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/kline/{symbol}?count=120` | 个股日K线 |

### 自选股
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/watchlist` | 查看自选股 |
| POST | `/api/watchlist/add` | 添加（body: `["000001"]`） |
| POST | `/api/watchlist/remove` | 删除 |

### 选股
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/formulas` | 可用选股公式列表 |
| POST | `/api/screen/{formula_key}` | 执行选股 |

### 信号
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/signals` | 可用信号列表 |
| GET | `/api/signals/scan` | 扫描自选股信号 |
| POST | `/api/signals/scan-now` | 手动触发扫描 |

### 回测
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/backtest/strategies` | 可用策略列表 |
| POST | `/api/backtest/run` | 执行回测 |

回测请求示例：
```json
{
  "symbol": "000001",
  "strategy": "ma_kdj_pressure",
  "count": 500,
  "init_capital": 100000,
  "position_pct": 0.2,
  "commission": 0.00025,
  "stamp_tax": 0.001
}
```

### 配置
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/config` | 查看配置 |
| POST | `/api/config` | 更新配置 |

## 添加自定义策略

### 添加选股公式

编辑 `tdx_parser/screener.py`，添加函数并注册：

```python
def formula_my_custom(C, H, L, O, V):
    """自定义选股条件"""
    return RET(CROSS(MA(C, 5), MA(C, 10))) and RET(V) > RET(MA(V, 20))

FORMULAS["my_custom"] = {"name": "自定义选股", "fn": formula_my_custom}
```

### 添加信号

编辑 `signals/engine.py`，添加到 `SIGNALS` 字典。

### 添加回测策略

编辑 `app.py` 中的 `STRATEGIES` 字典，提供 buy/sell 信号函数对。

## 定时任务

| 任务 | 时间 | 说明 |
|------|------|------|
| 信号扫描 | 盘中每3分钟 | 9:30-11:30, 13:00-15:00 |
| 每日选股 | 15:10 | 全A扫描+自选股踢出 |

仅工作日运行，周末自动跳过。

## 技术栈

| 组件 | 技术 |
|------|------|
| 行情数据 | AKShare (新浪源) + Ashare (备用) |
| 指标计算 | MyTT (通达信函数Python实现) |
| Web框架 | FastAPI |
| 任务调度 | APScheduler |
| 通知 | 飞书Webhook + SMTP邮件 |
| 数据存储 | JSON文件 (自选股/配置) |
