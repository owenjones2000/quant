# Requirements Document

## Introduction

本功能为 A 股量化选股、监控与飞书通知系统。系统基于通达信选股公式（转译为 Python/MyTT 实现），每个交易日收盘后扫描全 A 股，筛选符合条件的股票并加入自选股列表；对自选股持续监控均线突破回调信号；通过飞书 Webhook 推送通知。

技术栈：Python 3.11，AKShare 数据源，MyTT 指标库，APScheduler 调度，飞书 Webhook。

---

## Glossary

- **Screener（选股引擎）**：执行通达信公式转译逻辑，对股票池进行批量扫描并返回命中列表的模块。
- **Watchlist（自选股列表）**：持久化存储的用户关注股票集合，以 JSON 文件形式保存。
- **Monitor（监控引擎）**：对自选股列表中的股票持续检测均线状态和价格位置，产生突破回调信号的模块。
- **Notifier（通知模块）**：将信号格式化后通过飞书 Webhook 推送消息的模块。
- **Scheduler（调度器）**：基于 APScheduler 的定时任务管理器，负责触发选股和监控任务。
- **Daily_Screener（日线选股）**：在日线级别执行选股公式的任务。
- **Weekly_Screener（周线选股）**：在周线级别执行相同选股公式，用于标记"重点关注"的任务。
- **EMA(n)**：n 周期指数移动平均线。
- **KDJ(n)**：以 n 周期为参数的随机指标，包含 K、D、J 三线。
- **SLOPE(n)**：n 周期线性回归斜率。
- **CROSS(A,B)**：A 上穿 B 的交叉信号（当前 A>=B 且前一周期 A<B）。
- **EXIST(cond, n)**：过去 n 个周期内条件 cond 至少出现一次。
- **BARSLAST(cond)**：距上次条件 cond 为真的周期数。
- **LLV(X,n)**：X 在过去 n 周期内的最低值。
- **HHV(X,n)**：X 在过去 n 周期内的最高值。
- **ZT（涨停）**：当日涨幅 >= 9.5% 的状态。
- **CT（冲天）**：当日涨幅 >= 7.5% 的状态。
- **YALI（压力位）**：基于 J24 上穿 J 的交叉点计算的动态压力价格。
- **YALI2（压力位2）**：基于 J24 上穿 J2 的交叉点计算的动态压力价格。
- **Bull_Alignment（多头排列）**：EMA5 >= EMA10 >= EMA15 >= EMA30 的均线状态。
- **Pullback_Signal（突破回调信号）**：多头排列状态下，收盘价触及 EMA5/EMA10/EMA15 任意一条均线（2% 范围内）时产生的提示信号。
- **EMA60_Exit（EMA60 踢出规则）**：自选股中某股票收盘价跌破 EMA60 时，自动从自选股列表移除，等待下次选股重新命中后才可再次加入。
- **Key_Focus（重点关注）**：同时满足日线和周线选股条件的股票标记。
- **AKShare**：免费 A 股数据接口库，提供日线、周线历史 K 线数据。
- **MyTT**：通达信指标函数的 Python 实现库，提供 EMA、SMA、SLOPE、KDJ 等函数。

---

## Requirements

### Requirement 1: 通达信选股公式转译

**User Story:** As a 量化交易者, I want 将通达信选股公式完整转译为 Python 逻辑, so that 系统能够在 Python 环境中精确复现通达信的选股结果。

#### Acceptance Criteria

