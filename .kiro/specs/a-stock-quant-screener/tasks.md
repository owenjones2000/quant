# Implementation Plan: A股量化选股监控系统

## Overview

按模块依赖顺序实现：配置层 → 数据层 → 选股引擎 → 自选股管理 → 监控引擎 → 通知模块 → 调度器 → 入口。每步构建在前一步之上，最终在 `main.py` 完成整体串联。

## Tasks

- [-] 1. 初始化项目结构与配置模块
  - 创建 `backend/` 目录结构：`data/`、`logs/`、`tests/`
  - 创建 `backend/config.py`，实现 `DEFAULT_CONFIG`、`load_config()`、`save_config()`、`reload_config()`
  - 若 `config.json` 不存在则自动创建并写入默认值（扫描间隔 3 分钟，触碰阈值 2%，收盘时间 15:05）
  - 支持多个飞书 Webhook URL（数组格式）
  - _Requirements: 7.1, 7.2, 7.3, 7.4_

  - [ ]* 1.1 为 config 模块编写单元测试
    - 测试默认配置创建、热更新 `reload_config()`、多 Webhook URL 读取
    - _Requirements: 7.1, 7.2, 7.3_

- [ ] 2. 实现数据获取与缓存模块（data_fetcher.py）
  - 创建 `backend/data_fetcher.py`
  - 实现 `get_stock_list()` 通过 AKShare 获取全 A 股列表，返回 `columns=['code','name']`
  - 实现 `get_daily_kline()` 和 `get_weekly_kline()`，失败重试 3 次（间隔 1 秒），返回标准 OHLCV DataFrame（dtype=float64）
  - 实现 `parse_kline_df()` 解析 AKShare DataFrame 为标准格式，NaN 行跳过并记录警告
  - 实现 `get_kline_cached()` 带当日缓存（key=`{symbol}_{freq}_{today}`，`threading.Lock` 保护写操作）
  - 实现 `batch_fetch_klines()` 使用 `ThreadPoolExecutor(max_workers=10)` 并发拉取
  - 实现 `clear_daily_cache()` 清除当日缓存
  - _Requirements: 2.4, 8.1, 8.2, 8.3, 8.4, 8.5, 9.3, 9.4_

  - [ ]* 2.1 为 data_fetcher 编写单元测试
    - Mock AKShare，测试重试逻辑、NaN 处理、数据 Schema 验证、缓存命中
    - _Requirements: 2.4, 8.2, 8.3, 9.3, 9.4_

  - [ ]* 2.2 为缓存命中编写属性测试（Property 10）
    - **Property 10: 缓存命中不重复请求**
    - **Validates: Requirements 8.2, 8.3**

  - [ ]* 2.3 为 AKShare DataFrame 解析编写属性测试（Property 11）
    - **Property 11: AKShare DataFrame 解析 Schema**
    - **Validates: Requirements 9.3**

  - [ ]* 2.4 为重试次数上限编写属性测试（Property 12）
    - **Property 12: 重试次数上限（最多 4 次调用）**
    - **Validates: Requirements 2.4**

- [ ] 3. 实现选股引擎（screener.py）
  - 创建 `backend/screener.py`
  - 实现 `compute_indicators(df)`：计算 BUYIN、SALE、5/8/55 周期 KDJ（K/D/J/K2/D2/J2/K24/D24/J24）、YALI、YALI2、ZT、CT
  - KDJ 使用 MyTT `SMA(X,N,M)` 递推公式：`(M*X + (N-M)*prev) / N`
  - 实现 `apply_selection_formula(df)` 执行五条件组合判断，除零时返回 False 并记录警告
  - 实现 `ScreenResult` dataclass（code, name, change_pct, key_focus）
  - 实现 `run_weekly_check(codes)` 对日线命中股票执行周线复核，周线数据 < 60 行时跳过
  - 实现 `run_daily_screen(stock_pool, count=120)` 全 A 扫描，调用 `batch_fetch_klines`，K 线 < 60 行跳过，结果写入日志
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 2.2, 2.3, 2.5, 2.6, 4.1, 4.3, 4.4, 8.5_

  - [ ]* 3.1 为 screener 编写单元测试
    - 测试 KDJ 计算、选股公式五条件、除零处理、K 线不足跳过
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5_

  - [ ]* 3.2 为 KDJ SMA 递推一致性编写属性测试（Property 1）
    - **Property 1: KDJ SMA 递推一致性（误差 < 1e-6）**
    - **Validates: Requirements 1.2, 1.6**

  - [ ]* 3.3 为选股公式完整性编写属性测试（Property 2）
    - **Property 2: 选股公式完整性（五条件充要）**
    - **Validates: Requirements 1.3**

