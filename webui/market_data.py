"""Public Sina futures catalog and OHLCV downloads; no credentials or JS execution."""
import ast
import json
import re
import time
from datetime import datetime
from pathlib import Path
import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
CATALOG_URL = 'https://vip.stock.finance.sina.com.cn/quotes_service/view/js/qihuohangqing.js'
QUOTE_URL = 'https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/Market_Center.getHQFuturesData'
BAR_URL = 'https://stock2.finance.sina.com.cn/futures/api/jsonp.php/=/InnerFuturesNewService.'
PERIODS = {'5':'5 分钟', '15':'15 分钟', '30':'30 分钟', '60':'60 分钟', 'daily':'日线', 'weekly':'周线', 'monthly':'月线'}
_cache = None

def get(url, **kwargs):
    r = requests.get(url, timeout=25, headers={'Referer':'https://finance.sina.com.cn/', 'User-Agent':'Mozilla/5.0'}, **kwargs)
    r.raise_for_status()
    return r

def parse_catalog(text):
    body = text.split('ARRFUTURESNODES', 1)[1].split('};', 1)[0]
    result = []
    for match in re.finditer(r"(czce|dce|shfe|cffex|gfex)\s*:\s*(\[.*?\])\s*,?\s*(?=(?:czce|dce|shfe|cffex|gfex)\s*:|//|$)", body, re.S):
        exchange, raw = match.groups()
        entries = ast.literal_eval(raw)
        for name, node, *_ in entries[1:]:
            if re.fullmatch(r'[a-z0-9_]+', node):
                result.append(dict(id=node, name=name, exchange=exchange.upper(), exchange_name=entries[0]))
    if not result: raise ValueError('数据源品种目录格式已变化')
    return result

def catalog(refresh=False):
    global _cache
    path = ROOT / '.cache/futures_catalog.json'
    if not refresh and _cache and time.time()-_cache['time'] < 86400:
        return dict(_cache, cached=True)
    try:
        r = get(CATALOG_URL); r.encoding='gbk'
        result = dict(items=parse_catalog(r.text), time=time.time(), updated_at=datetime.now().isoformat(timespec='seconds'), cached=False)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(result, ensure_ascii=False))
        _cache=result
        return result
    except Exception:
        if path.exists():
            result=json.loads(path.read_text()); result.update(cached=True, warning='品种目录更新失败，正在使用上次缓存'); return result
        raise

def clean_bars(raw):
    df=pd.DataFrame(raw).rename(columns={'day':'timestamps','d':'timestamps','o':'open','h':'high','l':'low','c':'close','v':'volume','p':'hold'})
    required=['timestamps','open','high','low','close','volume']
    if not set(required).issubset(df.columns): raise ValueError('行情字段不完整或该周期暂无数据')
    df['timestamps']=pd.to_datetime(df['timestamps'], errors='coerce')
    for key in required[1:]: df[key]=pd.to_numeric(df[key], errors='coerce')
    import numpy as np
    valid=df['timestamps'].notna() & np.isfinite(df[required[1:]]).all(axis=1)
    valid &= (df.low>0) & (df.volume>=0) & (df.low<=df[['open','close']].min(axis=1)) & (df.high>=df[['open','close']].max(axis=1))
    df=df.loc[valid,required].sort_values('timestamps').drop_duplicates('timestamps',keep='last')
    if df.empty: raise ValueError('数据源没有返回有效 K 线')
    return df

def aggregate(df, period):
    if period not in ('weekly','monthly'): return df
    freq='W-FRI' if period=='weekly' else 'M'
    return df.groupby(df.timestamps.dt.to_period(freq), sort=True).agg(
        timestamps=('timestamps','last'), open=('open','first'), high=('high','max'),
        low=('low','min'), close=('close','last'), volume=('volume','sum')).reset_index(drop=True)

