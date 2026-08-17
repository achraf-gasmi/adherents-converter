# Changelog

Toutes les modifications notables de ce projet sont documentées dans ce
fichier. Format inspiré de [Keep a Changelog](https://keepachangelog.com/fr/1.1.0/).

## [Unreleased]

### Fixed

- **Traçabilité "Ligne source" faussée par toute ligne vide dans le fichier
  source.** Les lignes entièrement vides étaient retirées avant d'être
  numérotées, décalant le numéro de ligne rapporté pour toutes les lignes
  suivantes dans le rapport d'anomalies — rendant impossible de retrouver la
  bonne cellule en ouvrant le fichier source. Le lecteur de lignes
  (`core.detection.lire_lignes_donnees`) conserve désormais les lignes vides
  intermédiaires (seules celles en toute fin de feuille sont retirées), et
  centralise une logique auparavant dupliquée entre `app.py` et les tests.
