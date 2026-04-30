<!--
Post-LLM Memory (Parser)
========================

Wird an ALLE Parser-Prompts angehaengt:
- primary_parser (Legacy-Pfad ohne RAG)
- rag_parser    (RAG-Pfad)
- fallback_rest (Live-Liste aus HA als REST-Fallback)

Damit funktionieren diese Hinweise unabhaengig davon, ob RAG aktiv ist oder
welcher Pfad gerade greift.

WICHTIG: Alles, was zwischen den HTML-Kommentar-Tags steht, wird IGNORIERT
(damit ein unveraendertes Template-File leer wirkt). Echte Hinweise daher
AUSSERHALB der Kommentar-Tags schreiben — siehe Beispiele unten.

Format: freier Markdown-Text. Datei darf leer sein (dann wird nichts angehaengt).

Beispiel-Inhalt zum Kopieren (ausserhalb der Kommentar-Tags einfuegen):

## Haeufige Fehler / Korrekturen
- "Rollo Paul" meint die Rollo IM Zimmer Paul, nicht eine Person Paul
- Wenn Nutzer "alles aus" sagt, NUR Gruppen-Entities verwenden
- "Pumpe" ohne weiteren Kontext bezieht sich immer auf die Pool-Pumpe

## Bevorzugungen
- Wenn Nutzer nach Helligkeit fragt ohne Wert, default auf brightness_pct: 50
- Bei "ein bisschen waermer" -> +1 Grad relativ zum aktuellen Wert

## Niemals tun
- Niemals "automation.urlaub" ausloesen, immer rueckfragen
-->
