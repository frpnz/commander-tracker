## Avvio automatico con systemd
### Crea il servicesudo vim /etc/systemd/system/commander-tracker.service

[Unit]
Description=Commander Tracker (FastAPI)
After=network.target

[Service]
User=tracker
WorkingDirectory=/home/user/commander-tracker
ExecStart=/home/user/commander-tracker/.venv/bin/python -m uvicorn app:app --host 127.0.0.1 --port 8000
Restart=always
RestartSec=2
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target

### Stato del servizio
sudo systemctl status commander-tracker

### Avvio
sudo systemctl start commander-tracker

### Arrest
sudo systemctl stop commander-tracker

### Riavvio
sudo systemctl restart commander-tracker

### Reload (config changes)
sudo systemctl daemon-reload
sudo systemctl restart commander-tracker

### Real-time log
sudo journalctl -u commander-tracker -f

### Disinstall
sudo systemctl stop commander-tracker
sudo systemctl disable commander-tracker
sudo rm /etc/systemd/system/commander-tracker.service
sudo systemctl daemon-reload