1. THE Screener SHALL 使用 MyTT 库中的 EMA、SMA、SLOPE、CROSS、LLV、HHV、EXIST、BARSLAST、MA、REF 函数实现所有中间变量的计算。
2. THE Screener SHALL 按以下公式计算中间变量：
   - `BUYIN = EMA(CLOSE, 1)`
   - `SALE = EMA(SLOPE(CLOSE, 10) * 10 + CLOSE, 20)`
   - `RSV = (CLOSE - LLV(LOW, 5)) / (HHV(HIGH, 5) - LLV(LOW, 5)) * 100`，`K = SMA(RSV, 3, 1)`，`D = SMA(K, 3, 1)`，`J = 3*K - 2*D`（5周期 KDJ）
   - `RSV2 = (CLOSE - LLV(LOW, 8)) / (HHV(HIGH, 8) - LLV(LOW, 8)) * 100`，`K2 = SMA(RSV2, 3, 1)`，`D2 = SMA(K2, 3, 1)`，`J2 = 3*K2 - 2*D2`（8周期 KDJ）
   - `RSV24 = (CLOSE - LLV(LOW, 55)) / (HHV(HIGH, 55) - LLV(LOW, 55)) * 100`，`K24 = SMA(RSV24, 3, 1)`，`D24 = SMA(K24, 3, 1)`，`J24 = 3*K24 - 2*D24`（55周期 KDJ）
   - `YALI = IF(CROSS(J24, J), HIGH, REF(HIGH, BARSLAST(CROSS(J24, J))))`
   - `YALI2 = IF(CROSS(J24, J2), HIGH, REF(HIGH, BARSLAST(CROSS(J24, J2))))`
   - `ZT = (HIGH - REF(CLOSE, 1)) / REF(CLOSE, 1) * 100 >= 9.5`
   - `CT = (CLOSE - REF(CLOSE, 1)) / REF(CLOSE, 1) * 100 >= 7.5`
3. THE Screener SHALL 按以下组合条件判断股票是否命中选股：
   - `(CLOSE[-1] >= YALI[-1] OR CLOSE[-1] >= YALI2[-1])`
   - `AND CLOSE[-1] >= EMA(CLOSE, 15)[-1]`
   - `AND EMA(CLOSE, 5)[-1] >= EMA(CLOSE, 10)[-1] AND EMA(CLOSE, 10)[-1] >= EMA(CLOSE, 15)[-1]`
   - `AND EXIST(CT, 1) == True`
   - `AND EXIST(ZT, 1) == True`
4. IF 计算过程中出现除零错误（HHV == LLV 导致分母为零），THEN THE Screener SHALL 跳过该股票并记录警告日志，不中断整体扫描流程。
5. THE Screener SHALL 对每只股票至少加载 120 根日线 K 线数据以保证指标计算的准确性。
6. FOR ALL 有效股票，THE Screener 计算的 KDJ 值 SHALL 与通达信公式定义的 SMA 递推结果一致（即 `SMA(X, N, M) = (M * X + (N - M) * prev) / N`）。

---

### Requirement 2: 每日全 A 股扫描任务

**User Story:** As a 量化交易者, I want 系统在每个交易日收盘后自动扫描全 A 股, so that 我无需手动操作即可获得当日符合条件的股票列表。

#### Acceptance Criteria

1. WHEN 当前时间为交易日且时间在 15:05 至 15:30 之间，THE Scheduler SHALL 触发 Daily_Screener 对全 A 股执行一次选股扫描。
2. THE Daily_Screener SHALL 通过 AKShare 获取全 A 股列表，并对每只股票获取日线 K 线数据后执行 Requirement 1 中定义的选股公式。
3. WHEN Daily_Screener 扫描完成，THE Daily_Screener SHALL 返回命中股票的代码列表及对应股票名称。
4. IF AKShare 接口请求失败，THEN THE Daily_Screener SHALL 对该股票最多重试 3 次，每次间隔 1 秒，重试耗尽后跳过该股票并记录错误日志。
5. THE Daily_Screener SHALL 在非交易日（周六、周日及法定节假日）不执行扫描任务。
6. WHEN 扫描任务执行完毕，THE Daily_Screener SHALL 将本次扫描结果（命中股票列表、扫描时间、命中数量）写入日志文件。

---

### Requirement 3: 自选股持久化管理

**User Story:** As a 量化交易者, I want 选出的股票自动加入自选股列表并持久化保存, so that 系统重启后自选股数据不丢失。

#### Acceptance Criteria

