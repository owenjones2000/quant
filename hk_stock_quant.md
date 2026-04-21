# 港股量化交易完整指南（macOS / 2026）

---

## 一、技术栈总览

| 层级 | 工具 | 说明 |
|------|------|------|
| 交易接口 | Futu OpenAPI (futu-api) | 港股/美股实盘+仿真，macOS 原生支持 |
| 数据源（免费） | AKShare | 港股历史日线/分钟线，免费无限制 |
| 数据源（实时） | Futu OpenAPI | 实时 tick/分钟线，需开富途账户 |
| 回测框架 | Backtrader | 最成熟的 Python 回测框架，支持港股数据 |
| 策略开发 | Python + pandas + ta-lib | 标准量化开发栈 |
| 可视化 | matplotlib / plotly | 回测结果图表 |

> 富途 OpenAPI 是港股量化的最佳选择：免费、支持 macOS、有完整 Python SDK、支持港股+美股+A股。

---

## 二、环境安装

### 前置条件

已有 `~/vnpy_env` 虚拟环境（Python 3.11），直接复用：

```bash
source ~/vnpy_env/bin/activate
```

或新建独立环境：

```bash
/opt/homebrew/bin/python3.11 -m venv ~/hkquant_env
source ~/hkquant_env/bin/activate
```

### 安装依赖

```bash
pip install futu-api backtrader akshare pandas numpy matplotlib ta-lib
```

> 如果 ta-lib 安装失败，先用 brew 安装 C 库：
> ```bash
> brew install ta-lib
> pip install ta-lib
> ```

### 安装富途客户端（必须）

Futu OpenAPI 需要本地运行 **FutuOpenD** 守护进程作为网关：

1. 下载 FutuOpenD：https://www.futunn.com/download/openAPI
2. 安装并启动（macOS 直接双击）
3. 登录富途牛牛账号（需要开户，港股账户免费开）

---

## 三、富途账户开通

- 官网：https://www.futunn.com/
- 香港居民：HKID + 地址证明，线上开户，1-3 个工作日
- 内地居民：身份证 + 银行卡，支持远程视频开户
- 港股交易佣金：**终身 0 佣金**（富途主打）
- 仿真账户：开户后自动获得，无需入金即可测试 API

---

## 四、数据源详解

### 1. AKShare（免费历史数据）

```python
import akshare as ak

# 港股历史日线（前复权）
df = ak.stock_hk_hist(symbol="00700", period="daily",
                      start_date="20230101", end_date="20241231",
                      adjust="qfq")
print(df.head())
# 返回列：日期, 开盘, 收盘, 最高, 最低, 成交量, 成交额, 振幅, 涨跌幅

# 港股实时行情
df_rt = ak.stock_hk_spot_em()
print(df_rt[df_rt['代码'] == '00700'])

# 港股分钟线（近期数据）
df_min = ak.stock_hk_hist_min_em(symbol="00700", period="60",
                                  start_date="2024-01-01 09:30:00",
                                  end_date="2024-12-31 16:00:00",
                                  adjust="qfq")
```

常用港股代码：
- `00700` 腾讯  `09988` 阿里巴巴  `03690` 美团
- `00005` 汇丰  `00941` 中国移动  `02318` 中国平安
- `02800` 盈富基金（恒指ETF）

### 2. Futu OpenAPI（实时数据 + 下单）

```python
import futu as ft

# 连接 FutuOpenD（需先启动客户端）
quote_ctx = ft.OpenQuoteContext(host='127.0.0.1', port=11111)

# 获取实时报价
ret, data = quote_ctx.get_market_snapshot(['HK.00700', 'HK.09988'])
if ret == ft.RET_OK:
    print(data[['code', 'last_price', 'volume', 'turnover']])

# 订阅实时 tick
ret, data = quote_ctx.subscribe(['HK.00700'], [ft.SubType.TICKER])

# 获取历史 K 线
ret, data, page_req_key = quote_ctx.request_history_kline(
    'HK.00700',
    start='2023-01-01',
    end='2024-12-31',
    ktype=ft.KLType.K_DAY,
    autype=ft.AuType.QFQ  # 前复权
)
print(data)

quote_ctx.close()
```

---

## 五、回测框架（Backtrader）

### 基础双均线策略回测

