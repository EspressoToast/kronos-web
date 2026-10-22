import unittest
from webui.app import app, load_data_file

class WebTests(unittest.TestCase):
    def test_health(self):
        with app.test_client() as c:
            self.assertEqual(c.get('/api/health').json['status'],'ok')
    def test_ui(self):
        with app.test_client() as c:
            page=c.get('/').get_data(as_text=True)
            for marker in ['Kronos Web','refresh-data-btn','save-chart-btn','calendar-select']:
                self.assertIn(marker,page)
    def test_outside_data_rejected(self):
        frame,error=load_data_file('/etc/passwd')
        self.assertIsNone(frame)
        self.assertIn('data',error)
    def test_empty_request(self):
        with app.test_client() as c:
            self.assertEqual(c.post('/api/predict',json={}).status_code,400)