1. WHEN Daily_Screener 返回命中股票列表，THE Watchlist SHALL 将命中股票自动添加到自选股列表中。
2. THE Watchlist SHALL 以 JSON 格式将自选股数据持久化存储到 `backend/data/watchlist.json` 文件中，每条记录包含股票代码、股票名称、加入时间、是否为重点关注标记。
3. IF 股票已存在于自选股列表中，THEN THE Watchlist SHALL 不重复添加，但 SHALL 更新该股票的重点关注标记（如周线条件发生变化）。
4. THE Watchlist SHALL 提供删除接口，支持按股票代码从自选股列表中移除指定股票。
5. FOR ALL 写入操作，THE Watchlist SHALL 保证 JSON 文件的原子性写入，避免文件损坏（先写临时文件再重命名）。
6. WHEN 读取自选股列表，THE Watchlist SHALL 在 100 毫秒内返回完整列表。

---

### Requirement 4: 周线重点关注标记

**User Story:** As a 量化交易者, I want 系统对日线命中的股票额外检查周线条件, so that 我能快速识别日线和周线共振的强势股票。

#### Acceptance Criteria

1. WHEN Daily_Screener 产生命中股票列表，THE Weekly_Screener SHALL 对列表中每只股票获取周线 K 线数据并执行与 Requirement 1 相同的选股公式。
2. WHEN 某股票同时满足日线和周线选股条件，THE Watchlist SHALL 将该股票的 `key_focus` 字段标记为 `true`。
3. THE Weekly_Screener SHALL 通过 AKShare 的周线接口（`period="weekly"`）获取至少 120 根周线 K 线数据。
4. IF 周线数据不足 60 根，THEN THE Weekly_Screener SHALL 跳过该股票的周线检查，并将 `key_focus` 保持为 `false`。
5. WHEN 飞书通知发送时，THE Notifier SHALL 在重点关注股票的消息中附加"⭐ 重点关注"标识。

---

### Requirement 5: 自选股均线突破回调监控

**User Story:** As a 量化交易者, I want 系统持续监控自选股的均线状态, so that 当股价回调至关键均线时我能及时收到提示。

#### Acceptance Criteria

1. WHILE 当前时间在 A 股交易时间（09:30–11:30 或 13:00–15:00）内，THE Monitor SHALL 每 3 分钟对自选股列表中的所有股票执行一次均线状态检测。
2. THE Monitor SHALL 计算每只自选股的 EMA5、EMA10、EMA15、EMA30（基于日线收盘价）。
3. WHEN EMA5 >= EMA10 AND EMA10 >= EMA15 AND EMA15 >= EMA30（多头排列成立），THE Monitor SHALL 进一步检查当前价格是否触及均线。
4. WHEN 多头排列成立且当前收盘价满足以下任一条件，THE Monitor SHALL 产生 Pullback_Signal：
   - `abs(CLOSE - EMA5) / EMA5 <= 0.02`（价格在 EMA5 的 2% 范围内）
   - `abs(CLOSE - EMA10) / EMA10 <= 0.02`（价格在 EMA10 的 2% 范围内）
   - `abs(CLOSE - EMA15) / EMA15 <= 0.02`（价格在 EMA15 的 2% 范围内）
5. THE Monitor SHALL 对同一股票的同一均线触碰信号，在同一交易日内只产生一次 Pullback_Signal，避免重复通知。
6. IF 自选股列表为空，THEN THE Monitor SHALL 跳过本次检测并记录日志，不产生任何错误。
7. WHEN 每日收盘后 Monitor 执行检测时，IF 某自选股的收盘价低于其 EMA60，THEN THE Watchlist SHALL 自动将该股票从自选股列表中移除，并记录移除原因（"收盘价跌破 EMA60"）及移除时间。
8. WHEN 某股票因跌破 EMA60 被移除后，IF 该股票在后续交易日再次满足 Requirement 1 的选股条件，THEN THE Watchlist SHALL 允许将其重新加入自选股列表，视为全新入选。

---

### Requirement 6: 飞书消息推送

**User Story:** As a 量化交易者, I want 系统通过飞书推送选股结果和监控信号, so that 我在香港也能实时接收 A 股交易提示。

#### Acceptance Criteria

