import json
import unittest
import pandas as pd
from webui.app import create_prediction_chart

class ChartTests(unittest.TestCase):
    def frames(self):
        history = pd.DataFrame(dict(timestamps=pd.to_datetime(['2026-10-23', '2026-10-26']),
            open=[10, 12], high=[12, 13], low=[9, 10], close=[11, 11], volume=[100, 200]))
        future = history.drop(columns='timestamps').iloc[:1].copy()
        future.index = pd.to_datetime(['2026-10-27'])
        return history, future

    def test_volume_aligned_and_separate_scale(self):
        h, p = self.frames()
        chart = json.loads(create_prediction_chart(h, p))
        candles = [t for t in chart['data'] if t['type'] == 'candlestick']
        bars = [t for t in chart['data'] if t['type'] == 'bar']
        self.assertEqual([t['name'] for t in bars], ['历史成交量', '预测成交量'])
        for candle, bar in zip(candles, bars):
            self.assertEqual(candle['x'], bar['x'])
            self.assertEqual(bar['yaxis'], 'y2')
        self.assertEqual(bars[0]['y'], [100, 200])
        self.assertEqual(bars[0]['marker']['color'], ['#26A69A', '#EF5350'])
        self.assertLess(chart['layout']['yaxis2']['domain'][1], chart['layout']['yaxis']['domain'][0])
        self.assertEqual(chart['layout']['xaxis']['type'], 'category')

    def test_absent_volume_has_no_bars(self):
        h, p = self.frames()
        chart = json.loads(create_prediction_chart(h.drop(columns='volume'), p))
        self.assertEqual(len(chart['data']), 2)
        self.assertNotIn('yaxis2', chart['layout'])

    def test_invalid_volume_is_gap(self):
        h, p = self.frames()
        h['volume'] = [-1, float('nan')]
        chart = json.loads(create_prediction_chart(h, p))
        bars = [t for t in chart['data'] if t['type'] == 'bar']
        self.assertEqual(bars[0]['y'], [None, None])
