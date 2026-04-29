# A股量化交易系统 使用手册

> 版本记录见文末 [更新日志](#更新日志)

---

## 一、环境准备（首次使用）

### 1. 安装依赖

```bash
cd /Users/zhongxin/quant/backend
pip install -r requirements.txt
```

### 2. 启动 PostgreSQL

```bash
brew services start postgresql@16
```

### 3. 初始化数据库（仅首次）

```bash
/opt/homebrew/opt/postgresql@16/bin/psql -U zhongxin -d postgres -c "CREATE DATABASE quant_db ENCODING 'UTF8';"
/opt/homebrew/opt/postgresql@16/bin/psql -U zhongxin -d quant_db -f docs/init.sql
```

### 4. 全量同步历史数据（仅首次，约10-15分钟）

```bash
./run.sh fullsync
tail -f logs/sync.log   # 查看进度
```

---

## 二、日常使用

### 启动/停止服务

```bash
./run.sh start      # 后台启动
./run.sh stop       # 停止
./run.sh restart    # 重启
./run.sh status     # 查看状态
./run.sh logs       # 实时查看日志
```

服务启动后访问：
- **API文档**：http://localhost:8000/docs
- **健康检查**：http://localhost:8000/api/config

### 日志文件

| 文件 | 内容 |
|------|------|
| `logs/server.log` | API服务运行日志（信号扫描、调度任务） |
| `logs/sync.log` | 数据同步日志 |
| `logs/server.pid` | 服务进程ID |

---

## 三、自动化任务（服务运行时自动执行）

| 时间 | 任务 | 说明 |
|------|------|------|
| 盘中每3分钟 | 信号扫描 | 扫描自选股买卖信号，触发飞书/邮件通知 |
| 15:10 | 每日选股 | 全A扫描突破压力线个股，自动加入/踢出自选股 |
| 15:10 | 增量数据同步 | 更新全A日K线 + 自选股30分钟线 |

> 仅工作日运行，周末自动跳过

---

## 四、核心功能操作

### 4.1 自选股管理

**查看自选股**
```bash
curl http://localhost:8000/api/watchlist
```

**手动添加**
```bash
curl -X POST http://localhost:8000/api/watchlist/add \
  -H "Content-Type: application/json" \
  -d '["000001", "600519"]'
```

**删除**
```bash
curl -X POST http://localhost:8000/api/watchlist/remove \
  -H "Content-Type: application/json" \
  -d '["000001"]'
```

自选股分组：
- `auto` — 每日选股管道自动加入，可被自动踢出
- `manual` — 手动添加，不会被自动踢出

### 4.2 选股

**查看可用选股公式**
```bash
curl http://localhost:8000/api/formulas
```

**执行选股（在指定股票池中）**
```bash
curl -X POST http://localhost:8000/api/screen/macd_golden \
  -H "Content-Type: application/json" \
  -d '["000001", "600519", "000858"]'
```

可用公式：
| 公式key | 说明 |
|---------|------|
| `ma_cross` | MA5上穿MA20 |
| `volume_break` | 放量突破 |
| `macd_golden` | MACD金叉 |
| `kdj_oversold` | KDJ超卖金叉 |

### 4.3 信号扫描

**手动触发一次扫描**
```bash
curl -X POST http://localhost:8000/api/signals/scan-now
```

**查看当前信号**
```bash
curl http://localhost:8000/api/signals/scan
```

信号类型：
| 信号 | 类型 | 触发条件 |
|------|------|---------|
| MACD金叉 | 买入 🟢 | DIF上穿DEA |
| MACD死叉 | 卖出 🔴 | DEA上穿DIF |
| 触及布林下轨 | 买入 🟢 | 收盘≤BOLL下轨 |

### 4.4 回测

```bash
curl -X POST http://localhost:8000/api/backtest/run \
  -H "Content-Type: application/json" \
  -d '{
    "symbol": "000001",
    "strategy": "ma_kdj_pressure",
    "count": 500,
    "init_capital": 100000,
    "position_pct": 0.2
  }'
```

可用策略：
| 策略key | 说明 |
|---------|------|
| `ma_kdj_pressure` | 多周期均线+KDJ压力支撑（主策略） |
| `macd` | MACD金叉死叉 |
| `ma_cross` | MA5/MA20金叉死叉 |
| `kdj` | KDJ超卖买入超买卖出 |
| `boll` | 布林带下轨买上轨卖 |

回测参数：
| 参数 | 默认值 | 说明 |
|------|--------|------|
| `count` | 500 | K线条数（约2年） |
| `init_capital` | 100000 | 初始资金 |
| `position_pct` | 1.0 | 仓位比例（0.2=1/5仓） |
| `commission` | 0.00025 | 佣金万2.5 |
| `stamp_tax` | 0.001 | 印花税千1 |

### 4.5 K线数据

```bash
# 获取日K线（最近120条）
curl http://localhost:8000/api/kline/000001?count=120
```

### 4.6 配置通知

编辑 `config.json`：

```json
{
  "scan_interval_minutes": 3,
  "notify": {
    "feishu_webhook": "https://open.feishu.cn/open-apis/bot/v2/hook/你的webhook",
    "email": {
      "smtp_host": "smtp.qq.com",
      "smtp_port": 465,
      "user": "你的QQ邮箱@qq.com",
      "password": "QQ邮箱授权码",
      "to": "接收邮箱@example.com"
    }
  }
}
```

修改后重启服务生效：`./run.sh restart`

---

## 五、数据管理

### 手动触发增量同步

```bash
./run.sh sync
tail -f logs/sync.log
```

### 直接操作数据库

```bash
/opt/homebrew/opt/postgresql@16/bin/psql -U zhongxin -d quant_db
```

常用查询：
```sql
-- 今日涨停股
SELECT code, close, change_pct FROM kline_daily
WHERE date = CURRENT_DATE AND is_limit_up = TRUE
ORDER BY change_pct DESC;

-- 自选股列表
SELECT code, group_name, add_date, tags, reason FROM watchlist ORDER BY add_date DESC;

-- 某只股票最近10天K线
SELECT date, close, change_pct, is_limit_up FROM kline_daily
WHERE code='000001' ORDER BY date DESC LIMIT 10;

-- 信号历史
SELECT code, signal_name, signal_type, close_price, created_at
FROM signal_log ORDER BY created_at DESC LIMIT 20;
```

---

## 六、添加自定义策略

### 添加选股公式

编辑 `tdx_parser/screener.py`：

```python
def formula_my_strategy(C, H, L, O, V):
    """自定义选股：MA5上穿MA10且放量"""
    return RET(CROSS(MA(C, 5), MA(C, 10))) and RET(V) > RET(MA(V, 20))

FORMULAS["my_strategy"] = {"name": "自定义策略", "fn": formula_my_strategy}
```

### 添加信号

编辑 `signals/engine.py`，在 `SIGNALS` 字典中添加。

### 添加回测策略

编辑 `app.py` 中的 `STRATEGIES` 字典，提供 buy/sell 函数对。

---

## 七、开机自启（可选）

```bash
# 添加到 crontab
crontab -e

# 加入以下行（开机后1分钟启动）
@reboot sleep 60 && /Users/zhongxin/quant/backend/run.sh start
```

---

## 更新日志

| 日期 | 版本 | 变更内容 |
|------|------|---------|
| 2026-04-24 | v0.5 | 接入PostgreSQL，本地K线存储，涨停标记 |
| 2026-04-24 | v0.4 | 每日自动选股管道（突破压力线+自动踢出） |
| 2026-04-24 | v0.3 | 多周期均线+KDJ压力支撑策略，回测引擎 |
| 2026-03-24 | v0.2 | 定时扫描调度器，飞书/邮件通知，500只并发 |
| 2026-03-23 | v0.1 | 数据层(AKShare)，MyTT指标库，选股引擎，信号引擎 |