def download(node, period):
    if period not in PERIODS: raise ValueError('不支持的 K 线周期')
    if re.fullmatch(r'(sh|sz|bj)\d{6}', str(node)):
        return download_stock(node, period)
    item=next((x for x in catalog()['items'] if x['id']==node),None)
    if not item: raise ValueError('请先选择有效期货品种')
    quotes=get(QUOTE_URL,params={'node':node,'page':1,'num':100,'sort':'position','asc':0}).json()
    quote=next((q for q in quotes if re.fullmatch(r'[A-Za-z]+0',str(q.get('symbol','')))),None)
    if quote is None: raise ValueError('该品种暂未提供主连行情')
    symbol=quote['symbol'].upper()
    daily=period in ('daily','weekly','monthly')
    params={'symbol':symbol}
    if not daily: params['type']=period
    response=get(BAR_URL+('getDailyKLine' if daily else 'getFewMinLine'),params=params)
    match=re.search(r'=\((.*)\);?\s*$',response.text,re.S)
    if not match: raise ValueError('数据源行情响应格式异常')
    df=aggregate(clean_bars(json.loads(match.group(1))),period)
    directory=ROOT/'data';directory.mkdir(exist_ok=True)
    path=directory/f'sina_{symbol}_{period}.csv'
    tmp=path.with_suffix('.tmp');df.to_csv(tmp,index=False);tmp.replace(path)
    metadata=dict(symbol=symbol,name=quote.get('name',item['name']),exchange=item['exchange'],period=period,
        calendar=item['exchange'] if item['exchange'] in ('DCE','SHFE') else 'none',
        fetched_at=datetime.now().isoformat(timespec='seconds'),last_bar=df.timestamps.iloc[-1].isoformat(),
        rows=len(df),source='新浪财经',url=response.url,
        note='公开行情可能延迟，最新一根可能尚未收盘。周/月线由日线聚合，时间为该周期最后一条已有日线。')
    path.with_suffix('.source.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2))
    return dict(metadata,file_path=str(path))

def metadata(path):
    path=Path(path).resolve()
    if not path.is_relative_to((ROOT/'data').resolve()): return {}
    sidecar=path.with_suffix('.source.json')
    return json.loads(sidecar.read_text()) if sidecar.exists() else {}

# The A-share catalog is kept separate so a stock provider outage does not
# prevent existing futures downloads. All symbols come from a validated catalog.
STOCK_API = 'https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/'
_stock_cache = None

def parse_stocks(rows):
    exchanges = {'sh': ('SSE', '上海证券交易所'), 'sz': ('SZSE', '深圳证券交易所'), 'bj': ('BSE', '北京证券交易所')}
    if not isinstance(rows, list):
        raise ValueError('A 股目录响应格式异常')
    items = []
    for row in rows:
        symbol = str(row.get('symbol', '')).lower()
        name = str(row.get('name', '')).strip()
        if not re.fullmatch(r'(sh|sz|bj)\d{6}', symbol) or not name:
            continue
        exchange, exchange_name = exchanges[symbol[:2]]
        items.append(dict(id=symbol, code=symbol[2:], name=name, kind='stock', exchange=exchange, exchange_name=exchange_name))
    return items

def stock_catalog(refresh=False):
    global _stock_cache
    path = ROOT / '.cache/stock_catalog.json'
    if _stock_cache is None and path.exists():
        try:
            _stock_cache = json.loads(path.read_text())
        except (ValueError, OSError):
            pass
    if not refresh and _stock_cache and time.time() - _stock_cache['time'] < 86400:
        return dict(_stock_cache, cached=True)
    try:
        count = int(get(STOCK_API + 'Market_Center.getHQNodeStockCount', params={'node':'hs_a'}).json())
        if not 1 <= count <= 15000:
            raise ValueError('A 股目录数量异常')
        from concurrent.futures import ThreadPoolExecutor
        def page(number):
            rows = get(STOCK_API + 'Market_Center.getHQNodeData', params={
                'node':'hs_a', 'page':number, 'num':100, 'sort':'symbol', 'asc':1}).json()
            return parse_stocks(rows)
        with ThreadPoolExecutor(max_workers=4) as pool:
            pages = list(pool.map(page, range(1, (count + 99)//100 + 1)))
        items = {item['id']:item for batch in pages for item in batch}
        if len(items) != count:
            raise ValueError('A 股目录下载不完整，请稍后重新更新')
        result = dict(items=sorted(items.values(), key=lambda x:x['id']), time=time.time(),
                      updated_at=datetime.now().isoformat(timespec='seconds'), cached=False)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix('.tmp')
        tmp.write_text(json.dumps(result, ensure_ascii=False)); tmp.replace(path)
        _stock_cache = result
        return result
    except Exception:
        if _stock_cache:
            return dict(_stock_cache, cached=True, warning='A 股目录更新失败，正在使用上次缓存')
        raise

def instrument_catalog(refresh=False):
    items, warnings, updates = [], [], []
    for label, fetch in [('期货', catalog), ('A 股', stock_catalog)]:
        try:
            result = fetch(refresh)
            for item in result['items']:
                items.append(dict(item, kind=item.get('kind', 'futures')))
            updates.append(f"{label}：{result['updated_at']}")
            if result.get('warning'): warnings.append(result['warning'])
        except Exception:
            warnings.append(f'{label}目录暂时无法更新，请点击更新标的数据库重试')
    if not items:
        raise ValueError('标的数据库暂时不可用，请稍后重试')
    return dict(items=items, updated_at='；'.join(updates), warning='；'.join(warnings))

def download_stock(symbol, period):
    item = next((x for x in stock_catalog()['items'] if x['id'] == symbol), None)
    if item is None:
        raise ValueError('请选择标的数据库中的有效 A 股')
    daily = period in ('daily', 'weekly', 'monthly')
    response = get(STOCK_API + 'CN_MarketData.getKLineData', params={
        'symbol':symbol, 'scale':'240' if daily else period, 'ma':'no', 'datalen':1023})
    raw = response.json()
    if not isinstance(raw, list) or not raw:
        raise ValueError('该股票在所选周期暂无行情，请切换周期或标的')
    df = aggregate(clean_bars(raw), period)
    directory = ROOT / 'data'; directory.mkdir(exist_ok=True)
    path = directory / f'sina_{symbol}_{period}.csv'
    tmp = path.with_suffix('.tmp'); df.to_csv(tmp, index=False); tmp.replace(path)
    info = dict(symbol=symbol, code=item['code'], name=item['name'], kind='stock', exchange=item['exchange'],
        period=period, calendar='CN_A', adjustment='不复权', rows=len(df),
        fetched_at=datetime.now().isoformat(timespec='seconds'), last_bar=df.timestamps.iloc[-1].isoformat(),
        source='新浪财经', url=response.url,
        note='A 股行情不复权，成交量单位为股；最新一根可能尚未收盘。已接入沪深京 A 股 2026 年节假日日历，超出核对年份会报错。')
    path.with_suffix('.source.json').write_text(json.dumps(info, ensure_ascii=False, indent=2))
    return dict(info, file_path=str(path))
