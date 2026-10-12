# Realisierungskonzept WX-Station (Raspberry Pi 4)

Dieses Dokument baut auf dem initialen Dokument `Konzept_WX-Station.md` auf und analysiert die Anforderungen, evaluiert verschiedene Architektur- und Speicherungsansätze und liefert konkrete Umsetzungsvarianten für Hard- und Software.

---

## 1. Einleitung & Zielsetzung

Ziel des Projekts ist der Aufbau einer zuverlässigen, ressourceneffizienten und erweiterbaren Wetterstation auf Basis eines **Raspberry Pi 4**.
Ein Sensor vom Typ **BME280** erfasst alle 5 Minuten meteorologische Basisdaten:
- **Temperatur** (°C)
- **Relative Luftfeuchtigkeit** (%)
- **Luftdruck** (hPa, absolut und auf Meereshöhe normiert QNH)

Die Daten werden historisiert und über zwei Schnittstellen bereitgestellt:
1. **TCP-Schnittstelle:** Direkte Rohdaten- bzw. JSON-Abfrage der aktuellen Messwerte im Netzwerk (z. B. für Automationen, Scripts oder APRS-Telemetrie).
2. **Web-Dashboard:** Visuelle Aufbereitung mit Text, Gauge-Instrumenten für Live-Daten sowie interaktiven Liniendiagrammen für kumulierte Zeiträume (24 Stunden, 7 Tage, 30 Tage) inklusive Minimum-, Maximum- und Mittelwerten.

Besonderes Augenmerk liegt auf **Ressourceneffizienz** und **Schonung der SD-Karte** des Raspberry Pi.

---

## 2. Systemarchitektur & Servicemodell

Zur Sicherstellung von Stabilität und Modularität empfiehlt sich eine klare Trennung zwischen Datenerfassung und Datenpräsentation.

```
                    +---------------------------+
                    |       BME280 Sensor       |
                    +-------------+-------------+
                                  | I2C (GPIO 2/3)
                                  v
+---------------------------------+---------------------------------+
| Dienst 1: WX-Collector (Sensor-Daemon)                           |
|  - 5-Minuten Sampling-Timer                                       |
|  - Validierung & Kompensation                                     |
|  - Ringpuffer / Live-Cache im RAM (/dev/shm)                     |
|  - TCP-Server für Sofortabfragen (Port z.B. 4001)                |
|  - Persistierung in Datenbank                                     |
+---------------------------------+---------------------------------+
                                  |
                                  v (RRD / SQLite)
+---------------------------------+---------------------------------+
| Dienst 2: WX-Webservice & API                                     |
|  - REST / JSON API (Ist-Daten, 24h, 7d, 30d Min/Max/Avg)          |
|  - Optional WebSocket/SSE für Live-Updates                       |
|  - Integrierter HTTP-Server für Web-Frontend                      |
|  - HTML5 / CSS / JavaScript UI (Gauges + Liniendiagramme)        |
+-------------------------------------------------------------------+
```

### Architektur-Varianten für die Dienste

* **Variante S1: Zwei eigenständige systemd-Dienste (Empfohlen)**
  - `wx-collector.service`: Kümmert sich autonom um Hardwarezugriff, Datenspeicherung und TCP-Socket. Stürzt das Webinterface ab, laufen Messung und Protokollierung unterbrechungsfrei weiter.
  - `wx-web.service`: Kümmert sich um HTTP-Bereitstellung und Datenaufbereitung.
* **Variante S2: Monolithischer Dienst**
  - Ein einziger Prozess bedient I2C, TCP-Server und Webserver. 
  - *Vorteil:* Geringster RAM-Footprint, keine Interprozesskommunikation (IPC) nötig.
  - *Nachteil:* Fehler im Webserver (z. B. Speicherleck oder unvollständiger HTTP-Request) können den Messtakt blockieren.
* **Variante S3: Containerisiert (Docker / Docker Compose)**
  - *Vorteil:* Isolierte Umgebungen, einfache Portierbarkeit.
  - *Nachteil:* Höherer Overhead auf dem Raspberry Pi, I2C-Gerätedurchreichung (`/dev/i2c-1`) erforderlich.

---

## 3. Abfrage der Sensordaten (BME280)

### 3.1 Hardware-Anbindung
* **Bus:** I2C-1 des Raspberry Pi 4
  - Pin 1 (3.3V VCC)
  - Pin 3 (GPIO 2, SDA)
  - Pin 5 (GPIO 3, SCL)
  - Pin 6 oder 9 (GND)
