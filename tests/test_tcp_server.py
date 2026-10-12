"""Integration tests for TCP server."""

import json
import os
import shutil
import socket
import tempfile
import time
import unittest
from wx_station.ram_cache import RAMCache
from wx_station.sensor import WeatherSample
from wx_station.tcp_server import TCPServerManager


class TestTCPServer(unittest.TestCase):

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.cache_file = os.path.join(self.test_dir, "wx_tcp_test.json")
        self.cache = RAMCache(cache_path=self.cache_file)

        # Seed sample data
        sample = WeatherSample(
            timestamp=1700000000.0,
            temperature=19.50,
            humidity=58.20,
            pressure=1013.25,
            pressure_qnh=1024.10,
            dew_point=11.02,
            sensor_model="BME280"
        )
        self.cache.write_sample(sample, station_name="TCP-Test-Station")

        # Pick a free random port
        self.port = 49152 + (os.getpid() % 10000)
        self.server_mgr = TCPServerManager(host="127.0.0.1", port=self.port, cache=self.cache, default_format="plaintext")
        self.server_mgr.start()
        time.sleep(0.1)

    def tearDown(self):
        self.server_mgr.stop()
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_plaintext_query_on_connect(self):
        s = socket.create_connection(("127.0.0.1", self.port), timeout=2.0)
        sf = s.makefile("r", encoding="utf-8")
        line = sf.readline()
        self.assertTrue(line.startswith("TEMP:19.50;HUM:58.20;PRESS:1013.25;QNH:1024.10;DEW:11.02"))

        # Send JSON command
        s.sendall(b"JSON\n")
        json_line = sf.readline()
        parsed = json.loads(json_line)
        self.assertEqual(parsed["temperature"], 19.50)
        self.assertEqual(parsed["station"], "TCP-Test-Station")

        # Send QUIT
        s.sendall(b"QUIT\n")
        s.close()


if __name__ == "__main__":
    unittest.main()
