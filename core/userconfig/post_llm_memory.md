<!--
Post-LLM Memory (Parser)
========================

Wird an ALLE Parser-Prompts angehaengt:
- primary_parser (Legacy-Pfad ohne RAG)
- rag_parser    (RAG-Pfad)
- fallback_rest (Live-Liste aus HA als REST-Fallback)

Damit funktionieren diese Hinweise unabhaengig davon, ob RAG aktiv ist
oder welcher Pfad gerade greift.

Format: freier Markdown-Text. Datei darf leer sein (dann wird nichts
angehaengt). HTML-Kommentare wie dieser werden komplett ignoriert.

Eigene Hinweise daher AUSSERHALB der Kommentar-Tags schreiben.
Updates des Add-ons ueberschreiben deine Anpassungen NICHT.
-->

<!--
Beispiel-Inhalt zum Kopieren (ausserhalb der Kommentar-Tags einfuegen,
oder ganz nach eigenem Setup ersetzen):

## Setup-spezifische Begriffe
- "Pumpe" ohne Kontext -> immer Pool-Pumpe
- "Rollo Paul" -> Rollo IM Zimmer Paul, nicht eine Person Paul
- "alles aus" -> NUR Gruppen-Entities verwenden, nicht jede Entity einzeln

## Stockwerke / Bereiche
- "OG" / "oben" / "Obergeschoss" -> alle Entities mit Area="OG"
- "EG" / "unten" / "Erdgeschoss" -> alle Entities mit Area="EG"

## Bevorzugungen
- Helligkeit ohne konkreten Wert -> brightness_pct: 50
- "ein bisschen waermer" -> +1 Grad relativ zum aktuellen Wert
- "deutlich waermer" -> +3 Grad relativ zum aktuellen Wert

## Verbotene Aktionen
- "automation.urlaub" niemals ohne Rueckfrage triggern
-->
