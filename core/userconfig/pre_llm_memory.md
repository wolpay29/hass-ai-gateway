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

Beispiel-Inhalt zum Kopieren (ausserhalb der Kommentar-Tags einfuegen):

## Haeufige STT- / Tippfehler
- "lciht", "leicht", "luicht" -> immer als "licht" interpretieren
- "wonzimer" -> "wohnzimmer"
- "paula", "pauli" wenn Geraetebezug -> "paul" (Personenname)

## Mehrdeutige Begriffe
- "oben" alleine ist mehrdeutig (Obergeschoss vs. Rollo hochfahren) - Original lassen
-->
