# Audio-Aufnahmen fuer die End-to-End-Test-Pipeline

Hier ist die vollstaendige Liste der WAV-Dateien, die in `tests/e2e/fixtures/audio/`
liegen muessen. Jede Zeile entspricht einem Testfall in [cases.yaml](../cases.yaml).

## Aufnahme-Anleitung

- **Format**: 16-bit PCM, 16 kHz, Mono, **WAV**.
- **Quelle**: am einfachsten mit dem RPi-Mikro oder einem Headset am PC. Audacity exportieren als "WAV (Microsoft) - signed 16-bit PCM, 16 kHz mono".
- **Stille schneiden**: vorne / hinten max. 0.3 s Stille.
- **Sprecher**: deine eigene Stimme - das System soll mit deiner Aussprache trainiert sein.
- **Akzent / Tippfehler erlaubt**: bewusst nicht kuenstlich klar sprechen, sonst sind die Tests unrealistisch.
- **Dialekt-Kollisionen pruefen**: bei den `seq_*`-Aufnahmen die Stimmlage gleich halten wie in den Vor-Aufnahmen, damit Whisper sie als selber Sprecher behandelt.

Wenn etwas im Whisper-Schritt verlorengeht, im Report unter "Transcript" ablesen
und ggf. eine deutlichere Aufnahme einsprechen - oder das `whisper_vocabulary.md`
unter `tests/e2e/fixtures/` erweitern.

## Aufnahmeliste

### Single-Cases - Statusabfragen

| Datei | Gesprochen (Vorschlag) | Erwartung |
|---|---|---|
| `status_pv.wav`              | "Wie viel Strom erzeugt die PV gerade?"          | Statusantwort mit Wattzahl, kein Schalten |
| `status_aussentemp.wav`      | "Wie warm ist es draussen?"                      | Statusantwort in Grad Celsius |
| `status_battery.wav`         | "Wie voll ist die Batterie?"                     | Statusantwort mit Prozent |
| `status_pool_climate.wav`    | "Was macht die Pool-Heizung gerade?"             | Statusantwort zur Pool-Waermepumpe |
| `status_abstellkammer.wav`   | "Ist die Tuer der Abstellkammer offen oder zu?"  | Antwort mit "offen" / "zu" / "geschlossen" |

### Single-Cases - Direkte Aktionen

| Datei | Gesprochen (Vorschlag) | Erwartung |
|---|---|---|
| `action_licht_paul_an.wav`   | "Mach das Licht bei Paul an."                    | `light.licht_paul` -> `turn_on` |
| `action_licht_max_aus.wav`   | "Schalte das Licht im Zimmer von Max aus."       | `light.licht_max` -> `turn_off` |
| `action_tor_auto.wav`        | "Mach das Garagentor auf."                       | `automation.trigger_tor_auto` -> `trigger` |
| `action_pool_pump_on.wav`    | "Schalte die Pool-Pumpe ein."                    | `automation.trigger_pool_pump_on` -> `trigger` |
| `action_rollo_paul_zu.wav`   | "Mach den Rollo bei Paul runter."                | `switch.rollo_paul_ab` -> `turn_on` |

### Single-Cases - Multi-Action

| Datei | Gesprochen (Vorschlag) | Erwartung |
|---|---|---|
| `action_paul_und_max_an.wav` | "Mach das Licht bei Paul und Max an."             | 2 Aktionen: paul + max turn_on |
| `action_alle_lichter_og_aus.wav` | "Schalte alle Lichter im Obergeschoss aus." | 1 Aktion: `light.licht_og_aus` (Gruppen-Entity) |

### Single-Cases - Mehrdeutigkeit / Plural

| Datei | Gesprochen (Vorschlag) | Erwartung |
|---|---|---|
| `ambiguous_licht.wav`        | "Mach das Licht an."                             | Rueckfrage, keine Aktion |
| `plural_lichter_aus.wav`     | "Mach die Lichter aus."                          | Rueckfrage, keine Aktion |

