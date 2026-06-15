# Timelapse

Täglicher Screenshot von einer Reolink-Kamera, gespeichert auf einem QNAP NAS via NFS.

## Voraussetzungen

- Python 3.8+
- NFS-Share bereits gemountet (z.B. unter `/mnt/qnap/timelapse`)
- Reolink-Kamera im lokalen Netzwerk erreichbar

## Installation

```bash
pip install -r requirements.txt
cp config.example.ini config.ini
# config.ini anpassen (Kamera-IP, Zugangsdaten, NAS-Pfad)
```

## Einmaliger Test

```bash
python snapshot.py
```

## Automatisch jeden Morgen (Cron)

```bash
crontab -e
```

Zeile einfügen (täglich um 07:00 Uhr):

```
0 7 * * * cd /pfad/zum/repo && python snapshot.py >> /var/log/reolink_snapshot.log 2>&1
```

## Dateistruktur auf dem NAS

```
/mnt/qnap/timelapse/
└── 2026-06-15/
    └── snapshot_2026-06-15_07-00-03.jpg
```
