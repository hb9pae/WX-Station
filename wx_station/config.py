"""Configuration loader for WX Station using configparser."""

import configparser
import os
from dataclasses import dataclass
from typing import Union


@dataclass
class StationConfig:
    name: str = "WX-Station Raspberry Pi 4"
    altitude_m: float = 450.0


@dataclass
class SensorConfig:
    bus: int = 1
    address: Union[str, int] = "auto"
    samples: int = 3
    sample_delay: float = 0.5


@dataclass
class CollectorConfig:
    interval_s: int = 300
    ram_cache_path: str = "/dev/shm/wx_current.json"
    rrd_path: str = "/home/pi/WX-Station/data/wx_station.rrd"


@dataclass
class TcpConfig:
    enabled: bool = True
    host: str = "0.0.0.0"
    port: int = 4001
    format: str = "plaintext"


@dataclass
class WebConfig:
    host: str = "0.0.0.0"
    port: int = 8080
    refresh_interval_s: int = 15
    title: str = "WX-Station Wetter Dashboard"
    theme: str = "dark"


@dataclass
class AppConfig:
    station: StationConfig
    sensor: SensorConfig
    collector: CollectorConfig
    tcp: TcpConfig
    web: WebConfig


def _parse_address(addr_raw: str) -> Union[str, int]:
    """Parses I2C address string into int (hex or decimal) or 'auto'."""
    trimmed = addr_raw.strip().strip("'\"")
    if trimmed.lower() == "auto":
        return "auto"
    if trimmed.lower().startswith("0x"):
        try:
            return int(trimmed, 16)
        except ValueError:
            return trimmed
    try:
        return int(trimmed)
    except ValueError:
        return trimmed


def load_config(config_path: str = "config.ini") -> AppConfig:
    """Loads configuration from INI file with fallbacks to defaults."""
    parser = configparser.ConfigParser(inline_comment_prefixes=("#", ";"))

    if os.path.exists(config_path):
        try:
            parser.read(config_path, encoding="utf-8")
        except Exception as e:
            print(f"Warning: Failed to load {config_path}: {e}. Using defaults.")
    else:
        # Check if legacy config.yaml or config.ini exists in project root
        if config_path == "config.ini" and not os.path.exists("config.ini") and os.path.exists("config.yaml"):
            print("Notice: config.ini not found, but config.yaml exists. Please migrate to config.ini.")

    # Station
    station_name = parser.get("station", "name", fallback="WX-Station Raspberry Pi 4").strip()
    try:
        altitude_m = parser.getfloat("station", "altitude_m", fallback=450.0)
    except ValueError:
        altitude_m = 450.0

    station = StationConfig(
        name=station_name,
        altitude_m=altitude_m,
    )

    # Sensor
    try:
        sensor_bus = parser.getint("sensor", "bus", fallback=1)
    except ValueError:
        sensor_bus = 1

    sensor_addr_raw = parser.get("sensor", "address", fallback="auto")
    sensor_addr = _parse_address(sensor_addr_raw)

    try:
        sensor_samples = parser.getint("sensor", "samples", fallback=3)
    except ValueError:
        sensor_samples = 3

    try:
        sensor_sample_delay = parser.getfloat("sensor", "sample_delay", fallback=0.5)
    except ValueError:
        sensor_sample_delay = 0.5

    sensor = SensorConfig(
        bus=sensor_bus,
        address=sensor_addr,
        samples=sensor_samples,
        sample_delay=sensor_sample_delay,
    )

    # Collector
    try:
        collector_interval = parser.getint("collector", "interval_s", fallback=300)
    except ValueError:
        collector_interval = 300

    collector_ram_cache = parser.get(
        "collector", "ram_cache_path", fallback="/dev/shm/wx_current.json"
    ).strip()
    collector_rrd = parser.get(
        "collector", "rrd_path", fallback="/home/pi/WX-Station/data/wx_station.rrd"
    ).strip()

    collector = CollectorConfig(
        interval_s=collector_interval,
        ram_cache_path=collector_ram_cache,
        rrd_path=collector_rrd,
    )

    # TCP
    try:
        tcp_enabled = parser.getboolean("tcp", "enabled", fallback=True)
    except ValueError:
        tcp_enabled = True

    tcp_host = parser.get("tcp", "host", fallback="0.0.0.0").strip()
    try:
        tcp_port = parser.getint("tcp", "port", fallback=4001)
    except ValueError:
        tcp_port = 4001
    tcp_format = parser.get("tcp", "format", fallback="plaintext").strip().lower()

    tcp = TcpConfig(
        enabled=tcp_enabled,
        host=tcp_host,
        port=tcp_port,
        format=tcp_format,
    )

    # Web
    web_host = parser.get("web", "host", fallback="0.0.0.0").strip()
    try:
        web_port = parser.getint("web", "port", fallback=8080)
    except ValueError:
        web_port = 8080

    try:
        web_refresh = parser.getint("web", "refresh_interval_s", fallback=15)
    except ValueError:
        web_refresh = 15

    web_title = parser.get("web", "title", fallback=station_name).strip()
    if not web_title:
        web_title = station_name

    web_theme = parser.get("web", "theme", fallback="dark").strip().lower()
    if web_theme not in ("dark", "light"):
        web_theme = "dark"

    web = WebConfig(
        host=web_host,
        port=web_port,
        refresh_interval_s=web_refresh,
        title=web_title,
        theme=web_theme,
    )

    return AppConfig(
        station=station,
        sensor=sensor,
        collector=collector,
        tcp=tcp,
        web=web,
    )
