"""Download recent Sina futures bars. No credentials required."""
import argparse
import csv
import json
import math
from datetime import datetime
from pathlib import Path
import requests

def download(symbol, period, directory):
    names={'A0':'豆一主连','P0':'棕榈油主连','SS0':'不锈钢主连'}
    method='getDailyKLine' if period=='daily' else 'getFewMinLine'
    url=f'https://stock2.finance.sina.com.cn/futures/api/jsonp.php/=/InnerFuturesNewService.{method}'
    params={'symbol':symbol}
    if period!='daily': params['type']=period
    r=requests.get(url,params=params,timeout=45);r.raise_for_status()
    raw=json.loads(r.text.split('=(',1)[1].rsplit(');',1)[0])
    if not raw: raise ValueError('数据源未返回行情')
    rows={}; rejected=[]
    for row in raw:
        datetime.fromisoformat(row['d'])
        o,h,l,c,v=[float(row[k]) for k in ['o','h','l','c','v']]
        if all(math.isfinite(x) for x in [o,h,l,c,v]) and 0<l<=min(o,c)<=max(o,c)<=h and v>=0:
            rows[row['d']]=row
        else: rejected.append(row)
    clean=[rows[k] for k in sorted(rows)]
    if not clean: raise ValueError('没有有效行情')
    directory.mkdir(parents=True,exist_ok=True)
    name=f'{names[symbol]}_{symbol}_{"日线" if period=="daily" else period+"分钟"}_新浪'
    path=directory/f'{name}.csv'
    tmp=path.with_suffix('.tmp')
    with tmp.open('w',encoding='utf-8',newline='') as f:
        writer=csv.writer(f);writer.writerow(['timestamps','open','high','low','close','volume','hold'])
        writer.writerows([row[k] for k in ['d','o','h','l','c','v','p']] for row in clean)
    tmp.replace(path)
    path.with_suffix('.source.json').write_text(json.dumps({'url':r.url,'downloaded_at':datetime.now().isoformat(), 'rows':len(clean),'rejected':rejected,'note':'新浪原始主连口径，未复权。分钟历史长度受数据源限制。'},ensure_ascii=False,indent=2))
    print(f'{path}: {len(clean)} 根，{clean[0]["d"]} 至 {clean[-1]["d"]}')
    return path

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--symbol',choices=['A0','P0','SS0'],default='P0')
    parser.add_argument('--period',choices=['1','5','15','30','60','daily'],default='30')
    args=parser.parse_args()
    download(args.symbol,args.period,Path(__file__).resolve().parents[1]/'data')
