"""Web service and REST API for WX Station."""

import argparse
import os
from typing import Optional
from flask import Flask, jsonify, render_template, request

from wx_station.config import load_config, AppConfig
from wx_station.ram_cache import RAMCache
from wx_station.rrd_manager import RRDManager


def create_app(config: Optional[AppConfig] = None) -> Flask:
    """Creates and configures the Flask application."""
    if config is None:
        config = load_config()

    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    template_dir = os.path.join(base_dir, "templates")
    static_dir = os.path.join(base_dir, "static")

    app = Flask(
        __name__,
        template_folder=template_dir,
        static_folder=static_dir
    )

    cache = RAMCache(config.collector.ram_cache_path)
    rrd = RRDManager(config.collector.rrd_path, step=config.collector.interval_s)

    @app.route("/")
    def index():
        return render_template(
            "index.html",
            station_name=config.station.name,
            altitude_m=config.station.altitude_m,
            refresh_interval=config.web.refresh_interval_s,
        )

    @app.route("/api/current")
    def api_current():
        """Returns the most recent weather sample from shared memory."""
        data = cache.read_sample()
        if not data:
            return jsonify({
                "error": "No sensor data available yet",
                "station": config.station.name
            }), 503
        return jsonify(data)

    @app.route("/api/history")
    def api_history():
        """Returns historical time-series data and min/max/avg stats from RRD."""
        period = request.args.get("period", "24h").lower()
        if period not in ("24h", "7d", "30d", "1y"):
            period = "24h"

        try:
            hist_data = rrd.fetch(period=period)
            return jsonify(hist_data)
        except Exception as e:
            return jsonify({"error": f"Failed to fetch RRD history: {str(e)}"}), 500

    @app.route("/api/status")
    def api_status():
        """Returns general station configuration and status."""
        current = cache.read_sample()
        return jsonify({
            "status": "online" if current else "waiting_for_data",
            "station_name": config.station.name,
            "altitude_m": config.station.altitude_m,
            "sensor_model": current.get("sensor_model", "Unknown") if current else "Unknown",
            "last_reading": current.get("iso_time") if current else None,
            "rrd_database": config.collector.rrd_path,
        })

    @app.route("/health")
    def health():
        return jsonify({"status": "ok"})

    return app


def main():
    parser = argparse.ArgumentParser(description="WX-Station Web Service")
    parser.add_argument("-c", "--config", default="config.yaml", help="Path to configuration file")
    parser.add_argument("-p", "--port", type=int, default=None, help="Override port")
    args = parser.parse_args()

    cfg = load_config(args.config)
    port = args.port or cfg.web.port

    app = create_app(cfg)
    print(f"Starting WX-Station Web Dashboard on http://{cfg.web.host}:{port}")
    app.run(host=cfg.web.host, port=port, debug=False)


if __name__ == "__main__":
    main()
