"""Sensor drivers and calculation utilities for WX Station.

Supports:
- Bosch BME280 (Temperature, Humidity, Pressure)
- Bosch BMP280 (Temperature, Pressure)
- Bosch BMP180 (Temperature, Pressure)
- Mock Sensor (for testing and offline simulation)
"""

import math
import statistics
import struct
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional, List

try:
    import smbus2
    SMBUS_AVAILABLE = True
except ImportError:
    SMBUS_AVAILABLE = False


@dataclass
class RawSensorReading:
    temperature: float          # °C
    pressure: float             # hPa (absolut)
    humidity: Optional[float]   # % (None falls Sensor keine Feuchte liefert)
    sensor_model: str           # z. B. 'BME280', 'BMP180', 'BMP280', 'Mock'


@dataclass
class WeatherSample:
    timestamp: float            # Unix Timestamp
    temperature: float          # °C
    humidity: float             # % (0.0 bis 100.0)
    pressure: float             # hPa (absoluter Stationsdruck QFE)
    pressure_qnh: float         # hPa (auf Meereshöhe normiert QNH)
    dew_point: float            # °C (Taupunkt)
    sensor_model: str


class ISensorDriver(ABC):
    """Abstract interface for sensor drivers."""

    @abstractmethod
    def read(self) -> RawSensorReading:
        """Reads raw unadjusted values from the sensor."""
        pass

    @abstractmethod
    def close(self) -> None:
        """Closes the underlying bus connection."""
        pass

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Name of the sensor model."""
        pass


class BME280Driver(ISensorDriver):
    """Driver for Bosch BME280 and BMP280 via I2C using smbus2."""

    def __init__(self, bus_num: int = 1, address: int = 0x76):
        if not SMBUS_AVAILABLE:
            raise RuntimeError("smbus2 is not installed or available.")
        self.bus_num = bus_num
        self.address = address
        self.bus = smbus2.SMBus(self.bus_num)
        self._is_bmp280 = False

        self.chip_id = self.bus.read_byte_data(self.address, 0xD0)
        if self.chip_id == 0x58:
            self._is_bmp280 = True
        elif self.chip_id != 0x60:
            raise ValueError(f"Unknown chip ID 0x{self.chip_id:02X} for BME280/BMP280 at 0x{self.address:02X}")

        self._read_calibration()

    @property
    def model_name(self) -> str:
        return "BMP280" if self._is_bmp280 else "BME280"

    def _read_calibration(self) -> None:
        """Reads calibration parameters from BME280/BMP280 NVM."""
        # 0x88 to 0xA1 (24 bytes)
        cal1 = self.bus.read_i2c_block_data(self.address, 0x88, 24)
        (
            self.dig_T1, self.dig_T2, self.dig_T3,
            self.dig_P1, self.dig_P2, self.dig_P3,
            self.dig_P4, self.dig_P5, self.dig_P6,
            self.dig_P7, self.dig_P8, self.dig_P9
        ) = struct.unpack('<HhhHhhhhhhhh', bytes(cal1))

        if not self._is_bmp280:
            self.dig_H1 = self.bus.read_byte_data(self.address, 0xA1)
            # 0xE1 to 0xE7 (7 bytes)
            cal2 = self.bus.read_i2c_block_data(self.address, 0xE1, 7)
            self.dig_H2 = struct.unpack('<h', bytes([cal2[0], cal2[1]]))[0]
            self.dig_H3 = cal2[2]
            self.dig_H4 = (cal2[3] << 4) | (cal2[4] & 0x0F)
            if self.dig_H4 > 2047:
                self.dig_H4 -= 4096
            self.dig_H5 = (cal2[5] << 4) | (cal2[4] >> 4)
            if self.dig_H5 > 2047:
                self.dig_H5 -= 4096
            self.dig_H6 = struct.unpack('b', bytes([cal2[6]]))[0]

    def read(self) -> RawSensorReading:
        """Performs a measurement in Forced Mode and compensates values."""
        # Config oversampling:
        # ctrl_hum (0xF2): osrs_h = 1 (1x oversampling)
        if not self._is_bmp280:
            self.bus.write_byte_data(self.address, 0xF2, 0x01)

        # ctrl_meas (0xF4): osrs_t=1 (001), osrs_p=1 (001), mode=forced (01) -> 0b00100101 = 0x25
        self.bus.write_byte_data(self.address, 0xF4, 0x25)

        # Wait until measurement is complete (status register 0xF3 bit 3 is 0)
        for _ in range(20):
            time.sleep(0.01)
            status = self.bus.read_byte_data(self.address, 0xF3)
            if (status & 0x08) == 0:
                break

        # Read data registers: 0xF7 to 0xFE (8 bytes if BME280, 6 bytes if BMP280)
        count = 6 if self._is_bmp280 else 8
        data = self.bus.read_i2c_block_data(self.address, 0xF7, count)

        adc_p = (data[0] << 12) | (data[1] << 4) | (data[2] >> 4)
        adc_t = (data[3] << 12) | (data[4] << 4) | (data[5] >> 4)

        # Compensate Temperature
        var1 = (((adc_t >> 3) - (self.dig_T1 << 1)) * self.dig_T2) >> 11
        var2 = (((((adc_t >> 4) - self.dig_T1) * ((adc_t >> 4) - self.dig_T1)) >> 12) * self.dig_T3) >> 14
        t_fine = var1 + var2
        temperature = float((t_fine * 5 + 128) >> 8) / 100.0

        # Compensate Pressure
        p_var1 = t_fine - 128000
        p_var2 = p_var1 * p_var1 * self.dig_P6
        p_var2 = p_var2 + ((p_var1 * self.dig_P5) << 17)
        p_var2 = p_var2 + (self.dig_P4 << 35)
        p_var1 = ((p_var1 * p_var1 * self.dig_P3) >> 8) + ((p_var1 * self.dig_P2) << 12)
        p_var1 = (((1 << 47) + p_var1) * self.dig_P1) >> 33

        if p_var1 == 0:
            pressure = 0.0
        else:
            p = 1048576 - adc_p
            p = (((p << 31) - p_var2) * 3125) // p_var1
            p_var1 = (self.dig_P9 * (p >> 13) * (p >> 13)) >> 25
            p_var2 = (self.dig_P8 * p) >> 19
            p = ((p + p_var1 + p_var2) >> 8) + (self.dig_P7 << 4)
            pressure = float(p) / 256.0 / 100.0  # hPa

        # Compensate Humidity
        humidity: Optional[float] = None
        if not self._is_bmp280:
            adc_h = (data[6] << 8) | data[7]
            h_var = t_fine - 76800
            h_var = (((((adc_h << 14) - (self.dig_H4 << 20) - (self.dig_H5 * h_var)) + 16384) >> 15) *
                     (((((((h_var * self.dig_H6) >> 10) * (((h_var * self.dig_H3) >> 11) + 32768)) >> 10) + 2097152) *
                       self.dig_H2 + 8192) >> 14))
            h_var = h_var - (((((h_var >> 15) * (h_var >> 15)) >> 7) * self.dig_H1) >> 4)
            if h_var < 0:
                h_var = 0
            if h_var > 419430400:
                h_var = 419430400
            humidity = float(h_var >> 12) / 1024.0

        return RawSensorReading(
            temperature=temperature,
            pressure=pressure,
            humidity=humidity,
            sensor_model=self.model_name
        )

    def close(self) -> None:
        if self.bus:
            self.bus.close()


class BMP180Driver(ISensorDriver):
    """Driver for Bosch BMP180 / BMP085 via I2C using smbus2."""

    def __init__(self, bus_num: int = 1, address: int = 0x77):
        if not SMBUS_AVAILABLE:
            raise RuntimeError("smbus2 is not installed or available.")
        self.bus_num = bus_num
        self.address = address
        self.bus = smbus2.SMBus(self.bus_num)

        chip_id = self.bus.read_byte_data(self.address, 0xD0)
        if chip_id != 0x55:
            raise ValueError(f"Unknown chip ID 0x{chip_id:02X} for BMP180 at 0x{self.address:02X}")

        self._read_calibration()

    @property
    def model_name(self) -> str:
        return "BMP180"

    def _read_calibration(self) -> None:
        """Reads 22 bytes of calibration data from 0xAA."""
        cal = self.bus.read_i2c_block_data(self.address, 0xAA, 22)
        words = struct.unpack('>hhhHHHhhhhh', bytes(cal))
        (
            self.ac1, self.ac2, self.ac3,
            self.ac4, self.ac5, self.ac6,
            self.b1, self.b2, self.mb, self.mc, self.md
        ) = words

    def read(self) -> RawSensorReading:
        """Reads temperature and pressure from BMP180."""
        # 1. Read uncompensated temperature
        self.bus.write_byte_data(self.address, 0xF4, 0x2E)
        time.sleep(0.005)
        msb = self.bus.read_byte_data(self.address, 0xF6)
        lsb = self.bus.read_byte_data(self.address, 0xF7)
        ut = (msb << 8) + lsb

        x1 = ((ut - self.ac6) * self.ac5) >> 15
        x2 = (self.mc << 11) // (x1 + self.md)
        b5 = x1 + x2
        temperature = float((b5 + 8) >> 4) / 10.0

        # 2. Read uncompensated pressure (oss = 3, ultra-high resolution)
        oss = 3
        self.bus.write_byte_data(self.address, 0xF4, 0x34 + (oss << 6))
        time.sleep(0.026)
        msb = self.bus.read_byte_data(self.address, 0xF6)
        lsb = self.bus.read_byte_data(self.address, 0xF7)
        xlsb = self.bus.read_byte_data(self.address, 0xF8)
        up = ((msb << 16) + (lsb << 8) + xlsb) >> (8 - oss)

        b6 = b5 - 4000
        x1 = (self.b2 * ((b6 * b6) >> 12)) >> 11
        x2 = (self.ac2 * b6) >> 11
        x3 = x1 + x2
        b3 = (((self.ac1 * 4 + x3) << oss) + 2) // 4

        x1 = (self.ac3 * b6) >> 13
        x2 = (self.b1 * ((b6 * b6) >> 12)) >> 16
        x3 = ((x1 + x2) + 2) >> 2
        b4 = (self.ac4 * (x3 + 32768)) >> 15

        b7 = (up - b3) * (50000 >> oss)
        if b7 < 0x80000000:
            p = (b7 * 2) // b4
        else:
            p = (b7 // b4) * 2

        x1 = (p >> 8) * (p >> 8)
        x1 = (x1 * 3038) >> 16
        x2 = (-7357 * p) >> 16
        p = p + ((x1 + x2 + 3791) >> 4)
        pressure = float(p) / 100.0  # hPa

        return RawSensorReading(
            temperature=temperature,
            pressure=pressure,
            humidity=None,  # BMP180 has no humidity sensor
            sensor_model="BMP180"
        )

    def close(self) -> None:
        if self.bus:
            self.bus.close()


class MockSensorDriver(ISensorDriver):
    """Driver for simulated testing without physical hardware."""

    def __init__(self, temp: float = 21.5, hum: float = 55.0, press: float = 1013.25):
        self._temp = temp
        self._hum = hum
        self._press = press
        self._counter = 0

    @property
    def model_name(self) -> str:
        return "MockSensor"

    def read(self) -> RawSensorReading:
        self._counter += 1
        # Small realistic oscillation
        delta_t = 0.5 * math.sin(self._counter * 0.2)
        delta_h = 2.0 * math.cos(self._counter * 0.2)
        delta_p = 1.0 * math.sin(self._counter * 0.1)

        return RawSensorReading(
            temperature=round(self._temp + delta_t, 2),
            pressure=round(self._press + delta_p, 2),
            humidity=round(min(100.0, max(0.0, self._hum + delta_h)), 2),
            sensor_model=self.model_name
        )

    def close(self) -> None:
        pass


def calculate_dew_point(temperature_c: float, humidity_pct: float) -> float:
    """Calculates dew point temperature in °C using the Magnus-Tetens formula."""
    if humidity_pct <= 0.0:
        return temperature_c
    a = 17.27
    b = 237.7
    alpha = ((a * temperature_c) / (b + temperature_c)) + math.log(humidity_pct / 100.0)
    dew = (b * alpha) / (a - alpha)
    return round(dew, 2)


def calculate_qnh(pressure_hpa: float, altitude_m: float, temperature_c: float = 15.0) -> float:
    """Calculates relative sea-level barometric pressure (QNH) in hPa.

    Uses the international barometric formula:
    P_0 = P * (1 - (0.0065 * h) / (T_kelvin + 0.0065 * h)) ^ -5.255
    """
    if altitude_m <= 0.0:
        return round(pressure_hpa, 2)
    t_kelvin = temperature_c + 273.15
    lapse_rate = 0.0065
    factor = 1.0 - (lapse_rate * altitude_m) / (t_kelvin + lapse_rate * altitude_m)
    if factor <= 0:
        return round(pressure_hpa, 2)
    qnh = pressure_hpa * math.pow(factor, -5.255)
    return round(qnh, 2)


def probe_and_create_sensor(bus_num: int = 1, address: str | int = "auto") -> ISensorDriver:
    """Probes the I2C bus and creates the appropriate sensor driver."""
    if not SMBUS_AVAILABLE:
        print("Warning: smbus2 not available, falling back to MockSensorDriver.")
        return MockSensorDriver()

    addresses_to_probe: List[int] = []
    if address == "auto":
        addresses_to_probe = [0x76, 0x77]
    else:
        addresses_to_probe = [int(address)]

    last_error: Optional[Exception] = None

    for addr in addresses_to_probe:
        try:
            bus = smbus2.SMBus(bus_num)
            try:
                chip_id = bus.read_byte_data(addr, 0xD0)
            finally:
                bus.close()

            if chip_id in (0x60, 0x58):
                # BME280 or BMP280
                return BME280Driver(bus_num=bus_num, address=addr)
            elif chip_id == 0x55:
                # BMP180 / BMP085
                return BMP180Driver(bus_num=bus_num, address=addr)
            else:
                print(f"I2C device at 0x{addr:02X} has unknown chip ID 0x{chip_id:02X}")
        except Exception as e:
            last_error = e

    print(f"Warning: No supported sensor found on bus {bus_num} (Error: {last_error}). Falling back to MockSensorDriver.")
    return MockSensorDriver()


def read_filtered_sample(
    sensor: ISensorDriver,
    altitude_m: float = 450.0,
    samples_count: int = 3,
    sample_delay: float = 0.5
) -> WeatherSample:
    """Takes multiple burst samples, computes median for spike rejection, and calculates QNH & Dew Point."""
    temps: List[float] = []
    pressures: List[float] = []
    humidities: List[float] = []
    sensor_model = sensor.model_name

    for i in range(max(1, samples_count)):
        reading = sensor.read()
        temps.append(reading.temperature)
        pressures.append(reading.pressure)
        if reading.humidity is not None:
            humidities.append(reading.humidity)
        sensor_model = reading.sensor_model
        if i < samples_count - 1 and sample_delay > 0:
            time.sleep(sample_delay)

    med_temp = round(statistics.median(temps), 2)
    med_press = round(statistics.median(pressures), 2)
    # If sensor provides no humidity (e.g. BMP180), fallback to 0.0 or standard relative humidity
    med_hum = round(statistics.median(humidities), 2) if humidities else 0.0

    dew = calculate_dew_point(med_temp, med_hum) if humidities else 0.0
    qnh = calculate_qnh(med_press, altitude_m, med_temp)

    return WeatherSample(
        timestamp=time.time(),
        temperature=med_temp,
        humidity=med_hum,
        pressure=med_press,
        pressure_qnh=qnh,
        dew_point=dew,
        sensor_model=sensor_model
    )