* **I2C-Adresse:** Standardmässig `0x76` (SDO auf GND) oder `0x77` (SDO auf VCC).
* **Sensor-Selbstüberwärmung (Self-Heating):** 
  Der BME280 erwärmt sich bei kontinuierlicher Messung minimal selbst. Empfohlen ist der Betrieb im **Forced Mode**: Der Sensor schläft und wird alle 5 Minuten kurz für eine Einzelmessung aufgeweckt.

### 3.2 Robustheit & Plausibilitätsprüfungen
* **Burst-Sampling:** Zur Vermeidung von I2C-Störungen (Bitkipper) werden pro Intervall 3 Messungen im Abstand von 500 ms durchgeführt und der Median gebildet.
* **Plausibilitätsfilter:**
  - Temperatur: -40 °C bis +85 °C (Änderungsrate max. 5 °C in 5 Minuten)
  - Feuchte: 0 % bis 100 %
  - Druck: 850 hPa bis 1100 hPa
* **Berechnete Werte:**
  - Taupunkt (Dew Point) via Magnus-Formel
  - QNH (relativer Luftdruck auf Meereshöhe, berechnet aus Stationshöhe)

---

## 4. Evaluation der Speicher-Varianten

Auf einem Raspberry Pi 4 ist die Wahl der Speicherstrategie entscheidend, da ständige, unkontrollierte Schreibzugriffe die Lebensdauer der Flash-Speicherkarte (SD-Karte) drastisch verkürzen und Fragmentierung verursachen können.

### 4.1 Variante 1: RRDtool (Round-Robin Database)
* **Prinzip:** Feste, im Voraus allozierte Dateigrösse (Ringpuffer). Alte Daten werden automatisch nach definierten Konsolidierungsfunktionen (CF: `AVERAGE`, `MIN`, `MAX`) zusammengefasst.
* **Konfiguration für 5-Minuten-Takt:**
  - Schrittweite (Step): 300 Sekunden (5 Min)
  - RRA 1 (24 Stunden Detaildaten): 288 Datenpunkte (1 Tag unkomprimiert)
  - RRA 2 (Woche): Aggregation auf z. B. 30 Minuten (Faktor 6) -> 336 Datenpunkte
  - RRA 3 (Monat): Aggregation auf z. B. 2 Stunden (Faktor 24) -> 360 Datenpunkte
* **Vorteile:**
  - Konstante Dateigrösse (typisch unter 200 KB für alle Werte).
  - Keine Wartung, kein unkontrolliertes Wachstum der Dateigrösse.
  - Extrem geringe I/O-Last; automatisches Berechnen von Min, Max und Schnitt.
  - Sehr langlebig und seit Jahrzehnten auf Embedded-Systemen bewährt.
* **Nachteile:**
  - Nachträgliches Ändern der Schema-Struktur (z. B. Hinzufügen neuer Sensoren) erfordert Neuanlegen oder separate RRD-Dateien.
  - Binäres proprietäres Format; direkte relationale Abfragen nicht möglich.

### 4.2 Variante 2: SQLite mit Aggregationstabellen
* **Prinzip:** Relationale SQL-Datenbank in einer Datei (`wx_station.db`).
* **Optimierung für SD-Karten:**
  - Aktivierung des `WAL`-Modus (Write-Ahead-Logging): `PRAGMA journal_mode = WAL;`
  - Reduktion synchroner Schreibzugriffe: `PRAGMA synchronous = NORMAL;`
  - Aggregations-Tabellen (stündliche/tägliche Zusammenfassung per Trigger oder periodischem Job) zur Beschleunigung der Monatsansichten.
* **Vorteile:**
  - Höchste Flexibilität: Neue Sensoren können jederzeit über `ALTER TABLE` hinzugefügt werden.
  - SQL-Standard: Beliebige Ad-hoc-Auswertungen, einfacher Export (CSV, JSON).
  - Native Bibliotheken für nahezu jede Programmiersprache vorhanden.
* **Nachteile:**
  - Datenbank wächst stetig (bei 5-Minuten-Intervall ca. 105.000 Datensätze pro Jahr = ca. 10-15 MB pro Jahr).
  - Daten-Pruning (Bereinigung alter Rohdaten) muss selbst implementiert werden.
  - Höheres I/O-Aufkommen auf der SD-Karte als bei RRD.