```python
import backtrader as bt
import akshare as ak
import pandas as pd

# 1. 从 AKShare 获取数据
def get_hk_data(symbol, start, end):
    df = ak.stock_hk_hist(symbol=symbol, period="daily",
                          start_date=start, end_date=end, adjust="qfq")
    df.columns = ['date', 'open', 'close', 'high', 'low',
                  'volume', 'turnover', 'amplitude', 'pct_change',
                  'change', 'turnover_rate']
    df['date'] = pd.to_datetime(df['date'])
    df = df.set_index('date')
    df['openinterest'] = 0
    return df[['open', 'high', 'low', 'close', 'volume', 'openinterest']]

# 2. 定义策略
class DoubleMaStrategy(bt.Strategy):
    params = (('fast', 10), ('slow', 30),)

    def __init__(self):
        self.fast_ma = bt.indicators.SMA(period=self.p.fast)
        self.slow_ma = bt.indicators.SMA(period=self.p.slow)
        self.crossover = bt.indicators.CrossOver(self.fast_ma, self.slow_ma)

    def next(self):
        if not self.position:
            if self.crossover > 0:       # 金叉买入
                self.buy()
        elif self.crossover < 0:         # 死叉卖出
            self.close()

# 3. 运行回测
cerebro = bt.Cerebro()
cerebro.addstrategy(DoubleMaStrategy, fast=10, slow=30)

df = get_hk_data("00700", "20230101", "20241231")
data = bt.feeds.PandasData(dataname=df)
cerebro.adddata(data)

cerebro.broker.setcash(100000)          # 初始资金 10 万港币
cerebro.broker.setcommission(0.001)     # 手续费 0.1%（印花税+平台费）
cerebro.addsizer(bt.sizers.PercentSizer, percents=95)

# 添加分析器
cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name='sharpe')
cerebro.addanalyzer(bt.analyzers.DrawDown, _name='drawdown')
cerebro.addanalyzer(bt.analyzers.Returns, _name='returns')

print(f'初始资金: {cerebro.broker.getvalue():.2f}')
results = cerebro.run()
strat = results[0]

print(f'最终资金: {cerebro.broker.getvalue():.2f}')
print(f'夏普比率: {strat.analyzers.sharpe.get_analysis()["sharperatio"]:.2f}')
print(f'最大回撤: {strat.analyzers.drawdown.get_analysis()["max"]["drawdown"]:.2f}%')
print(f'年化收益: {strat.analyzers.returns.get_analysis()["rnorm100"]:.2f}%')

cerebro.plot()  # 画图
```

### 参数优化

```python
cerebro = bt.Cerebro(optreturn=False)
cerebro.optstrategy(DoubleMaStrategy,
                    fast=range(5, 20, 5),
                    slow=range(20, 60, 10))

cerebro.adddata(data)
cerebro.broker.setcash(100000)
cerebro.broker.setcommission(0.001)

results = cerebro.run(maxcpus=1)

# 找最优参数
best = max(results, key=lambda x: x[0].analyzers.returns.get_analysis()['rnorm100'])
print(f"最优参数: fast={best[0].p.fast}, slow={best[0].p.slow}")
```

---

## 六、实盘交易（Futu OpenAPI）

```python
import futu as ft

# 连接交易接口
trd_ctx = ft.OpenSecTradeContext(
    filter_trdmarket=ft.TrdMarket.HK,
    host='127.0.0.1',
    port=11111,
    security_firm=ft.SecurityFirm.FUTUSECURITIES
)

# 查询账户资产
ret, data = trd_ctx.accinfo_query()
if ret == ft.RET_OK:
    print(data[['cash', 'total_assets', 'market_val']])

# 查询持仓
ret, data = trd_ctx.position_list_query()
print(data)

# 下单（限价单）
ret, data = trd_ctx.place_order(
    price=350.0,
    qty=100,
    code='HK.00700',
    trd_side=ft.TrdSide.BUY,
    order_type=ft.OrderType.NORMAL,
    trd_env=ft.TrdEnv.SIMULATE  # 仿真环境，改 REAL 为实盘
)
if ret == ft.RET_OK:
    print(f"下单成功，订单ID: {data['order_id'][0]}")

trd_ctx.close()
```

---

## 七、港股交易规则（量化必知）

| 规则 | 说明 |
|------|------|
| 交易时间 | 09:30-12:00, 13:00-16:00（港股时间） |
| 最小交易单位 | 每只股票不同（1手=100股/200股/500股等） |
| 印花税 | 买卖双向各 0.1% |
| 结算 | T+2 交收 |
| 卖空 | 需要融券，普通账户不能裸卖空 |
| 涨跌停 | 无涨跌停限制 |

---

## 八、完整项目结构

```
~/hkquant/
├── data/
│   └── cache/          # AKShare 数据缓存
├── strategy/
│   ├── ma_strategy.py  # 均线策略
│   └── momentum.py     # 动量策略
├── backtest/
│   └── run_backtest.py # 回测脚本
├── live/
│   └── futu_trader.py  # 实盘交易
└── requirements.txt
```

`requirements.txt`:
```
futu-api
backtrader
akshare
pandas
numpy
matplotlib
ta-lib
```

---

## 九、常用命令速查

```bash
# 激活环境
source ~/vnpy_env/bin/activate

# 测试 AKShare 港股数据
python -c "import akshare as ak; print(ak.stock_hk_hist(symbol='00700', period='daily', start_date='20240101', end_date='20241231', adjust='qfq').tail())"

# 运行回测
python backtest/run_backtest.py

# 检查 FutuOpenD 是否运行
curl http://127.0.0.1:11111
```

---

## 十、macOS vs Windows 对比

| 功能 | macOS | Windows |
|------|-------|---------|
| AKShare 数据 | ✅ | ✅ |
| Backtrader 回测 | ✅ | ✅ |
| Futu OpenAPI 实盘 | ✅ | ✅ |
| CTP 期货实盘 | ❌ | ✅ |
| VeighNa Studio | ❌ | ✅ |

港股量化在 macOS 上完全没有限制，Futu OpenAPI 原生支持。
