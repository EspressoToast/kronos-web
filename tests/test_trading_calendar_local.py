"""Run with .venv/bin/python -m unittest discover -s tests -p test_trading_calendar_local.py"""
import unittest
from unittest.mock import patch
from pathlib import Path
import pandas as pd
from webui.trading_calendar import is_trading_day, permitted, resolve_calendar
from webui.app import app, future_timestamps

class CalendarTests(unittest.TestCase):
    def test_holidays_and_makeup_weekends(self):
        for day in ['2026-01-02','2026-02-23','2026-04-06','2026-05-05','2026-06-19','2026-09-25','2026-10-07','2026-10-10','2026-02-28']:
            self.assertFalse(is_trading_day(day), day)
        self.assertTrue(is_trading_day('2026-10-08'))

    def test_holiday_eve_and_resumption(self):
        for stamp in ['2026-09-30 21:30','2026-10-01 00:30','2026-10-07 21:30','2026-10-08 00:30','2026-02-13 21:30']:
            self.assertFalse(permitted(stamp), stamp)
        self.assertTrue(permitted('2026-10-08 09:30'))
        self.assertTrue(permitted('2026-10-08 21:30'))

    def test_friday_night_and_saturday_carry(self):
        self.assertTrue(permitted('2026-10-23 21:30'))
        self.assertTrue(permitted('2026-10-24 00:30'))
        self.assertFalse(permitted('2026-10-24 09:30'))
        self.assertFalse(permitted('2026-10-25 21:30'))
        self.assertFalse(permitted('2026-10-26 00:30'))

    def test_daily_skips_weekends_and_holiday(self):
        history=pd.Series(pd.bdate_range('2026-08-01','2026-09-30'))
        result=future_timestamps(history,3,'DCE')
        self.assertEqual(list(result.dt.strftime('%Y-%m-%d')),['2026-10-08','2026-10-09','2026-10-12'])

    def test_intraday_holiday_boundary(self):
        history=pd.Series([pd.Timestamp(day)+pd.Timedelta(slot) for day in pd.bdate_range('2026-09-01','2026-09-30') for slot in ['00:30:00','09:30:00','15:00:00','21:30:00']])
        history=history[history<=pd.Timestamp('2026-09-30 15:00')]
        result=future_timestamps(history,4,'SHFE')
        self.assertEqual(list(result.dt.strftime('%Y-%m-%d %H:%M')),['2026-10-08 09:30','2026-10-08 15:00','2026-10-08 21:30','2026-10-09 00:30'])

    def test_year_coverage(self):
        with self.assertRaisesRegex(ValueError,'仅覆盖 2026'):
            future_timestamps(pd.Series(pd.bdate_range('2026-12-01','2026-12-31')),1,'DCE')
        with self.assertRaisesRegex(ValueError,'仅覆盖 2026'):
            permitted('2026-12-31 21:30')

    def test_file_mapping(self):
        for name, exchange in [('豆一主连_A0_30分钟_新浪.csv','DCE'),('棕榈油主连_P0_日线_新浪.csv','DCE'),('不锈钢主连_SS0_30分钟_新浪.csv','SHFE')]:
            self.assertEqual(resolve_calendar('auto', name), exchange)
        with self.assertRaisesRegex(ValueError,'无法自动识别'):
            resolve_calendar('auto','unknown.csv')

    def test_api_rejects_unknown_year_before_inference(self):
        class Spy:
            max_context=512
            def predict(self, **kwargs):
                raise AssertionError('Model must not be called')
        path=Path(__file__).resolve().parents[1]/'data/棕榈油主连_P0_日线_新浪.csv'
        frame=pd.DataFrame({'timestamps':pd.bdate_range(end='2026-10-22',periods=500),
                            'open':1.,'high':1.,'low':1.,'close':1.})
        with patch('webui.app.predictor',Spy()), patch('webui.app.load_data_file',return_value=(frame,None)), app.test_client() as c:
            r=c.post('/api/predict',json={'file_path':str(path),'lookback':400,'pred_len':120})
            self.assertEqual(r.status_code,400)
            self.assertIn('仅覆盖 2026',r.json['error'])

if __name__=='__main__': unittest.main()