1. THE Notifier SHALL 通过 HTTP POST 请求向配置的飞书 Webhook URL 发送消息，使用飞书卡片消息格式（`msg_type: interactive`）。
2. WHEN Daily_Screener 完成扫描且命中股票数量大于 0，THE Notifier SHALL 发送一条包含以下内容的飞书消息：
   - 消息标题：`📊 A股选股结果 - {日期}（共{N}只）`
   - 每只股票一行，格式：`{股票代码} {股票名称} 涨跌幅:{涨跌幅}%`，重点关注股票附加 `⭐ 重点关注`
3. WHEN Monitor 产生 Pullback_Signal，THE Notifier SHALL 发送一条包含以下内容的飞书消息：
   - 消息标题：`📉 突破回调提示 - {时间}`
   - 每条信号一行，格式：`{股票代码} {股票名称} 触及{均线名称} 当前涨跌幅:{涨跌幅}%`
4. IF 飞书 Webhook 请求返回非 200 状态码或网络超时（超时阈值 10 秒），THEN THE Notifier SHALL 记录错误日志并重试一次，重试失败后不再重试。
5. IF 飞书 Webhook URL 未配置（为空字符串），THEN THE Notifier SHALL 跳过发送并在日志中记录警告，不抛出异常。
6. WHEN Daily_Screener 扫描完成但命中股票数量为 0，THE Notifier SHALL 不发送任何飞书消息。

---

### Requirement 7: 系统配置管理

**User Story:** As a 量化交易者, I want 通过配置文件管理所有系统参数, so that 我无需修改代码即可调整系统行为。

#### Acceptance Criteria

1. THE Scheduler SHALL 从 `backend/config.json` 读取以下配置项：飞书 Webhook URL、监控扫描间隔（分钟）、收盘选股触发时间、均线触碰阈值百分比。
2. IF `backend/config.json` 文件不存在，THEN THE Scheduler SHALL 使用内置默认配置创建该文件，默认值为：扫描间隔 3 分钟，触碰阈值 2%，收盘选股时间 15:05。
3. THE Scheduler SHALL 支持在不重启进程的情况下，通过重新加载配置文件更新飞书 Webhook URL。
4. WHERE 用户配置了多个飞书 Webhook URL（数组格式），THE Notifier SHALL 向所有配置的 URL 发送相同消息。

---

### Requirement 8: 数据获取与缓存

**User Story:** As a 量化交易者, I want 系统高效获取 A 股历史数据, so that 全 A 股扫描能在合理时间内完成。

#### Acceptance Criteria

1. THE Daily_Screener SHALL 使用并发请求（最大并发数 10）批量获取全 A 股日线数据，以减少总扫描时间。
2. THE Daily_Screener SHALL 对每只股票的日线数据进行本地缓存，缓存有效期为当个交易日（即同一交易日内不重复请求相同股票数据）。
3. WHEN 缓存命中，THE Daily_Screener SHALL 直接从本地缓存读取数据，不发起 AKShare 网络请求。
4. THE Daily_Screener SHALL 在全 A 股（约 5000 只）扫描任务中，总耗时不超过 30 分钟。
5. IF AKShare 返回的 K 线数据行数少于 60，THEN THE Daily_Screener SHALL 跳过该股票（数据不足以计算指标），不将其加入命中列表。

---

### Requirement 9: 数据解析与序列化

**User Story:** As a 量化交易者, I want 系统能正确解析和序列化股票数据与配置, so that 数据在存储和传输过程中保持完整性。

#### Acceptance Criteria

1. THE Watchlist SHALL 将自选股数据序列化为 UTF-8 编码的 JSON 格式，并能从该格式反序列化还原完整的自选股列表。
2. FOR ALL 有效的自选股 JSON 文件，解析后再序列化再解析 SHALL 产生与原始数据等价的结果（round-trip 属性）。
3. THE Daily_Screener SHALL 将 AKShare 返回的 DataFrame 解析为包含 `open`、`high`、`low`、`close`、`volume` 字段的标准格式，字段类型均为 float64。
4. IF AKShare 返回的数据中存在 NaN 值，THEN THE Daily_Screener SHALL 对该股票跳过处理并记录警告，不将 NaN 传入指标计算函数。

