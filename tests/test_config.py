"""Unit tests for configuration loader and INI parser."""

import os
import shutil
import tempfile
import unittest

from wx_station.config import load_config, _parse_address, AppConfig


class TestConfig(unittest.TestCase):

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.ini_path = os.path.join(self.test_dir, "test_config.ini")

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_default_fallbacks_when_file_not_found(self):
        cfg = load_config(os.path.join(self.test_dir, "non_existent.ini"))
        self.assertIsInstance(cfg, AppConfig)
        self.assertEqual(cfg.station.name, "WX-Station Raspberry Pi 4")
        self.assertEqual(cfg.station.altitude_m, 450.0)
        self.assertEqual(cfg.sensor.bus, 1)
        self.assertEqual(cfg.sensor.address, "auto")
        self.assertEqual(cfg.sensor.samples, 3)
        self.assertEqual(cfg.sensor.sample_delay, 0.5)
        self.assertEqual(cfg.collector.interval_s, 300)
        self.assertTrue(cfg.tcp.enabled)
        self.assertEqual(cfg.tcp.port, 4001)
        self.assertEqual(cfg.web.port, 8080)
        self.assertEqual(cfg.web.theme, "dark")
        self.assertEqual(cfg.web.title, "WX-Station Raspberry Pi 4")

    def test_parse_address(self):
        self.assertEqual(_parse_address("auto"), "auto")
        self.assertEqual(_parse_address("AUTO"), "auto")
        self.assertEqual(_parse_address("0x76"), 0x76)
        self.assertEqual(_parse_address("0x77"), 0x77)
        self.assertEqual(_parse_address("118"), 118)
        self.assertEqual(_parse_address('"0x76"'), 0x76)

    def test_load_custom_ini(self):
        content = """
[station]
name = Wetterstation Säntis
altitude_m = 2501.9

[sensor]
bus = 2
address = 0x77
samples = 5
sample_delay = 1.0

[collector]
interval_s = 60
ram_cache_path = /tmp/ram.json
rrd_path = /tmp/weather.rrd

[tcp]
enabled = false
host = 127.0.0.1
port = 5000
format = json

[web]
host = 127.0.0.1
port = 9090
refresh_interval_s = 30
title = Säntis Wetter Dashboard Live
theme = light
"""
        with open(self.ini_path, "w", encoding="utf-8") as f:
            f.write(content)

        cfg = load_config(self.ini_path)
        self.assertEqual(cfg.station.name, "Wetterstation Säntis")
        self.assertEqual(cfg.station.altitude_m, 2501.9)
        self.assertEqual(cfg.sensor.bus, 2)
        self.assertEqual(cfg.sensor.address, 0x77)
        self.assertEqual(cfg.sensor.samples, 5)
        self.assertEqual(cfg.sensor.sample_delay, 1.0)
        self.assertEqual(cfg.collector.interval_s, 60)
        self.assertEqual(cfg.collector.ram_cache_path, "/tmp/ram.json")
        self.assertEqual(cfg.collector.rrd_path, "/tmp/weather.rrd")
        self.assertFalse(cfg.tcp.enabled)
        self.assertEqual(cfg.tcp.host, "127.0.0.1")
        self.assertEqual(cfg.tcp.port, 5000)
        self.assertEqual(cfg.tcp.format, "json")
        self.assertEqual(cfg.web.host, "127.0.0.1")
        self.assertEqual(cfg.web.port, 9090)
        self.assertEqual(cfg.web.refresh_interval_s, 30)
        self.assertEqual(cfg.web.title, "Säntis Wetter Dashboard Live")
        self.assertEqual(cfg.web.theme, "light")

    def test_theme_fallback_on_invalid_value(self):
        content = """
[web]
theme = neon_blue
"""
        with open(self.ini_path, "w", encoding="utf-8") as f:
            f.write(content)

        cfg = load_config(self.ini_path)
        self.assertEqual(cfg.web.theme, "dark")

    def test_title_defaults_to_station_name_when_missing(self):
        content = """
[station]
name = Alpnach Station
[web]
# Kein title angegeben
theme = light
"""
        with open(self.ini_path, "w", encoding="utf-8") as f:
            f.write(content)

        cfg = load_config(self.ini_path)
        self.assertEqual(cfg.web.title, "Alpnach Station")


if __name__ == "__main__":
    unittest.main()
