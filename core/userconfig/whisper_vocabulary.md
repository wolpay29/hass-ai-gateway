<!--
Wortschatz-Hilfe fuer die Spracherkennung (Whisper / faster-whisper).

Der Inhalt dieser Datei wird als `initial_prompt` an das STT-Modell uebergeben.
Whisper bevorzugt dann diese Begriffe in der Transkription. Das verbessert die
Erkennung von deutschen Smart-Home-Begriffen, Raumnamen und Eigennamen, die
sonst gerne falsch transkribiert werden.

Tipps:
- Schreibe Begriffe so wie du sie aussprichst.
- Keine ganzen Phrasen, sondern Worte/Namen, die haeufig fehlerhaft erkannt werden.
- Eigennamen (Kinder, Raumnamen, Geraetebezeichnungen) hier eintragen.
- HTML-Kommentare wie dieser werden vor der Verwendung entfernt.
- Datei leeren -> kein initial_prompt (Whisper-Default-Verhalten).

Nach Aenderung: Service neu starten (oder Container neu starten), damit der
neue Wortschatz geladen wird.
-->

Wohnzimmer, Schlafzimmer, Kueche, Bad, Flur, Buero, Werkstatt, Gaestezimmer.
Erdgeschoss, Obergeschoss, Untergeschoss, Keller, Dachboden, Garten, Garage.
Rolladen, Rollade, Rollos, Jalousie, Markise, Tor, Garagentor, Haustuer.
Lampe, Licht, Deckenleuchte, Stehlampe, Steckdose, Schalter, Dimmer.
Heizung, Vorlauftemperatur, Ruecklauftemperatur, Therme, Waermepumpe, Fussbodenheizung.
Wallbox, Wechselrichter, Photovoltaik, Solar, Batterie, Stromzaehler, Hausanschluss.
Pool, Pool-Pumpe, Filter, Solarheizung, Aussentemperatur, Wassertemperatur.
Sensor, Akku, Luftfeuchtigkeit, Helligkeit, Bewegungsmelder, Luftqualitaet.
Automation, Szene, Skript, Routine.