- [ ] 4. 检查点 — 确保数据层和选股引擎测试全部通过
  - 确保所有测试通过，如有问题请提出。

- [ ] 5. 实现自选股管理模块（watchlist.py）
  - 创建 `backend/watchlist.py`
  - 实现 `WatchlistEntry` dataclass（code, name, added_at, key_focus, removed_at, remove_reason）
  - 实现 `load_watchlist()` 从 `backend/data/watchlist.json` 读取，文件损坏时返回空列表并记录错误
  - 实现 `save_watchlist()` 原子写入：先写 `.json.tmp` 再 `os.replace()`，UTF-8 编码
  - 实现 `add_stocks(results)` 批量添加，已存在则更新 `key_focus`，不重复添加
  - 实现 `remove_stock(code, reason)` 按代码移除
  - 实现 `remove_below_ema60(klines)` 检查所有自选股，收盘价 < EMA60 时移除并记录原因和时间
  - 实现 `get_active_codes()` 返回当前有效自选股代码列表
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 5.7, 5.8, 9.1, 9.2_

  - [ ]* 5.1 为 watchlist 编写单元测试
    - 测试 CRUD 操作、原子写入、EMA60 踢出、文件损坏处理
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 5.7_

  - [ ]* 5.2 为自选股添加幂等性编写属性测试（Property 3）
    - **Property 3: 自选股添加幂等性（同一代码只出现一次）**
    - **Validates: Requirements 3.3**

  - [ ]* 5.3 为 JSON 序列化 Round-Trip 编写属性测试（Property 4）
    - **Property 4: 自选股 JSON 序列化 Round-Trip**
    - **Validates: Requirements 3.2, 9.1, 9.2**

  - [ ]* 5.4 为 EMA60 踢出规则编写属性测试（Property 7）
    - **Property 7: EMA60 踢出规则（移除后不再出现在 active codes）**
    - **Validates: Requirements 5.7**

- [ ] 6. 实现监控引擎（monitor.py）
  - 创建 `backend/monitor.py`
  - 实现 `PullbackSignal` dataclass（code, name, ema_name, current_price, ema_value, change_pct, triggered_at）
  - 实现 `check_bull_alignment(ema5, ema10, ema15, ema30)` 判断多头排列
  - 实现 `check_ema_touch(price, ema, threshold=0.02)` 判断价格是否在 EMA 的 2% 范围内
  - 实现 `_is_duplicate_signal()` 和 `_mark_signal_sent()` 基于内存集合 `_sent_signals` 去重
  - 实现 `run_monitor_scan(threshold=0.02)` 对所有自选股执行一次扫描，自选股为空时跳过并记录日志
  - 同一交易日内同一股票同一均线只产生一条信号
  - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6_

  - [ ]* 6.1 为 monitor 编写单元测试
    - 测试多头排列判断、均线触碰、信号去重、空列表跳过
    - _Requirements: 5.3, 5.4, 5.5, 5.6_

  - [ ]* 6.2 为多头排列+均线触碰信号生成编写属性测试（Property 5）
    - **Property 5: 多头排列 + 均线触碰信号生成**
    - **Validates: Requirements 5.3, 5.4**

  - [ ]* 6.3 为回调信号同日去重编写属性测试（Property 6）
    - **Property 6: 回调信号同日去重（同日同股同线最多一条）**
    - **Validates: Requirements 5.5**

