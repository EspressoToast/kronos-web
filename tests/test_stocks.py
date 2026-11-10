import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, Mock
from webui import market_data as m

class StockTests(unittest.TestCase):
    def test_codes_keep_leading_zero_and_exchange(self):
        rows = [{'symbol':'sz000001','name':'平安银行'}, {'symbol':'sh600519','name':'贵州茅台'},
                {'symbol':'bj920000','name':'安徽凤凰'}, {'symbol':'../../x','name':'bad'}]
        items = m.parse_stocks(rows)
        self.assertEqual([x['code'] for x in items], ['000001','600519','920000'])
        self.assertEqual([x['exchange'] for x in items], ['SZSE','SSE','BSE'])

    def test_stock_download_aggregates_and_writes_metadata(self):
        item = m.parse_stocks([{'symbol':'sz000001','name':'平安银行'}])[0]
        response = Mock(url='https://example.invalid/bars')
        response.json.return_value = [dict(day=d,open='10',high='12',low='9',close='11',volume=v)
            for d,v in [('2026-10-08','100'),('2026-10-09','200')]]
        with tempfile.TemporaryDirectory() as root, patch.object(m,'ROOT',Path(root)), patch.object(m,'stock_catalog',return_value={'items':[item]}), patch.object(m,'get',return_value=response) as fetch:
            result=m.download('sz000001','monthly')
            self.assertEqual(result['rows'],1)
            self.assertEqual(result['calendar'],'CN_A')
            self.assertEqual(result['kind'],'stock')
            self.assertEqual(result['code'],'000001')
            self.assertEqual(fetch.call_args.kwargs['params']['scale'],'240')
            self.assertEqual(m.pd.read_csv(result['file_path']).volume.iloc[0],300)
            self.assertEqual(json.loads(Path(result['file_path']).with_suffix('.source.json').read_text())['adjustment'],'不复权')

    def test_invalid_stock_is_not_requested(self):
        with patch.object(m,'stock_catalog',return_value={'items':[]}), patch.object(m,'get') as fetch:
            with self.assertRaises(ValueError): m.download('sz999999','30')
            fetch.assert_not_called()

    def test_partial_catalog_keeps_futures_and_warns(self):
        with patch.object(m,'catalog',return_value={'items':[{'id':'zly_qh','name':'棕榈'}],'updated_at':'today'}), patch.object(m,'stock_catalog',side_effect=ValueError('offline')):
            result=m.instrument_catalog(True)
            self.assertEqual(result['items'][0]['kind'],'futures')
            self.assertIn('A 股',result['warning'])

    def test_incomplete_refresh_keeps_stock_cache(self):
        old={'time':0,'updated_at':'old','items':[{'id':'sz000001','name':'平安银行'}]}
        count=Mock();count.json.return_value='201'
        page=Mock();page.json.return_value=[{'symbol':'sz000001','name':'平安银行'}]
        with tempfile.TemporaryDirectory() as root, patch.object(m,'ROOT',Path(root)), patch.object(m,'_stock_cache',old), patch.object(m,'get',side_effect=lambda url,**kwargs:count if 'Count' in url else page):
            result=m.stock_catalog(True)
            self.assertEqual(result['updated_at'],'old')
            self.assertIn('缓存',result['warning'])
            self.assertFalse((Path(root)/'.cache/stock_catalog.json').exists())
