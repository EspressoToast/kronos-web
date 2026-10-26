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
    df=pd.DataFrame(raw).rename(columns={'d':'timestamps','o':'open','h':'high','l':'low','c':'close','v':'volume','p':'hold'})
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
