import unittest
from unittest.mock import patch
import pandas as pd
from webui.trading_calendar import is_trading_day, permitted, resolve_calendar, stock_period_timestamps
from webui.app import app, future_timestamps

class StockCalendarTests(unittest.TestCase):
    def test_holidays_and_makeup_weekends(self):
        for day in ['2026-01-01','2026-02-23','2026-04-06','2026-05-05','2026-06-19','2026-09-25','2026-10-07','2026-02-14','2026-02-28','2026-05-09','2026-09-20','2026-10-10']:
            with self.subTest(day=day): self.assertFalse(is_trading_day(day,'CN_A'))
        for day in ['2026-01-05','2026-02-24','2026-04-07','2026-05-06','2026-06-22','2026-09-28','2026-10-08']:
            self.assertTrue(is_trading_day(day,'CN_A'))

    def test_lunch_and_night_closed(self):
        for slot in ['09:25','12:00','12:59','15:30','21:00','01:00']:
            self.assertFalse(permitted('2026-10-08 '+slot,exchange='CN_A'))
        for slot in ['09:30','11:30','13:00','15:00']:
            self.assertTrue(permitted('2026-10-08 '+slot,exchange='CN_A'))

    def test_daily_skips_national_day(self):
        values=future_timestamps(pd.to_datetime(['2026-09-29','2026-09-30']),3,'CN_A')
        self.assertEqual(values.dt.strftime('%Y-%m-%d').tolist(),['2026-10-08','2026-10-09','2026-10-12'])

    def test_intraday_preserves_slots_skips_lunch_and_holiday(self):
        history=pd.to_datetime(['2026-09-29 10:00','2026-09-29 11:30','2026-09-29 12:00','2026-09-29 13:30','2026-09-29 15:00','2026-09-29 21:00','2026-09-30 11:30'])
        result=future_timestamps(history,4,'CN_A')
        self.assertEqual(result.dt.strftime('%Y-%m-%d %H:%M').tolist(),['2026-09-30 13:30','2026-09-30 15:00','2026-10-08 10:00','2026-10-08 11:30'])

    def test_periods_use_last_trading_day_and_skip_closed_week(self):
        self.assertEqual(stock_period_timestamps('2026-09-18',2,'weekly').dt.strftime('%Y-%m-%d').tolist(),['2026-09-24','2026-09-30'])
        self.assertEqual(stock_period_timestamps('2026-02-13',1,'weekly').iloc[0],pd.Timestamp('2026-02-27'))
        self.assertEqual(stock_period_timestamps('2026-09-30',1,'monthly').iloc[0],pd.Timestamp('2026-10-30'))

    def test_unknown_year_rejected(self):
        with self.assertRaisesRegex(ValueError,'2026'): is_trading_day('2027-01-04','CN_A')
        with self.assertRaisesRegex(ValueError,'2026'): future_timestamps(pd.to_datetime(['2026-12-30','2026-12-31']),1,'CN_A')
        with self.assertRaisesRegex(ValueError,'2026'): stock_period_timestamps('2026-12-31',1,'monthly')

    def test_auto_recognizes_all_stock_exchanges(self):
        for symbol in ['sh600519','sz000001','bj920000']:
            self.assertEqual(resolve_calendar('auto',f'/data/sina_{symbol}_30.csv'),'CN_A')

    def test_old_stock_metadata_upgraded_and_no_futures_calendar(self):
        frame=pd.DataFrame(dict(timestamps=pd.to_datetime(['2026-09-29','2026-09-30']),open=[1]*2,high=[1]*2,low=[1]*2,close=[1]*2,volume=[2]*2))
        class Predictor:
            max_context=512
            def predict(self,**kw):
                return pd.DataFrame(dict(open=1.,high=1.,low=1.,close=1.,volume=2.),index=kw['y_timestamp'])
        with patch('webui.app.load_data_file',return_value=(frame,None)), patch('webui.app.predictor',Predictor()), patch('webui.app.market_data.metadata',return_value={'kind':'stock','calendar':'none','period':'daily'}), patch('webui.app.save_prediction_results'), app.test_client() as client:
            response=client.post('/api/predict',json={'file_path':'old.csv','lookback':2,'pred_len':1,'calendar':'DCE'})
            self.assertEqual(response.status_code,200,response.json)
            self.assertEqual(response.json['calendar'],'CN_A')
            self.assertEqual(response.json['forecast_start'][:10],'2026-10-08')
            self.assertIn('A 股',response.json['timestamp_note'])
