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
- **Version non détectée sur un fichier dont l'en-tête n'est pas en ligne 1.**
  Cas réel : ASSETS.xlsx / "Export Adherent + Beneficiaire" a une ligne 1
  entièrement vide avant l'en-tête réel (ligne 2), ce qui empêchait toute
  détection automatique du format (V0/V1) et obligeait à un forçage manuel.
  La détection recherche désormais la signature d'en-tête sur les 10
  premières lignes de chaque onglet (`core.detection._localiser_entete`) au
  lieu de se limiter à la ligne 1. Le numéro de ligne réel de l'en-tête
  (`OngletDetecte.ligne_entete`) est propagé à la lecture des données et au
  calcul de "Ligne source" (`convertir_v0`/`convertir_v1`) pour que la
  traçabilité reste exacte quel que soit le décalage.