### Single-Cases - Smalltalk

| Datei | Gesprochen (Vorschlag) | Erwartung |
|---|---|---|
| `smalltalk_hallo.wav`        | "Hallo, wie geht's?"                             | Smalltalk-Reply, keine Aktion |

### Single-Cases - Entities NICHT in entities.yaml

Hier triggerst du gezielt Faelle, in denen die test-`entities.yaml` die gefragte
Entity nicht enthaelt. RAG-on findet sie ueber den Index. RAG-off muss in den
Fallback (Mode 1 / Mode 2) gehen oder mit `needs_fallback_no_mode` scheitern.

Voraussetzung: in deinem echten HA existieren passende Entities mit den
genannten Begriffen. Falls bei dir die genauen Begriffe anders heissen,
nimm Synonyme die in deinem HA-Index zu finden sind.

| Datei | Gesprochen (Vorschlag) | Erwartung |
|---|---|---|
| `out_of_yaml_humidity.wav`   | "Wie hoch ist die Luftfeuchtigkeit im Bad?"      | RAG-on: Statusantwort. RAG-off+fb0: `needs_fallback_no_mode`. fb1/fb2: Antwort kommt aus Fallback. |
| `out_of_yaml_dimmer.wav`     | "Stell den Dimmer im Wohnzimmer auf 30 Prozent." | Wie oben - mit `service_data: brightness_pct` |
| `out_of_yaml_wallbox.wav`    | "Ist die Wallbox aktiv?"                         | Wie oben - existiert in HA, fehlt in test-yaml |

### Single-Cases - Bedingte Aktion

| Datei | Gesprochen (Vorschlag) | Erwartung |
|---|---|---|
| `conditional_pv_pool.wav`    | "Wenn die PV mehr als 1000 Watt erzeugt, schalte die Pool-Pumpe ein." | LLM entscheidet aufgrund des Live-Werts |

### Single-Cases - Stop-Befehl

| Datei | Gesprochen (Vorschlag) | Erwartung |
|---|---|---|
| `stop_command.wav`           | "Vergiss es."                                    | Smalltalk-Reply, keine Aktion |

### Sequence-Cases - History / Pronomen / Folge-Befehle

Sequenzen nutzen einige Audio-Dateien aus den Single-Cases (gleicher Inhalt,
gleiche Datei). Zusaetzliche Dateien:

| Datei | Gesprochen (Vorschlag) | Verwendet in |
|---|---|---|
| `seq_und_wieder_aus.wav`     | "Und wieder aus."                                | `pronoun_followup` |
| `seq_paul.wav`               | "Paul."                                          | `clarification_round` (Antwort auf "Welches Licht?") |
| `seq_pool_warm_wenn_kalt.wav`| "Mach den Pool warm wenn es draussen unter 20 Grad ist." | `status_then_conditional` |

## Schnellstart

1. Diese Datei oeffnen, alle Audio-Dateien einsprechen, in `tests/e2e/fixtures/audio/`
   ablegen.
2. `cp tests/e2e/.env.local.example tests/e2e/.env.local` und ausfuellen.
3. `python -m tests.e2e.runner --only "rag-on-prellm-on-fb0" --case status_pv` als
   ersten Smoke-Test - laueft eine einzige Variante x ein einziger Case (~10 Sekunden).
4. Wenn der Smoke-Test sauber ist: `python -m tests.e2e.runner --open` fuer den
   vollen Lauf (~10-15 Minuten je nach Modell-Geschwindigkeit).

## Cases erweitern

Neuer Case: einfach `cases.yaml` aufmachen, neuen Eintrag unter `single_cases:`
oder als Step in einem `sequence_cases:`-Eintrag anhaengen. Audio-Datei dazu
unter `fixtures/audio/<id>.wav` ablegen, fertig.

Settings-Variante hinzufuegen: `matrix.yaml` aufmachen, einen neuen Eintrag
unter `runs:` anhaengen. Beim naechsten Lauf wird die Variante automatisch
mitgespielt.
