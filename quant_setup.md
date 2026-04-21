# 大陆期货量化交易环境 - macOS 安装与使用指南

> 基于 VeighNa (vn.py) 4.x + AKShare + Tushare，适配 macOS Apple Silicon / Intel

---

## 环境说明

| 组件 | 版本 | 说明 |
|------|------|------|
| Python | 3.11 | 通过 Homebrew 安装 |
| vnpy | 最新 | 核心框架 |
| vnpy_ctastrategy | 1.4.x | CTA 策略引擎 |
| vnpy_akshare | 1.0.x | AKShare 数据源 |
| vnpy_tushare | 1.4.x | Tushare 数据源 |
| akshare | 最新 | 免费期货数据 |

> ⚠️ **CTP 网关（vnpy_ctp）不支持 macOS**，CTP 实盘/仿真需在 Linux VPS 上运行。
> macOS 本机适合：策略开发、回测、数据分析。

---

## 一、安装步骤（已完成）

### 1. 安装 Python 3.11

```bash
brew install python@3.11
```

### 2. 创建虚拟环境

```bash
/opt/homebrew/bin/python3.11 -m venv ~/vnpy_env
```

### 3. 激活虚拟环境

```bash
source ~/vnpy_env/bin/activate
```

### 4. 安装依赖

```bash
pip install vnpy vnpy_ctastrategy vnpy_tushare vnpy_akshare akshare
```

---

## 二、每次使用前激活环境

```bash
source ~/vnpy_env/bin/activate

# 验证安装
python -c "import vnpy; import vnpy_ctastrategy; import akshare; print('OK')"
```

---

## 三、启动 VeighNa 图形界面

```bash
source ~/vnpy_env/bin/activate
python -m vnpy.trader.ui
```

> 注意：macOS 上 GUI 需要 PyQt5/PySide6，如启动失败先安装：
> ```bash
> pip install pyqt5
> ```

---

## 四、用 AKShare 获取期货数据（命令行）

```python
import akshare as ak

# 获取螺纹钢主连日线数据
df = ak.futures_main_sina(symbol="RB0")
print(df.tail())

# 获取铁矿石主连
df = ak.futures_main_sina(symbol="I0")
print(df.tail())

# 常用品种代码
# RB0 螺纹钢  I0 铁矿石  CU0 铜  AU0 黄金
# IF0 沪深300股指  IC0 中证500  IM0 中证1000
```

运行方式：

```bash
source ~/vnpy_env/bin/activate
python your_script.py
```

---

## 五、双均线策略示例

保存为 `strategy/ma_strategy.py`：

```python
from vnpy_ctastrategy import CtaTemplate
from vnpy.trader.object import BarData
from vnpy.trader.utility import ArrayManager

class DoubleMaStrategy(CtaTemplate):
    """双均线期货策略"""
    author = "quant"

    fast_window = 10
    slow_window = 30
    fixed_size = 1

    parameters = ["fast_window", "slow_window", "fixed_size"]
    variables = []

    def on_init(self):
        self.am = ArrayManager(size=100)
        self.write_log("策略初始化")
        self.load_bar(100)

    def on_start(self):
        self.write_log("策略启动")

    def on_stop(self):
        self.write_log("策略停止")

    def on_bar(self, bar: BarData):
        self.cancel_all()
        am = self.am
        am.update_bar(bar)
        if not am.inited:
            return

        fast_ma = am.sma(self.fast_window)
        slow_ma = am.sma(self.slow_window)

        if self.pos == 0:
            if fast_ma > slow_ma:
                self.buy(bar.close_price * 1.005, self.fixed_size)
        elif self.pos > 0:
            if fast_ma < slow_ma:
                self.sell(bar.close_price * 0.995, abs(self.pos))

        self.put_event()
```

---

## 六、回测示例

```python
from vnpy_ctastrategy.backtesting import BacktestingEngine
from vnpy.trader.constant import Interval
from datetime import datetime

# 初始化回测引擎
engine = BacktestingEngine()
engine.set_parameters(
    vt_symbol="RB2501.SHFE",   # 螺纹钢合约
    interval=Interval.DAILY,
    start=datetime(2023, 1, 1),
    end=datetime(2024, 12, 31),
    rate=0.0003,               # 手续费率
    slippage=1,                # 滑点（元/手）
    size=10,                   # 合约乘数
    pricetick=1,               # 最小变动价位
    capital=100000,            # 初始资金
)

# 加载策略
from strategy.ma_strategy import DoubleMaStrategy
engine.add_strategy(DoubleMaStrategy, {"fast_window": 10, "slow_window": 30})

# 加载数据（需要先有历史数据）
engine.load_data()

# 运行回测
engine.run_backtesting()

# 统计结果
df = engine.calculate_result()
engine.calculate_statistics()
engine.show_chart()
```

---

## 七、SimNow 仿真实盘（需 Linux VPS）

macOS 不支持 CTP，需要在 Linux 上运行实盘/仿真。

### 推荐方案：阿里云/腾讯云香港 VPS（2核4G，~80元/月）

```bash
# 在 Linux VPS 上安装
pip install vnpy vnpy_ctp vnpy_ctastrategy vnpy_akshare

# SimNow 仿真配置
# 注册地址：http://www.simnow.com.cn/
# BrokerID: 9999
# 行情服务器: 180.168.146.187:10131
# 交易服务器: 180.168.146.187:10130
# 产品名称: simnow_client_test
# 授权码: 0000000000000000
```

---

## 八、后期接入 OpenBB（可选）

```bash
pip install openbb openbb-akshare
```

```python
from openbb import obb

# 获取期货数据
price = obb.derivatives.futures.price(symbol="RB0", provider="akshare")
print(price.to_df())
```

---

## 九、常用命令速查

```bash
# 激活环境
source ~/vnpy_env/bin/activate

# 退出环境
deactivate

# 查看已安装包
pip list | grep vnpy

# 更新包
pip install --upgrade vnpy vnpy_ctastrategy akshare

# 启动图形界面
python -m vnpy.trader.ui
```

---

## 十、目录结构建议

```
~/quant/
├── strategy/          # 策略文件
│   └── ma_strategy.py
├── data/              # 本地数据缓存
├── logs/              # 日志
└── backtest.py        # 回测脚本
```

---

## 注意事项

1. CTP 实盘只能在 Linux 上跑，macOS 做策略开发和回测
2. Tushare 需要注册获取 token：https://tushare.pro/register
3. AKShare 完全免费，适合日线级别数据
4. 实盘前务必在 SimNow 仿真跑 1-2 周
5. 期货有杠杆，建议从 1 手开始，控制仓位
