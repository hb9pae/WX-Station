"""Atomic RAM cache manager for live WX data."""

import json
import os
import tempfile
from typing import Any, Dict, Optional
from wx_station.sensor import WeatherSample


class RAMCache:
    """Provides atomic read and write access to live sensor data in RAM (/dev/shm)."""

    def __init__(self, cache_path: str = "/dev/shm/wx_current.json"):
        self.cache_path = cache_path
        # Falls /dev/shm nicht schreibbar ist (z. B. spezielle Umgebungen), Fallback auf /tmp
        parent_dir = os.path.dirname(self.cache_path)
        if not os.path.exists(parent_dir) or not os.access(parent_dir, os.W_OK):
            self.cache_path = "/tmp/wx_current.json"

    def write_sample(self, sample: WeatherSample, station_name: str = "WX-Station") -> None:
        """Atomically writes the weather sample to JSON in shared memory."""
        data = {
            "station": station_name,
            "timestamp": sample.timestamp,
            "iso_time": time_iso(sample.timestamp),
            "temperature": sample.temperature,
            "humidity": sample.humidity,
            "pressure": sample.pressure,
            "pressure_qnh": sample.pressure_qnh,
            "dew_point": sample.dew_point,
            "sensor_model": sample.sensor_model,
        }
        self.write_dict(data)

    def write_dict(self, data: Dict[str, Any]) -> None:
        """Atomically writes a dictionary to the cache file using a temporary file."""
        target_dir = os.path.dirname(os.path.abspath(self.cache_path))
        os.makedirs(target_dir, exist_ok=True)

        payload = json.dumps(data, indent=2)

        # Atomic write: Write to temp file in same directory, then rename
        with tempfile.NamedTemporaryFile("w", dir=target_dir, delete=False, encoding="utf-8") as tf:
            tf.write(payload)
            temp_name = tf.name

        os.replace(temp_name, self.cache_path)

    def read_sample(self) -> Optional[Dict[str, Any]]:
        """Reads the current live sample from the cache file."""
        if not os.path.exists(self.cache_path):
            return None
        try:
            with open(self.cache_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"Error reading RAM cache {self.cache_path}: {e}")
            return None


def time_iso(timestamp: float) -> str:
    """Formats unix timestamp to ISO-8601 UTC string."""
    import datetime
    return datetime.datetime.fromtimestamp(timestamp, tz=datetime.timezone.utc).isoformat()
