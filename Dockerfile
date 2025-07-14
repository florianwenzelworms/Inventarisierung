# Verwenden Sie ein offizielles, schlankes Python-Image als Basis
FROM python:3.9-slim

# Setzen Sie das Arbeitsverzeichnis im Container
WORKDIR /app

# Kopieren Sie zuerst die Datei mit den Abhängigkeiten, um den Docker-Build-Cache zu optimieren
COPY requirements.txt .

# Installieren Sie die Python-Bibliotheken
RUN pip install --no-cache-dir -r requirements.txt

# Kopieren Sie den gesamten restlichen Anwendungscode in das Arbeitsverzeichnis
COPY . .

# Setzen Sie eine Umgebungsvariable, um Python anzuweisen, Ausgaben direkt zu schreiben
ENV PYTHONUNBUFFERED 1

# Machen Sie den Port, auf dem die App laufen wird, für Docker sichtbar
EXPOSE 5000

# Der Befehl, um die Anwendung mit einem produktionsreifen Server (Gunicorn) zu starten
# -w 4 startet 4 "Worker"-Prozesse
# -b 0.0.0.0:5000 bindet den Server an alle Netzwerkschnittstellen auf Port 5000
# app:app bedeutet: in der Datei app.py, finde die Flask-Instanz namens app
CMD ["gunicorn", "-w", "4", "-b", "0.0.0.0:5000", "app:app"]
