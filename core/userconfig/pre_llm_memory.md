<!--
Pre-LLM Memory (Query-Rewriter)
================================

Wird VOR der RAG-Suche an den Rewriter-Prompt angehaengt. Hier kommen
Hinweise rein, die dem Rewriter helfen, Tippfehler / STT-Fehler /
Pronomen besser aufzuloesen — BEVOR die Embedding-Suche laeuft.

Format: freier Markdown-Text. Datei darf leer sein (dann wird nichts
angehaengt). HTML-Kommentare wie dieser werden komplett ignoriert.

Eigene Hinweise daher AUSSERHALB der Kommentar-Tags schreiben.
Updates des Add-ons ueberschreiben deine Anpassungen NICHT.
-->

<!--
Beispiel-Setup zum Inspirieren (Kommentar-Tags um die passenden Bloecke
entfernen, oder Inhalt komplett anpassen):

## Personen / Raeume
- "Paul", "Paolo", "Pawl" -> "Paul" (Bewohner mit eigenem Zimmer)

## Haeufige STT-Fehler bei Geraeten
- "Rolladen", "Rollade", "Roland" wenn Geraetebezug -> "Rolladen"
- "Jalousie", "Schalousie" -> "Jalousie"
- "Wallbox", "Wollbox" -> "Wallbox"
- "Photovoltaik", "Fotovoltaik" -> "Photovoltaik"
- "Wechselrichter", "Wechselrichtet" -> "Wechselrichter"
- "Vorlauftemperatur", "Vorlauf-Temperatur" -> "Vorlauftemperatur"
- "Fussbodenheizung", "Fussboeden" -> "Fussbodenheizung"
- "Waermepumpe", "Wermepumpe", "Waermepump" -> "Waermepumpe"

## Setup-Begriffe
- "Pool", "Pull", "Poul" -> "Pool"
- "Pool-Pumpe", "Bullpumpe" -> "Pool-Pumpe"

## Allgemein
- Wiederholungen im Transcript ("Mach das Licht an. Mach das Licht an.")
  -> nur einmal verwenden, Duplikate ignorieren
-->
