"""Versioned exchange holiday calendar; never assume an unverified year is open."""
import json
import re
from pathlib import Path
import pandas as pd

CONFIG = json.loads((Path(__file__).parent / 'calendars/cn_futures_2026.json').read_text())
START = pd.Timestamp(CONFIG['coverage_start'])
END = pd.Timestamp(CONFIG['coverage_end'])
STOCK_CONFIG = json.loads((Path(__file__).parent / 'calendars/cn_a_shares_2026.json').read_text())
STOCK_HOLIDAYS = {d for a, b in STOCK_CONFIG['holiday_ranges'] for d in pd.date_range(a, b)}
HOLIDAYS = {d for a, b in CONFIG['holiday_ranges'] for d in pd.date_range(a, b)}
NO_NIGHT = {pd.Timestamp(d) for d in CONFIG['no_night_starts']}


def resolve_calendar(selection, file_path):
    if selection in ('DCE', 'SHFE', 'CN_A', 'none'):
        return selection
    if selection != 'auto':
        raise ValueError('不支持的交易日历')
    name = Path(file_path).name.upper()
    if re.search(r'(^|_)(SH|SZ|BJ)\d{6}(_|\.)', name):
        return 'CN_A'
    if re.search(r'(^|_)(A|P)\d+(_|\.)', name) or any(x in name for x in ('豆一', '棕榈油')):
        return 'DCE'
    if re.search(r'(^|_)SS\d+(_|\.)', name) or '不锈钢' in name:
        return 'SHFE'
    raise ValueError('无法自动识别该文件的交易所，请选择 A 股、大商所、上期所，或明确选择仅按历史时段推算')


def checked(day, exchange="DCE"):
    day = pd.Timestamp(day).normalize()
    config = STOCK_CONFIG if exchange == 'CN_A' else CONFIG
    if not pd.Timestamp(config['coverage_start']) <= day <= pd.Timestamp(config['coverage_end']):
        raise ValueError('交易日历仅覆盖 2026 年，预测超出已核对范围；请减少预测条数或更新日历文件')
    return day


def is_trading_day(day, exchange='DCE'):
    day = checked(day, exchange)
    holidays = STOCK_HOLIDAYS if exchange == 'CN_A' else HOLIDAYS
    return day.weekday() < 5 and day not in holidays


def night_open(start_day):
    start_day = pd.Timestamp(start_day).normalize()
    # Explicit year-boundary closure is known from the following year's notice.
    if start_day in NO_NIGHT:
        return False
    if not is_trading_day(start_day):
        return False
    # Friday night is permitted and belongs to Monday, unless explicitly closed.
    next_day = start_day + pd.Timedelta(days=1)
    while not is_trading_day(next_day):
        next_day += pd.Timedelta(days=1)
    return True


def permitted(stamp, daily=False, exchange="DCE"):
    stamp = pd.Timestamp(stamp)
    if exchange == 'CN_A':
        if not is_trading_day(stamp, exchange):
            return False
        if daily:
            return True
        label = stamp.strftime('%H:%M:%S')
        return any(start <= label <= end for start, end in STOCK_CONFIG['sessions'])
    if daily:
        return is_trading_day(stamp)
    checked(stamp)
    if stamp.hour >= 21:
        return night_open(stamp.normalize())
    if stamp.hour < 3:
        return night_open(stamp.normalize() - pd.Timedelta(days=1))
    return 9 <= stamp.hour < 16 and is_trading_day(stamp)


def calendar_note(exchange):
    if exchange == 'none':
        return '未启用节假日过滤，仅按历史时段推算。'
    if exchange == 'CN_A':
        return f'已应用沪深京 A 股 2026 年交易日历（核对日期：{STOCK_CONFIG["version"]}），跳过周末、节假日、午休及夜间；K 线时刻沿用历史口径，不覆盖个股停牌、临时停市和盘后交易。'
    name = {'DCE': '大商所', 'SHFE': '上期所'}[exchange]
    return f'已应用{name}2026年休市及停夜盘日历（核对日期：{CONFIG["version"]}）；K线时刻沿用历史数据口径，不覆盖临时停市。'


def stock_period_timestamps(last, count, period):
    """Return the last verified trading date of each subsequent stock week/month."""
    freq = 'W-FRI' if period == 'weekly' else 'M'
    current = pd.Period(pd.Timestamp(last), freq=freq)
    result = []
    while len(result) < count:
        current += 1
        # Verify the entire period before using its final trading day.
        days = pd.date_range(current.start_time.normalize(), current.end_time.normalize())
        trading_days = [day for day in days if is_trading_day(day, 'CN_A')]
        if trading_days:
            result.append(trading_days[-1])
    return pd.Series(result)
