import unittest
from unittest.mock import patch
import pandas as pd
from webui.market_data import parse_catalog, clean_bars, aggregate, download
from webui.app import app

class MarketTests(unittest.TestCase):
    def test_catalog_safe_parse(self):
        text="ARRFUTURESNODES = { dce : ['大商所', ['棕榈','zly_qh','0']], gfex : ['广期所',['工业硅','si_qh','1']], // ignore\n};"
        self.assertEqual([x['id'] for x in parse_catalog(text)], ['zly_qh','si_qh'])
    def test_aggregation_and_invalid_rows(self):
        raw=[dict(d=d,o=o,h=h,l=l,c=c,v=v) for d,o,h,l,c,v in [
            ('2026-09-30',10,12,9,11,100),('2026-10-08',11,14,10,13,200),
            ('2026-10-09',13,15,12,14,300),('2026-10-10',10,9,12,11,20)]]
        df=clean_bars(raw); self.assertEqual(len(df),3)
        monthly=aggregate(df,'monthly');self.assertEqual(len(monthly),2)
        last=monthly.iloc[-1];self.assertEqual([last.open,last.high,last.low,last.close,last.volume],[11,15,10,14,500])
        self.assertEqual(str(last.timestamps.date()),'2026-10-09')
        self.assertEqual(len(aggregate(df,'weekly')),2)
    def test_invalid_period_no_network(self):
        with self.assertRaises(ValueError): download('anything','bad')
    def test_monthly_prediction_uses_months(self):
        frame=pd.DataFrame(dict(timestamps=pd.to_datetime(['2026-08-31','2026-09-30','2026-10-26']),open=[1]*3,high=[1]*3,low=[1]*3,close=[1]*3,volume=[2]*3))
        class Predictor:
            max_context=512
            def predict(self,**kw):
                return pd.DataFrame(dict(open=1.,high=1.,low=1.,close=1.,volume=2.), index=kw['y_timestamp'])
        with patch('webui.app.load_data_file',return_value=(frame,None)), patch('webui.app.predictor',Predictor()), patch('webui.app.market_data.metadata',return_value={'period':'monthly','calendar':'DCE'}), patch('webui.app.save_prediction_results'), app.test_client() as c:
            r=c.post('/api/predict',json={'file_path':'test','lookback':3,'pred_len':3})
            self.assertEqual(r.status_code,200,r.json)
            self.assertEqual([x['timestamp'][:10] for x in r.json['prediction_results']],['2026-11-30','2026-12-31','2027-01-31'])
