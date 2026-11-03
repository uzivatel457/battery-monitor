# Changelog — Battery monitor by u457

## 1.1.0 — 2026-11-03

- Jazyk okna, instalátoru a hlášek se bere z jazyka Windows (čeština, slovenština, angličtina, němčina, polština, francouzština, španělština). Ostatní jazyky použijí angličtinu.
- Po startu se zkontroluje nové vydání na GitHubu. Lze aktualizovat, odložit, nebo danou verzi přeskočit.
- Veřejný název aplikace je **Battery monitor by u457**.

## 1.0.0 — 2026-09-22

- Přejmenování aplikace na **BatteryMonitor** (verze v titulku okna).
- Živé sledování nabití, napětí, proudu, výkonu, CPU a GPU.
- Trvalý CSV záznam do `logs/` (flush / fsync, název souboru s časem).
- Načítání logů s grafy přes celý rozsah a průměrováním bodů.
- Analýza načteného měření: doba vybíjení/nabíjení, spotřebovaná kapacita (% i mWh), počet chyb baterie a detaily anomálií.
- Přenositelná instalace (`install.bat` / `run.bat` / `BatteryMonitor.vbs`).
- Balíček ZIP do složky `_install` (`BatteryMonitor1.0.0.zip`).