- [ ] 7. 实现飞书通知模块（notifier.py）
  - 创建 `backend/notifier.py`
  - 实现 `format_screen_message(results, date)` 生成飞书卡片消息 payload（`msg_type: interactive`），标题含日期和数量，每只股票一行含代码/名称/涨跌幅，`key_focus=True` 附加"⭐ 重点关注"
  - 实现 `format_pullback_message(signals)` 生成回调信号卡片消息
  - 实现 `send_feishu(webhook_url, payload, timeout=10)` 发送 HTTP POST，失败重试一次，返回是否成功
  - 实现 `send_to_all(payload, webhooks)` 向所有 URL 发送
  - 实现 `notify_screen_result(results)` 入口（results 为空时不发送）
  - 实现 `notify_pullback_signals(signals)` 入口
  - Webhook URL 为空时跳过并记录警告，不抛出异常
  - _Requirements: 4.5, 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 7.4_

  - [ ]* 7.1 为 notifier 编写单元测试
    - Mock HTTP 请求，测试消息格式化、空列表不发送、URL 为空跳过、重试逻辑
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6_

  - [ ]* 7.2 为飞书消息格式完整性编写属性测试（Property 8）
    - **Property 8: 飞书消息格式完整性（含标题/代码/名称/涨跌幅/重点关注标识）**
    - **Validates: Requirements 4.5, 6.2**

  - [ ]* 7.3 为多 Webhook 全量发送编写属性测试（Property 9）
    - **Property 9: 多 Webhook 全量发送（N 个 URL 各发送一次）**
    - **Validates: Requirements 7.4**

- [ ] 8. 检查点 — 确保核心业务模块测试全部通过
  - 确保所有测试通过，如有问题请提出。

- [ ] 9. 实现调度器（scheduler.py）
  - 创建 `backend/scheduler.py`（替换现有文件）
  - 实现 `is_trading_day(dt)` 排除周末和法定节假日
  - 实现 `is_trading_time(dt)` 判断盘中时间（09:30–11:30 或 13:00–15:00）
  - 实现 `is_close_screen_window(dt, trigger_time)` 判断收盘选股窗口
  - 实现 `daily_screen_job()` 收盘选股任务：选股 → 周线复核 → 更新自选股 → EMA60 踢出 → 发送通知
  - 实现 `monitor_job()` 盘中监控任务：检测均线触碰 → 发送回调信号
  - 实现 `start_scheduler(config)` 启动 APScheduler，注册收盘选股（cron 15:05）和盘中监控（interval 3 分钟）任务
  - 非交易日静默跳过，支持热更新 Webhook URL
  - _Requirements: 2.1, 2.5, 5.1, 7.1, 7.2, 7.3_

  - [ ]* 9.1 为 scheduler 编写单元测试
    - 测试交易日判断、交易时间判断、非交易日跳过逻辑
    - _Requirements: 2.1, 2.5_

- [ ] 10. 实现入口文件（main.py）并串联所有模块
  - 创建 `backend/main.py`
  - 加载配置，初始化日志（写入 `logs/screener.log`）
  - 调用 `start_scheduler(config)` 启动调度器
  - 保持进程运行（`scheduler.start()` + 主线程阻塞）
  - 确保 `backend/data/watchlist.json` 初始文件存在（不存在时创建空数组 `[]`）
  - _Requirements: 2.1, 3.2, 7.1_

- [ ] 11. 最终检查点 — 确保所有测试通过
  - 运行 `pytest backend/tests/ -v` 确保全部通过，如有问题请提出。

## Notes

- 标注 `*` 的子任务为可选项，可跳过以加快 MVP 交付
- 每个任务引用具体需求条款以保证可追溯性
- 属性测试使用 `hypothesis`，每个属性 `@settings(max_examples=100)`
- 并发拉取使用 `ThreadPoolExecutor(max_workers=10)`，缓存用 `threading.Lock` 保护
- 原子写入：先写 `watchlist.json.tmp` 再 `os.replace()`
- 虚拟环境：`~/vnpy_env`，依赖：`akshare mytt apscheduler hypothesis pytest requests`
