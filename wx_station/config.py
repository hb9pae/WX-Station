"""Configuration loader for WX Station."""

import os
from dataclasses import dataclass
from typing import Any, Dict
import yaml


@dataclass
class StationConfig:
    name: str = "WX-Station Raspberry Pi 4"
    altitude_m: float = 450.0


@dataclass
class SensorConfig:
    bus: int = 1
    address: str | int = "auto"
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


@dataclass
class AppConfig:
    station: StationConfig
    sensor: SensorConfig
    collector: CollectorConfig
    tcp: TcpConfig
    web: WebConfig


def load_config(config_path: str = "config.yaml") -> AppConfig:
    """Loads configuration from yaml file with fallbacks to defaults."""
    cfg: Dict[str, Any] = {}
    if os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                cfg = yaml.safe_load(f) or {}
        except Exception as e:
            print(f"Warning: Failed to load {config_path}: {e}. Using defaults.")

    station_dict = cfg.get("station", {})
    sensor_dict = cfg.get("sensor", {})
    collector_dict = cfg.get("collector", {})
    tcp_dict = cfg.get("tcp", {})
    web_dict = cfg.get("web", {})

    station = StationConfig(
        name=station_dict.get("name", "WX-Station Raspberry Pi 4"),
        altitude_m=float(station_dict.get("altitude_m", 450.0)),
    )

    addr = sensor_dict.get("address", "auto")
    if isinstance(addr, str) and addr.lower() != "auto":
        addr = int(addr, 16) if addr.startswith("0x") else int(addr)

    sensor = SensorConfig(
        bus=int(sensor_dict.get("bus", 1)),
        address=addr,
        samples=int(sensor_dict.get("samples", 3)),
        sample_delay=float(sensor_dict.get("sample_delay", 0.5)),
    )

    collector = CollectorConfig(
        interval_s=int(collector_dict.get("interval_s", 300)),
        ram_cache_path=str(collector_dict.get("ram_cache_path", "/dev/shm/wx_current.json")),
        rrd_path=str(collector_dict.get("rrd_path", "/home/pi/WX-Station/data/wx_station.rrd")),
    )

    tcp = TcpConfig(
        enabled=bool(tcp_dict.get("enabled", True)),
        host=str(tcp_dict.get("host", "0.0.0.0")),
        port=int(tcp_dict.get("port", 4001)),
        format=str(tcp_dict.get("format", "plaintext")),
    )

    web = WebConfig(
        host=str(web_dict.get("host", "0.0.0.0")),
        port=int(web_dict.get("port", 8080)),
        refresh_interval_s=int(web_dict.get("refresh_interval_s", 15)),
    )

    return AppConfig(
        station=station,
        sensor=sensor,
        collector=collector,
        tcp=tcp,
        web=web,
    )
