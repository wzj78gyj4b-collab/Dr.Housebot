# Dr.Housebot

Deutschsprachiger Telegram-Gruppenbot mit Moderationsgrundfunktionen, Gruppenverknüpfung, Aktivitätspunkten, Regeln, Werkzeugen und KI-Fallback zwischen Gemini und Ollama.

## Status

Dies ist eine neue, isolierte Projektbasis für Tests. Noch nicht auf fps.ms deployen, bevor die Telegram-Berechtigungen, Moderationsabläufe und KI-Anbieter mit einer Testgruppe geprüft wurden. Der alte Housebot wird nicht verändert.

## Lokal starten

1. Python 3.11+ installieren.
2. Abhängigkeiten: `pip install -r requirements.txt`
3. `.env.example` nach `.env` kopieren und `TELEGRAM_BOT_TOKEN`, `ADMIN_IDS` und `ADMIN_ROOM_ID` setzen.
4. `python main.py`

Geheimnisse gehören ausschließlich in Umgebungsvariablen bzw. die Secret-Verwaltung des Hosters. **Nie** echte Tokens, API-Schlüssel, `.env` oder Datenbankdateien committen.

## Befehle

- `/start`, `/help`, `/menu`
- In einer Zielgruppe: `/connect` (durch Gruppenadmin), `/settings`, `/setrules TEXT`, `/rules`, `/rank`
- `/stil neutral|trocken|freundlich`, `/ai FRAGE`
- `/wetter STADT`, `/zitat`, `/nasa`
- Im konfigurierten Adminraum, nur für `ADMIN_IDS`: `/send TEXT`, `/warn CHAT_ID USER_ID GRUND`, `/mute CHAT_ID USER_ID MINUTEN [GRUND]`, `/unmute CHAT_ID USER_ID`, `/kick CHAT_ID USER_ID`, `/ban CHAT_ID USER_ID [GRUND]`, `/unban CHAT_ID USER_ID`, `/logs`

Der Bot muss in Zielgruppen die passenden Adminrechte haben, um Nachrichten zu löschen, Mitglieder einzuschränken oder zu bannen. Gruppen müssen einmal durch einen Gruppenadmin mit `/connect` registriert werden. Admin-Befehle wirken ausschließlich auf registrierte Gruppen.

## KI-Fallback

`AI_PROVIDER=gemini` bevorzugt Gemini und wechselt bei Fehlern zu Ollama. `AI_PROVIDER=ollama` bevorzugt Ollama und wechselt bei Fehlern zu Gemini. Beide Anbieter benötigen ihre jeweilige Konfiguration. Sind beide nicht erreichbar, bleiben Nicht-KI-Funktionen aktiv.

Ollama auf demselben Hosting-System nur verwenden, wenn genügend RAM/CPU verfügbar sind; sonst einen separat betriebenen, abgesicherten Ollama-Endpunkt konfigurieren.

## Aktuelle Grenzen

Dies ist ein funktionsfähiger Ausgangspunkt, kein vollständig ausgehärteter Produktionsrelease. Captcha, Wortfilter, automatische Willkommensnachrichten für alle Telegram-Join-Events, erweiterte Freigabe-Workflows und ein vollständiges Audit-/Rechtemodell sind noch nicht enthalten. Nur tatsächlich implementierte Schalter werden angezeigt. Vor Produktion Tests mit einer privaten Gruppe durchführen.