### 4.3 Variante 3: InfluxDB / VictoriaMetrics
* **Prinzip:** Spezialisierte Time-Series-Datenbanken (TSDB).
* **Vorteile:**
  - Extrem mächtige Zeitreihen-Abfragesprachen (InfluxQL/Flux bzw. MetricsQL).
  - Automatische Retention Policies (Datenlöschung/Downsampling).
* **Nachteile:**
  - Deutlich höherer RAM- und CPU-Bedarf (InfluxDB v2 benötigt oft 200–500 MB RAM).
  - Für 3 Messwerte alle 5 Minuten unverhältnismässig hoher administrativer Aufwand.

### 4.4 Variante 4: Hybrider Ansatz (RAM-Puffer + RRDtool oder SQLite) – **Empfohlen**
* **Prinzip:**
  - Die jeweils letzten Messwerte und der Live-Zustand werden im RAM unter `/dev/shm/wx_live.json` (Shared Memory) gehalten.
  - Alle 5 Minuten wird ein Messpunkt in eine RRD- oder SQLite-Datenbank geschrieben.
  - TCP-Abfragen greifen direkt und latenzfrei auf den RAM zu, ohne die SD-Karte anzufassen.
* **Vorteile:**
  - Absolute SD-Karten-Schonung.
  - Ultraschnelle Reaktionszeiten für Ist-Daten und TCP-Verbindung.

### 4.5 Vergleichsmatrix

| Kriterium | RRDtool | SQLite (optimiert) | Time-Series DB (TSDB) | Hybrid (RAM + RRD/SQLite) |
| :--- | :---: | :---: | :---: | :---: |
| **Ressourcenverbrauch (RAM/CPU)** | Sehr gering (< 10 MB) | Gering (10–25 MB) | Hoch (150–500 MB) | Sehr gering (< 20 MB) |
| **Schonung der SD-Karte** | Sehr gut | Gut (mit WAL) | Mässig bis gering | Exzellent |
| **Native Min/Max/Avg Berechnung** | Ja (vollautomatisch) | SQL-Abfragen / Trigger | Ja (Downsampling) | Ja |
| **Flexibilität bei neuen Sensoren**| Eingeschränkt | Sehr hoch | Hoch | Hoch |
| **Komplexität der Einrichtung** | Gering | Gering | Mittel bis hoch | Gering bis mittel |

---

## 5. TCP-Schnittstelle für Live-Abfragen

Um Sensordaten unabhängig von der Weboberfläche abzufragen, stellt der Daemon einen schlanken TCP-Server (Standardport z. B. `4001`) zur Verfügung.

### Unterstützte Protokoll-Varianten

1. **JSON-over-TCP (Standard):**
   Client verbindet sich und sendet `GET` oder erhält direkt nach dem Connect:
   ```json
   {
     "timestamp": "2026-10-11T12:05:00Z",
     "temperature_c": 19.45,
     "humidity_pct": 58.2,
     "pressure_hpa": 1013.25,
     "pressure_qnh_hpa": 1024.10,
     "dew_point_c": 11.02
   }
   ```
2. **Kompaktes Text-Protokoll (CLI/Telnet/Mikrocontroller):**
   ```text
   TEMP:19.45;HUM:58.2;PRESS:1013.25;QNH:1024.10
   ```
3. **APRS-Wetter-Telemetrie-Format (Optionaler Modus):**
   Gemäss APRS-Spezifikation für Wettermeldungen:
   `c...s...g...t067r...p...h58b10132`

---

## 6. Datenabruf & Aggregationslogik

Der Webserver stellt REST-Endpunkte für die Visualisierung bereit:

* `GET /api/current`: Liefert den aktuellsten Messwert (aus dem RAM-Puffer).
* `GET /api/history?period=24h`: 
  - Datenpunkte im 5- oder 15-Minuten-Intervall für das Liniendiagramm.
  - Statistischer Block: `{ min: {...}, max: {...}, avg: {...} }`.
* `GET /api/history?period=7d`:
  - Datenpunkte aggregiert auf 30-Minuten-Schritte.
  - Wochen-Statistik (Min, Max, Durchschnitt für Temp, Feuchte, Druck).
* `GET /api/history?period=30d`:
  - Datenpunkte aggregiert auf 2-Stunden- oder Tages-Schritte.
  - Monats-Statistik (Min, Max, Durchschnitt).

---

