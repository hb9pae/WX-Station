"""Collector daemon orchestrating sensor reading, RAM caching, RRD updates and TCP serving."""

import argparse
import signal
import sys
import time
from typing import Optional

from wx_station.config import load_config, AppConfig
from wx_station.ram_cache import RAMCache
from wx_station.rrd_manager import RRDManager
from wx_station.sensor import (
    probe_and_create_sensor,
    read_filtered_sample,
    ISensorDriver,
    WeatherSample
)
from wx_station.tcp_server import TCPServerManager


class WXCollector:
    """The central daemon responsible for periodic sensor sampling, data persistence and serving."""

    def __init__(self, config: AppConfig):
        self.config = config
        self.running = False

        print(f"Initializing WX Collector: {config.station.name}")
        print(f"Station altitude: {config.station.altitude_m} m")

        # Initialize RAM cache & RRD
        self.cache = RAMCache(config.collector.ram_cache_path)
        self.rrd = RRDManager(config.collector.rrd_path, step=config.collector.interval_s)

        # Initialize Sensor
        self.sensor: ISensorDriver = probe_and_create_sensor(
            bus_num=config.sensor.bus,
            address=config.sensor.address
        )
        print(f"Active sensor driver: {self.sensor.model_name}")

        # Initialize TCP Server if enabled
        self.tcp_manager: Optional[TCPServerManager] = None
        if config.tcp.enabled:
            self.tcp_manager = TCPServerManager(
                host=config.tcp.host,
                port=config.tcp.port,
                cache=self.cache,
                default_format=config.tcp.format
            )

    def sample_and_record(self) -> WeatherSample:
        """Reads a filtered sample from sensor and updates RAM cache and RRD."""
        sample = read_filtered_sample(
            sensor=self.sensor,
            altitude_m=self.config.station.altitude_m,
            samples_count=self.config.sensor.samples,
            sample_delay=self.config.sensor.sample_delay
        )

        # 1. Update live cache in RAM
        self.cache.write_sample(sample, station_name=self.config.station.name)

        # 2. Update persistent RRD database
        self.rrd.update(
            timestamp=sample.timestamp,
            temp=sample.temperature,
            hum=sample.humidity,
            press=sample.pressure,
            qnh=sample.pressure_qnh,
            dew=sample.dew_point
        )

        ts_str = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(sample.timestamp))
        print(
            f"[{ts_str}] Sample recorded: "
            f"T={sample.temperature:.2f}°C, "
            f"RH={sample.humidity:.1f}%, "
            f"P={sample.pressure:.2f}hPa, "
            f"QNH={sample.pressure_qnh:.2f}hPa, "
            f"Dew={sample.dew_point:.2f}°C "
            f"({sample.sensor_model})"
        )
        return sample

    def run(self) -> None:
        """Main loop of the collector daemon."""
        self.running = True

        # Start TCP Server
        if self.tcp_manager:
            self.tcp_manager.start()

        # Immediate initial sample to populate cache and DB
        print("Taking initial sensor reading...")
        self.sample_and_record()

        interval = self.config.collector.interval_s
        print(f"Collector loop started. Next reading aligned to {interval}s interval.")

        while self.running:
            # Calculate time to next interval alignment (e.g. xx:00, xx:05, xx:10)
            now = time.time()
            next_run = (int(now) // interval + 1) * interval
            sleep_duration = max(1.0, next_run - now)

            # Sleep in 1-second chunks to respond quickly to shutdown signals
            sleep_end = time.time() + sleep_duration
            while self.running and time.time() < sleep_end:
                time.sleep(min(1.0, sleep_end - time.time()))

            if not self.running:
                break

            try:
                self.sample_and_record()
            except Exception as e:
                print(f"Error during sensor sample: {e}", file=sys.stderr)

        self.shutdown()

    def shutdown(self) -> None:
        """Graceful shutdown of all subsystems."""
        print("Shutting down WX Collector...")
        if self.tcp_manager:
            self.tcp_manager.stop()
        if self.sensor:
            self.sensor.close()
        print("WX Collector stopped cleanly.")


def main() -> None:
    parser = argparse.ArgumentParser(description="WX-Station Collector Daemon")
    parser.add_argument(
        "-c", "--config",
        default="config.ini",
        help="Path to configuration INI file"
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Take a single sample and exit"
    )
    args = parser.parse_args()

    cfg = load_config(args.config)
    collector = WXCollector(cfg)

    def handle_signal(sig, frame):
        print(f"\nReceived signal {sig}, initiating shutdown...")
        collector.running = False

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    if args.once:
        print("Running in single-sample mode (--once)...")
        collector.sample_and_record()
        collector.shutdown()
        return

    collector.run()


if __name__ == "__main__":
    main()
