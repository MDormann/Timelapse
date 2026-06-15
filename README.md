# Timelapse

Daily screenshot from a Reolink camera, saved to a QNAP NAS via NFS.

## Requirements

- Python 3.8+
- NFS share already mounted (e.g. at `/mnt/qnap/timelapse`)
- Reolink camera reachable on the local network

## Setup

```bash
pip install -r requirements.txt
cp config.example.ini config.ini
# Edit config.ini: camera IP, credentials, NAS path
```

## Manual test

```bash
python snapshot.py
```

## Scheduled daily run (Cron)

```bash
crontab -e
```

Add this line (runs every day at 07:00):

```
0 7 * * * cd /path/to/repo && python snapshot.py >> /var/log/reolink_snapshot.log 2>&1
```

### With Docker (recommended)

The image is built automatically on every push to `main` and published at
`ghcr.io/mdormann/timelapse:latest`.

```bash
# One-off test
docker run --rm \
  -v /path/to/config.ini:/app/config.ini:ro \
  -v /mnt/qnap/timelapse:/mnt/qnap/timelapse \
  ghcr.io/mdormann/timelapse:latest
```

Cron with Docker (daily at 07:00):

```
0 7 * * * docker run --rm -v /path/to/config.ini:/app/config.ini:ro -v /mnt/qnap/timelapse:/mnt/qnap/timelapse ghcr.io/mdormann/timelapse:latest >> /var/log/reolink_snapshot.log 2>&1
```

## File structure on the NAS

```
/mnt/qnap/timelapse/
└── 2026-06-15/
    └── snapshot_2026-06-15_07-00-03.jpg
```
