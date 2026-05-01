<!--
Pre-LLM Memory (Query-Rewriter)
================================

Wird VOR der RAG-Suche an den Rewriter-Prompt angehaengt.
Hier kommen Hinweise rein, die dem Rewriter helfen, Tippfehler / STT-Fehler /
Pronomen besser aufzuloesen — BEVOR die Embedding-Suche laeuft.

WICHTIG: Alles, was zwischen den HTML-Kommentar-Tags steht, wird IGNORIERT
(damit ein unveraendertes Template-File leer wirkt). Echte Hinweise daher
AUSSERHALB der Kommentar-Tags schreiben — siehe Beispiele unten.

Format: freier Markdown-Text. Datei darf leer sein (dann wird nichts angehaengt).
-->

## Personen / Raeume

- "Paul", "Paolo", "Paule", "Pawl" -> immer "Paul" (Bewohner, hat eigenes Zimmer im Obergeschoss)

## Haeufige STT-Fehler bei Geraeten

- "Rolladen", "Rolllade", "Rollade", "Roland" wenn Geraetebezug -> "Rolladen"
- "Jalousie", "Schalousie" -> "Jalousie"
- "Wallbox", "Wallbocks", "Wollbox" -> "Wallbox"
- "Photovoltaik", "Fotovoltaik", "Fotvoltaik" -> "Photovoltaik"
- "Wechselrichter", "Wechselrichtet" -> "Wechselrichter"
- "Vorlauftemperatur", "Vorlauf-Temperatur" -> "Vorlauftemperatur"
- "Fussboden", "Fussbodenheizung", "Fussboeden" -> "Fussbodenheizung"
- "Waermepumpe", "Wermepumpe", "Waermepump" -> "Waermepumpe"

## Pool

- "Pool", "Pull", "Poul" -> "Pool"
- "Pool-Pumpe", "Poolpumpe", "Bullpumpe" -> "Pool-Pumpe"

## Allgemein

- Wiederholungen im Transcript (z.B. "Mach das Licht an. Mach das Licht an.") -> nur einmal verwenden, Duplikate ignorieren
