"""Unit and integration tests for the Flask web service and REST API."""

import os
import shutil
import tempfile
import time
import unittest

from wx_station.config import AppConfig, StationConfig, SensorConfig, CollectorConfig, TcpConfig, WebConfig
from wx_station.ram_cache import RAMCache
from wx_station.rrd_manager import RRDManager
from wx_station.sensor import WeatherSample
from wx_station.web import create_app


class TestWebService(unittest.TestCase):

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.rrd_path = os.path.join(self.test_dir, "web_test.rrd")
        self.cache_path = os.path.join(self.test_dir, "web_test.json")

        self.cfg = AppConfig(
            station=StationConfig(name="Web-Test Station", altitude_m=450.0),
            sensor=SensorConfig(bus=1, address="auto"),
            collector=CollectorConfig(interval_s=300, ram_cache_path=self.cache_path, rrd_path=self.rrd_path),
            tcp=TcpConfig(enabled=False),
            web=WebConfig(host="127.0.0.1", port=8080, refresh_interval_s=10),
        )

        # Seed RRD
        self.rrd = RRDManager(self.rrd_path, step=300)
        now = int(time.time())
        if os.path.exists(self.rrd_path):
            os.remove(self.rrd_path)
        self.rrd._ensure_database(start_time=now - 600)
        self.rrd.update(now - 300, temp=22.0, hum=55.0, press=980.0, qnh=1031.0, dew=12.0)
        self.rrd.update(now, temp=22.5, hum=56.0, press=979.8, qnh=1030.8, dew=12.3)

        # Seed RAM Cache
        self.cache = RAMCache(self.cache_path)
        sample = WeatherSample(
            timestamp=float(now),
            temperature=22.5,
            humidity=56.0,
            pressure=979.8,
            pressure_qnh=1030.8,
            dew_point=12.3,
            sensor_model="BME280"
        )
        self.cache.write_sample(sample, station_name=self.cfg.station.name)

        self.app = create_app(self.cfg)
        self.client = self.app.test_client()

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_index_page(self):
        res = self.client.get("/")
        self.assertEqual(res.status_code, 200)
        self.assertIn(b"Web-Test Station", res.data)
        self.assertIn(b"gauge-temp", res.data)
        self.assertIn(b"historyChart", res.data)

    def test_api_current(self):
        res = self.client.get("/api/current")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data["temperature"], 22.5)
        self.assertEqual(data["humidity"], 56.0)
        self.assertEqual(data["sensor_model"], "BME280")
        self.assertEqual(data["station"], "Web-Test Station")

    def test_api_history(self):
        res = self.client.get("/api/history?period=24h")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertIn("series", data)
        self.assertIn("stats", data)
        self.assertIn("temp", data["series"])
        self.assertIn("qnh", data["series"])

    def test_api_status(self):
        res = self.client.get("/api/status")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data["status"], "online")
        self.assertEqual(data["station_name"], "Web-Test Station")
        self.assertEqual(data["sensor_model"], "BME280")

    def test_health(self):
        res = self.client.get("/health")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.get_json(), {"status": "ok"})


if __name__ == "__main__":
    unittest.main()
