"""Unit tests for sensor calculations and drivers."""

import unittest
from wx_station.sensor import (
    calculate_dew_point,
    calculate_qnh,
    MockSensorDriver,
    read_filtered_sample,
)


class TestSensorCalculations(unittest.TestCase):

    def test_dew_point_standard(self):
        # At 20°C and 50% relative humidity, dew point is approx 9.27°C
        dp = calculate_dew_point(20.0, 50.0)
        self.assertAlmostEqual(dp, 9.27, places=1)

    def test_dew_point_100_percent(self):
        # At 100% RH, dew point should equal temperature
        dp = calculate_dew_point(15.0, 100.0)
        self.assertAlmostEqual(dp, 15.0, places=1)

    def test_dew_point_zero_humidity(self):
        dp = calculate_dew_point(20.0, 0.0)
        self.assertEqual(dp, 20.0)

    def test_qnh_sea_level(self):
        # At altitude 0, QNH equals station pressure
        qnh = calculate_qnh(1013.25, 0.0, 15.0)
        self.assertEqual(qnh, 1013.25)

    def test_qnh_altitude_compensation(self):
        # At 450m elevation, QFE 960 hPa -> QNH is higher (approx 1012 hPa)
        qnh = calculate_qnh(960.0, 450.0, 15.0)
        self.assertGreater(qnh, 960.0)
        self.assertAlmostEqual(qnh, 1012.3, delta=2.0)

    def test_mock_sensor_reading(self):
        sensor = MockSensorDriver(temp=22.0, hum=60.0, press=1000.0)
        reading = sensor.read()
        self.assertEqual(reading.sensor_model, "MockSensor")
        self.assertAlmostEqual(reading.temperature, 22.0, delta=1.0)
        self.assertAlmostEqual(reading.humidity, 60.0, delta=3.0)
        self.assertAlmostEqual(reading.pressure, 1000.0, delta=2.0)
        sensor.close()

    def test_read_filtered_sample(self):
        sensor = MockSensorDriver(temp=20.0, hum=50.0, press=980.0)
        sample = read_filtered_sample(sensor, altitude_m=450.0, samples_count=3, sample_delay=0.01)
        self.assertIsNotNone(sample.timestamp)
        self.assertAlmostEqual(sample.temperature, 20.0, delta=1.5)
        self.assertGreater(sample.pressure_qnh, sample.pressure)
        sensor.close()


if __name__ == "__main__":
    unittest.main()
