# Konzept WX-Station

## Allgemeines
Ein BME280 ist an einem Raspberr PI Version 4 am GPIO angeschlossen.

Es soll ein Server für die Sensordaten (Temeratur, Feuchtigkeit und Luftdruck) entwickelt werden.
Der Server holt in einem Intervall von fünf Minuten die Sensordaten ab und speichert diese.

Ein weiterer Dienst bereitet die gespeicherten Daten auf und präsentiert diese auf über eine Webserver
den Benutzer. Neben den Ist-Daten sollen auch die kummulierten Daten (24h-Intervall, Wochenintervall und Monatsintervall) 
mit den Mittel-, Minimum- und Maximum-Daten angezeigt werden. 
Anzeige  der IST-Daten mit Text und einem Gauge-Anzeige, historische Daten mit einem Liniendiagramm.

Die aktuellen Sensordaten können auch über eine tcp-Verbindung abgefragt werden.

Speicherung der Sensor-Daten
Evaluiere verschieden Varianten für die Datenspeicherung. Die Speicherung soll effizient und ohne  grossen
Ressourcenverbrauch erfolgen. In einem ähnlichen Projekt habe ich eine RRD (Round-Robin Datenbank)  eingesetzt 


Erstelle ein Konzept
- Abfrage Sensordaten
- Mögliche Erweiterungen mit weiteren Sensoren
- Speicherung der Sensordaten, 
- Abruf Ist- und der Kumilierten Daten im gewünschten Intervall
- Präsentation der Daten
- Beschreibe weitere Möglichkeiten

- Erstelle ein neues Dokument mit den Realiserungsvarienten  

 
