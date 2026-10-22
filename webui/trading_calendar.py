"""Versioned exchange holiday calendar; never assume an unverified year is open."""
import json
import re
from pathlib import Path
import pandas as pd

CONFIG = json.loads((Path(__file__).parent / 'calendars/cn_futures_2026.json').read_text())
START = pd.Timestamp(CONFIG['coverage_start'])
END = pd.Timestamp(CONFIG['coverage_end'])
HOLIDAYS = {d for a, b in CONFIG['holiday_ranges'] for d in pd.date_range(a, b)}
NO_NIGHT = {pd.Timestamp(d) for d in CONFIG['no_night_starts']}


def resolve_calendar(selection, file_path):
    if selection in ('DCE', 'SHFE', 'none'):
        return selection
    if selection != 'auto':
        raise ValueError('不支持的交易日历')
    name = Path(file_path).name.upper()
    if re.search(r'(^|_)(A|P)\d+(_|\.)', name) or any(x in name for x in ('豆一', '棕榈油')):
        return 'DCE'
    if re.search(r'(^|_)SS\d+(_|\.)', name) or '不锈钢' in name:
        return 'SHFE'
    raise ValueError('无法自动识别该文件的交易所，请选择大商所、上期所，或明确选择仅按历史时段推算')


def checked(day):
    day = pd.Timestamp(day).normalize()
    if not START <= day <= END:
        raise ValueError('交易日历仅覆盖 2026 年，预测超出已核对范围；请减少预测条数或更新日历文件')
    return day


def is_trading_day(day):
    day = checked(day)
    return day.weekday() < 5 and day not in HOLIDAYS


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


def permitted(stamp, daily=False):
    stamp = pd.Timestamp(stamp)
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
    name = {'DCE': '大商所', 'SHFE': '上期所'}[exchange]
    return f'已应用{name}2026年休市及停夜盘日历（核对日期：{CONFIG["version"]}）；K线时刻沿用历史数据口径，不覆盖临时停市。'