## 7. Präsentationsschicht (Webserver & Dashboard)

### 7.1 Backend (Webserver & API)
* **Technologie-Optionen:**
  * **Option A: Node.js / TypeScript (Passend zu bestehenden Projektkonventionen in `gemini.md`)**
    - Leichtgewichtiger Fastify- oder Express-Server.
    - Vollständig typisiert (`ITemperatureReading`, `IWeatherStats`).
    - Exzellente asynchrone I/O-Leistung bei minimalem RAM-Bedarf.
  * **Option B: Python (FastAPI oder Flask)**
    - Sehr nahe an den Standard-GPIO/BME280-Treibern der Raspberry-Pi-Community.
* **Architektur:** Der Webdienst liest Ist-Daten aus `/dev/shm` und historische Daten aus der RRD-/SQLite-Datenbank.

### 7.2 Frontend (Web-Dashboard)
Das UI wird als responsives Single-Page-Interface (mobile-first) gestaltet, ohne schwere Frontend-Frameworks wie Angular oder React, um den Browser auf Mobilgeräten schnell zu laden:
* **Ist-Daten (Aktueller Zustand):**
  - Text-Darstellung mit Trend-Pfeilen (z. B. steigender/fallender Luftdruck über die letzten 3 Stunden).
  - **Gauge-Anzeigen (Messuhren):** Realisiert über SVG/HTML5 Canvas (z. B. mit `Canvas-Gauges` oder leichtem Vanilla-SVG).
    - Tacho 1: Temperatur (-10 °C bis +45 °C) mit Farbverlauf.
    - Tacho 2: Luftfeuchtigkeit (0 % bis 100 %).
    - Tacho 3: Barometer (960 hPa bis 1060 hPa) mit Wettertendenzen (Sturm, Regen, Veränderlich, Schön, Trocken).
* **Historische Daten:**
  - **Liniendiagramme:** Eingebunden über `Chart.js` oder `uPlot` (extrem schnell und ressourcensparend).
  - Umschaltbar zwischen 24 Stunden, 7 Tage und 30 Tage.
  - Getrennte oder kombinierte Achsen für Temperatur, Feuchtigkeit und Druck.
  - Einblendung von Min-, Max- und Durchschnittslinien bzw. Statistik-Karten.

---

## 8. Mögliche Erweiterungen mit weiteren Sensoren

Die Station kann stufenweise erweitert werden:

### 8.1 Meteorologische Sensoren
1. **Windgeschwindigkeit & Windrichtung:**
   - Schalenstern-Anemometer (Reed-Kontakt via GPIO-Interrupt für Pulse).
   - Windfahne (meist analog über Spannungsteiler -> benötigt SPI-ADC wie MCP3008 oder I2C ADS1115).
2. **Niederschlagsmesser (Pluviometer):**
   - Kippwaagen-Regenmesser (Tipping Bucket, z. B. 0.2794 mm pro Kipp-Impuls via GPIO-Flankenerkennung).
3. **Solar- & UV-Strahlung:**
   - BH1750 (I2C) für Umgebungshelligkeit (Lux).
   - VEML6075 oder LTR390 (I2C) für UV-Index.
4. **Zusätzliche Temperaturfühler:**
   - DS18B20 (wasserdichte 1-Wire-Sensoren) für Bodentemperatur oder Wassertemperatur.

### 8.2 Luftgüte- & Umgebungssensoren
1. **Feinstaub:** Sensirion SPS30 oder Plantower PMS5003 (UART / I2C) für PM1.0, PM2.5, PM10.
2. **CO2-Konzentration:** Sensirion SCD30 oder SCD40 (NDIR bzw. photoakustisch, I2C).
3. **VOC / Luftqualität:** BME680 / BME688 (Upgrade des BME280 mit Gassensor für Luftqualitätsindex IAQ).

### 8.3 Hardware-Erweiterbarkeit
* **I2C-Bus-Multiplexer (TCA9548A):** Ermöglicht den Betrieb mehrerer Sensoren mit identischer I2C-Adresse am selben Bus.

---

## 9. Weitere Möglichkeiten & Systemfeatures

1. **LoRa / APRS Integration (Bezug zu `gemini.md`):**
   - Aussenden periodischer Wetter-Baken (WX Reports) über LoRa APRS auf 433 MHz / 868 MHz.
   - Anbindung an das weltweite APRS-IS-Netzwerk.
