# WX-Station (Raspberry Pi 4)

Wetterstation mit BME280/BMP180 I2C-Sensor, RRDtool-Historisierung, Shared-Memory RAM-Cache, TCP-Socket-Server und Web-Dashboard.

---

## 1. Architektur-Übersicht

Das System besteht aus zwei unabhängigen systemd-Diensten:

1. **`wx-collector.service` (Mess- & Datendienst):**
   - Fragt den Sensor alle 5 Minuten ab (Burst-Medianfilter gegen I2C-Störungen).
   - Unterstützt BME280 (Temp/Hum/Press), BMP280 und BMP180 (automatische Erkennung).
   - Berechnet Taupunkt (Magnus-Formel) und QNH (normierter Meereshöhendruck).
   - Schreibt Live-Werte atomar in den RAM (`/dev/shm/wx_current.json`) – **0 Belastung der SD-Karte**.
   - Aktualisiert die RRD-Datenbank (`data/wx_station.rrd`, feste Grösse: 166 KB).
   - Stellt einen TCP-Socket auf Port `4001` bereit (sofortige Plaintext-Ausgabe).

2. **`wx-web.service` (Webserver & Dashboard):**
   - Webinterface auf Port `8080`.
   - Responsive Gauges (Messuhren) via dynamischem SVG für Ist-Daten.
   - Interaktive Liniendiagramme via Chart.js für 24 Stunden, 7 Tage und 30 Tage.
   - Statistiken (Minimum, Mittelwert, Maximum) für alle Messgrössen.
   - REST API Endpunkte (`/api/current`, `/api/history`, `/api/status`).

---

## 2. Zugriff & Bedienung

### Web-Dashboard
Im Browser öffnen:
- Lokal: `http://localhost:8080`
- Im Netzwerk: `http://<Raspberry-Pi-IP>:8080` (z. B. `http://192.168.1.243:8080`)

### TCP-Schnittstelle
Messwerte direkt im Netzwerk abfragen:
```bash
nc localhost 4001
# Ausgabe: TEMP:23.80;HUM:0.00;PRESS:979.40;QNH:1031.17;DEW:0.00;TS:1791733501
```
Interaktive Kommandos: `GET`, `JSON`, `PLAIN`, `QUIT`.

### REST API
- Aktueller Messwert: `curl http://localhost:8080/api/current`
- 24h-Historie & Stats: `curl http://localhost:8080/api/history?period=24h`
- 7d-Wochenhistorie: `curl http://localhost:8080/api/history?period=7d`
- 30d-Monatshistorie: `curl http://localhost:8080/api/history?period=30d`
- Status & Sensor: `curl http://localhost:8080/api/status`

---

## 3. Konfiguration

Die Einstellungen befinden sich in `config.yaml`:
```yaml
station:
  name: "WX-Station Raspberry Pi 4"
  altitude_m: 450.0  # Stationshöhe für QNH-Berechnung

sensor:
  bus: 1             # I2C-Bus (/dev/i2c-1)
  address: "auto"    # "auto", 0x76 oder 0x77
  samples: 3         # Median-Burst-Samples
  sample_delay: 0.5

collector:
  interval_s: 300    # 5 Minuten
  ram_cache_path: "/dev/shm/wx_current.json"
  rrd_path: "/home/pi/WX-Station/data/wx_station.rrd"

tcp:
  enabled: true
  host: "0.0.0.0"
  port: 4001
  format: "plaintext"

web:
  host: "0.0.0.0"
  port: 8080
  refresh_interval_s: 15
```

---

## 4. Dienstverwaltung (systemd)

Status prüfen:
```bash
systemctl status wx-collector.service wx-web.service
```

Logs live verfolgen:
```bash
journalctl -u wx-collector.service -f
journalctl -u wx-web.service -f
```

Neustart:
```bash
sudo systemctl restart wx-collector.service
sudo systemctl restart wx-web.service
```

---

## 5. Tests ausführen

```bash
python3 -m unittest discover tests
```
