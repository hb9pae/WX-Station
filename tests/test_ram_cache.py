"""Unit tests for RAMCache."""

import os
import shutil
import tempfile
import time
import unittest
from wx_station.ram_cache import RAMCache
from wx_station.sensor import WeatherSample


class TestRAMCache(unittest.TestCase):

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.cache_file = os.path.join(self.test_dir, "wx_test.json")
        self.cache = RAMCache(cache_path=self.cache_file)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_write_and_read_sample(self):
        sample = WeatherSample(
            timestamp=time.time(),
            temperature=21.45,
            humidity=55.2,
            pressure=1012.30,
            pressure_qnh=1023.50,
            dew_point=12.10,
            sensor_model="BME280"
        )
        self.cache.write_sample(sample, station_name="Test-Station")

        read_back = self.cache.read_sample()
        self.assertIsNotNone(read_back)
        self.assertEqual(read_back["station"], "Test-Station")
        self.assertEqual(read_back["temperature"], 21.45)
        self.assertEqual(read_back["humidity"], 55.2)
        self.assertEqual(read_back["pressure"], 1012.30)
        self.assertEqual(read_back["pressure_qnh"], 1023.50)
        self.assertEqual(read_back["dew_point"], 12.10)
        self.assertEqual(read_back["sensor_model"], "BME280")
        self.assertIn("iso_time", read_back)


if __name__ == "__main__":
    unittest.main()