2. **MQTT-Schnittstelle:**
   - Veröffentlichen der Messwerte an einen MQTT-Broker (z. B. Mosquitto) zur nahtlosen Integration in **Home Assistant**, **Node-RED** oder **openHAB**.
3. **Alarmierung & Grenzwerte:**
   - Benachrichtigungen (Telegram-Bot, E-Mail, Gotify) bei:
     - Frostgefahr (Temp < 0 °C)
     - Schnellem Luftdruckabfall (> 2 hPa in 3 Stunden = Sturmwarnung)
     - Sensor-Ausfall (Watchdog-Alert).
4. **Stromausfall- & Systemüberwachung:**
   - Überwachung von CPU-Temperatur, Speichernutzung und Throttling-Zustand des Raspberry Pi 4.
   - USV-Status (sofern USV-HAT vorhanden).

---

## 10. Gewählte Realisierungsarchitektur

Basierend auf den Anforderungen und Präferenzen wurde folgende Architektur festgelegt:

* **Programmiersprache / Runtime:** **Python 3**
  - Schlanker Hardwarezugriff (`smbus2` / BME280-Treiber)
  - Hohe Stabilität und native RRDtool-Unterstützung (`rrdtool`-Python-Bindings)
* **Speichermodell:** **Hybrid (RAM-Puffer + RRDtool)**
  - Aktuelle Werte werden im Shared Memory (`/dev/shm/wx_current.json`) gepuffert -> 0 I/O-Belastung auf der SD-Karte für Live-Abfragen.
  - Alle 5 Minuten erfolgt ein Flush in die RRD-Datenbank (`wx_station.rrd`).
  - RRDtool übernimmt automatisch die Konsolidierung (MIN, MAX, AVERAGE) für 24h, 7 Tage und 30 Tage bei absolut konstanter Dateigrösse.
* **TCP-Schnittstelle:** **Kompakter Plaintext-Stream / Socket**
  - Format: `TEMP:19.45;HUM:58.20;PRESS:1013.25;QNH:1024.10;DEW:11.02\n`
  - Direkter Abruf aus dem RAM-Puffer für minimale Latenz.
* **Webdienst & Visualisierung:**
  - Schlanker Webserver (z. B. FastAPI oder Flask).
  - REST-Endpunkte für Ist-Werte und historische Daten (generiert über `rrdtool.fetch`).
  - Frontend: Responsive Dashboard mit Text- & Canvas/SVG-Gauges für Ist-Daten sowie Chart.js / uPlot für 24h-, 7d- und 30d-Liniendiagramme (inkl. Min/Avg/Max).

---

## 11. Phasen- & Implementierungsplan

### Phase 1: Kernsystem BME280 (Aktueller Fokus)
1. **Hardware-Setup & I2C-Verifikation:**
   - I2C-Aktivierung auf dem Raspberry Pi 4 (`i2cdetect -y 1`).
   - Auslese-Skript mit Kalibrierungsdaten, Medianfilterung und Taupunkt/QNH-Berechnung.
2. **RRD-Datenbank-Initialisierung:**
   - Erstellung des RRD-Schemas mit 5-Minuten-Step und Archiven für 24h, 7d und 30d (MIN, AVERAGE, MAX).
3. **WX-Collector Daemon (systemd):**
   - 5-Minuten-Sampling und RRD-Update.
   - Schreiben der Live-Werte nach `/dev/shm/wx_current.json`.
   - Asynchroner TCP-Socket-Server auf konfigurierbarem Port (z. B. 4001) für Plaintext-Abfragen.
4. **WX-Webserver & Dashboard (systemd):**
   - API für Live- und RRD-Export.
   - Webinterface mit Gauges (Temperatur, Feuchte, Luftdruck) und interaktiven Liniendiagrammen (24h / 7d / 30d).

### Phase 2: Erweiterungen (Roadmap)
1. **LoRa-APRS Integration:**
   - Modul zur Formatierung von APRS-Wetter-Telemetriebaken und Anbindung an ein LoRa-Modem (z. B. SX1276/SX1278).
2. **Zusatzsensoren:**
   - Wind- und Regenmesser via GPIO-Flankenzähler.
   - Analoge Sensoren (z. B. Windfahne) via SPI ADC (MCP3008) oder I2C ADC (ADS1115).
   - Zusätzliche Temperaturfühler via 1-Wire (DS18B20).
3. **MQTT-Export:**
   - Optionales Publizieren der Daten an einen Heimautomations-Broker.
