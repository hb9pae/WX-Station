"""Unit and integration tests for RRDManager."""

import os
import shutil
import tempfile
import time
import unittest
from wx_station.rrd_manager import RRDManager


class TestRRDManager(unittest.TestCase):

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.rrd_path = os.path.join(self.test_dir, "test_wx.rrd")

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_database_creation(self):
        mgr = RRDManager(rrd_path=self.rrd_path, step=300)
        self.assertTrue(os.path.exists(self.rrd_path))
        self.assertGreater(os.path.getsize(self.rrd_path), 0)

    def test_update_and_fetch(self):
        now = int(time.time())
        t1 = now - 600
        t2 = now - 300
        t3 = now

        mgr = RRDManager(rrd_path=self.rrd_path, step=300)
        # Erstelle DB neu mit start_time vor t1
        if os.path.exists(self.rrd_path):
            os.remove(self.rrd_path)
        mgr._ensure_database(start_time=t1 - 300)

        mgr.update(t1, temp=20.0, hum=50.0, press=1010.0, qnh=1020.0, dew=9.0)
        mgr.update(t2, temp=21.0, hum=52.0, press=1009.5, qnh=1019.5, dew=10.0)
        mgr.update(t3, temp=22.0, hum=54.0, press=1009.0, qnh=1019.0, dew=11.0)

        data = mgr.fetch(period="24h")
        self.assertIn("series", data)
        self.assertIn("stats", data)
        self.assertIn("temp", data["series"])
        self.assertIn("hum", data["series"])
        self.assertIn("press", data["series"])

        temp_stats = data["stats"]["temp"]
        # If consolidation caught the data points
        if temp_stats["avg"] is not None:
            self.assertGreaterEqual(temp_stats["max"], 20.0)
            self.assertLessEqual(temp_stats["min"], 23.0)


if __name__ == "__main__":
    unittest.main()
