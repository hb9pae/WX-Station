"""RRDtool database manager for WX Station."""

import os
from typing import Any, Dict, List, Optional
import rrdtool


class RRDManager:
    """Handles creation, updating and querying of the WX-Station Round-Robin Database."""

    def __init__(self, rrd_path: str = "/home/pi/WX-Station/data/wx_station.rrd", step: int = 300):
        self.rrd_path = rrd_path
        self.step = step
        self._ensure_database()

    def _ensure_database(self, start_time: Optional[int] = None) -> None:
        """Creates the RRD file if it does not already exist."""
        if os.path.exists(self.rrd_path):
            return

        os.makedirs(os.path.dirname(os.path.abspath(self.rrd_path)), exist_ok=True)

        heartbeat = self.step * 2  # Toleriert 1 verpassten Zyklus

        # Data Sources: temp, hum, press, qnh, dew
        ds = [
            f"DS:temp:GAUGE:{heartbeat}:-50:70",
            f"DS:hum:GAUGE:{heartbeat}:0:100",
            f"DS:press:GAUGE:{heartbeat}:700:1200",
            f"DS:qnh:GAUGE:{heartbeat}:700:1200",
            f"DS:dew:GAUGE:{heartbeat}:-50:70",
        ]

        # Round Robin Archives (CF: AVERAGE, MIN, MAX):
        rras = [
            # 24h Detail
            "RRA:AVERAGE:0.5:1:288",
            "RRA:MIN:0.5:1:288",
            "RRA:MAX:0.5:1:288",
            # 7 Tage
            "RRA:AVERAGE:0.5:6:336",
            "RRA:MIN:0.5:6:336",
            "RRA:MAX:0.5:6:336",
            # 30 Tage
            "RRA:AVERAGE:0.5:24:360",
            "RRA:MIN:0.5:24:360",
            "RRA:MAX:0.5:24:360",
            # 1 Jahr
            "RRA:AVERAGE:0.5:288:365",
            "RRA:MIN:0.5:288:365",
            "RRA:MAX:0.5:288:365",
        ]

        cmd_args = [
            self.rrd_path,
            "--step", str(self.step),
        ]
        if start_time is not None:
            cmd_args.extend(["--start", str(int(start_time))])

        cmd_args.extend(ds)
        cmd_args.extend(rras)

        rrdtool.create(*cmd_args)
        print(f"RRD database created at {self.rrd_path}")

    def update(
        self,
        timestamp: float,
        temp: float,
        hum: float,
        press: float,
        qnh: float,
        dew: float
    ) -> None:
        """Inserts a new sample into the RRD database."""
        ts = int(timestamp)
        val_str = f"{ts}:{temp:.2f}:{hum:.2f}:{press:.2f}:{qnh:.2f}:{dew:.2f}"
        try:
            rrdtool.update(self.rrd_path, val_str)
        except Exception as e:
            # Falls Zeitstempel nicht strikt steigend
            print(f"RRD update error for {val_str}: {e}")

    def fetch(self, period: str = "24h") -> Dict[str, Any]:
        """Fetches consolidated time series and statistics for a given period.

        period options: '24h', '7d', '30d', '1y'
        """
        period_map = {
            "24h": "-24h",
            "7d": "-7d",
            "30d": "-30d",
            "1y": "-1y"
        }
        start_spec = period_map.get(period, "-24h")

        # AVERAGE Fetch
        result = rrdtool.fetch(self.rrd_path, "AVERAGE", "-s", start_spec, "-e", "now")
        (start_time, end_time, step_time), ds_names, rows = result

        timestamps: List[int] = []
        series: Dict[str, List[Optional[float]]] = {name: [] for name in ds_names}

        curr_t = start_time
        for row in rows:
            timestamps.append(curr_t)
            for idx, name in enumerate(ds_names):
                val = row[idx]
                series[name].append(round(val, 2) if val is not None else None)
            curr_t += step_time

        # Calculate min, max, avg for non-None values
        stats: Dict[str, Dict[str, Optional[float]]] = {}
        for name in ds_names:
            valid_vals = [v for v in series[name] if v is not None]
            if valid_vals:
                stats[name] = {
                    "min": round(min(valid_vals), 2),
                    "max": round(max(valid_vals), 2),
                    "avg": round(sum(valid_vals) / len(valid_vals), 2),
                }
            else:
                stats[name] = {"min": None, "max": None, "avg": None}

        return {
            "period": period,
            "start": start_time,
            "end": end_time,
            "step": step_time,
            "ds_names": ds_names,
            "timestamps": timestamps,
            "series": series,
            "stats": stats,
        }
