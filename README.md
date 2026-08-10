# Convertisseur de fichiers adhérents — BH Assurance

> ⚠️ **Ce dépôt ne contient aucune donnée.** Les fichiers Excel d'adhérents
> (noms, dates de naissance, CIN, RIB, photos) sont des données personnelles
> réelles d'assurés. Ils ne doivent **jamais** être commités ni poussés sur
> GitHub. Le dossier `data/samples/` est volontairement ignoré par Git
> (`.gitignore`) — placez-y vos propres fichiers en local pour tester
> l'application, ils resteront sur votre poste.

Application Python / Streamlit qui convertit les fichiers Excel des adhérents
des contrats groupe santé, reçus des entreprises clientes dans deux formats
historiques (V0 et V1), vers un format cible unique. Destinée à la Direction
Organisation et Qualité, utilisable sans connaissance technique.

Principe directeur : **auditabilité**. Toute valeur corrigée, complétée ou
rejetée par l'application apparaît dans un rapport d'anomalies avec sa
valeur d'origine. Aucune inférence silencieuse, aucune fusion automatique de
personnes.

## Installation

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt
```

## Lancement

```bash
streamlit run app.py
```

L'application s'ouvre dans le navigateur. Aucun accès réseau n'est requis :
tout le traitement se fait en mémoire, aucun fichier n'est écrit sur disque
ni transmis à un service externe.

## Utilisation

1. **Import** — déposez un ou plusieurs fichiers `.xlsx`. Chaque onglet est
   analysé et sa version (V0/V1) est détectée automatiquement à partir de la
   cellule A1. Un tableau récapitule fichier, onglet, version, nombre de
   lignes/familles, avec une case à cocher pour inclure ou exclure chaque
   onglet. Des bandeaux signalent les images encodées en base64 (jamais
   exportées), les fichiers sans colonne CIN, ou les onglets dont plus de
   30 % des adhérents sont sans CIN.
2. **Configuration** — activez ou désactivez les règles de normalisation
   (complétion des CIN à 7 chiffres, majuscules sur les noms, suppression
   des lignes fantômes, CIN factices, export consolidé).
3. **Conversion** — cliquez sur *Convertir*. Le pipeline calcule les rangs,
   applique les règles de normalisation, et affiche un aperçu des données,
   la liste filtrable des anomalies, et une synthèse par fichier.
4. **Export** — téléchargez chaque fichier converti individuellement, le
   fichier consolidé, le rapport global d'anomalies, ou une archive ZIP
   regroupant l'ensemble.

## Architecture

```
app.py                    Interface Streamlit (orchestration uniquement)
core/
  detection.py             Détection V0/V1 par signature d'en-tête
  mapping.py                Constantes : colonnes cible, alias, variantes
  convert_v0.py             Dépivotage V0 (large -> long)
  convert_v1.py              Remappage V1 (long -> cible)
  ranking.py                 Calcul des rangs, cohérence familiale, doublons
  normalize.py                Nettoyage des valeurs (noms, CIN, RIB, dates, genre)
  anomalies.py                 Registre des codes + collecteur de traçabilité
  export.py                     Écriture des classeurs xlsx du format cible
tests/                     Tests pytest (unitaires + intégration volumétrique)
data/samples/               Fichiers Excel sources de référence
```

## Règles de gestion (résumé)

- **Format cible** : 11 colonnes (Client, N° Famille ×2, Lien, Gendre, Nom,
  Date de naissance, Date d'affiliation, Rang, RIB, Identité gouvernementale).
  N° Famille, RIB et Identité gouvernementale sont écrits en texte pour
  préserver les zéros initiaux ; les dates au format `dd/mm/yyyy`.
- **Rang** : le comportement diffère selon le format source, sur demande
  explicite des utilisateurs métier après validation :
  - **V0** (le format ne porte pas de colonne Rang) : entièrement calculé —
    0 = adhérent, 1 = conjoint (toujours réservé), 2+ = enfants triés par
    date de naissance puis par nom puis par ordre d'apparition dans la
    source (départage déterministe des jumeaux).
  - **V1** : le rang fourni par la source **n'est plus corrigé** — il est
    repris tel quel dans l'export, y compris s'il est incohérent ou
    dupliqué. L'application se contente de détecter et de journaliser les
    anomalies (`RANG_INCOHERENT` : Lien et Rang ne correspondent pas ;
    `RANG_DUPLIQUE` : plusieurs lignes d'une même famille portent le même
    rang ; `RANG_ENFANTS_DESORDONNES` : l'ordre des rangs des enfants ne
    suit pas leur âge ; `RANG_MANQUANT` : rang absent ou illisible, laissé
    vide), sans jamais modifier la valeur exportée.
- **Genre** : si le genre est absent de la source (systématique en V0, ou
  ponctuel en V1), l'application le déduit automatiquement du prénom
  (dernier mot du nom nettoyé) à partir d'un dictionnaire de prénoms
  fréquents, et le renseigne dans la colonne Gendre. Toute valeur ainsi
  déduite est journalisée en `GENDRE_DEVINE` (sévérité information, avec le
  prénom utilisé pour la déduction) afin de rester auditable et vérifiable ;
  quand aucune déduction fiable n'est possible, `GENDRE_MANQUANT` est
  journalisé et le champ reste vide.
- **CIN** : nettoyage des espaces (y compris insécables) et astérisques,
  rejet des booléens et motifs factices, complétion à 8 chiffres si 7
  chiffres présents. Un CIN vide n'est signalé que sur la ligne d'adhérent
  (rang 0) — vide sur conjoint/enfant est normal (mineurs).
- **RIB** : 20 chiffres attendus, rang 0 uniquement, vidé si non conforme.
- **Doublons** : `DOUBLON_INTRA_FAMILLE` (même nom + même date de naissance
  dans une famille) et `DOUBLON_INTER_SOURCE` (même RIB sur deux N° Famille
  différents) sont signalés mais **jamais fusionnés automatiquement**.
- **Traçabilité** : chaque anomalie porte le fichier, l'onglet, le numéro de
  ligne source (tel qu'affiché par Excel), la colonne source concernée, la
  valeur d'origine (caractères invisibles rendus visibles, valeurs
  ambiguës explicitées : `[vide]`, `[False]`) et la valeur retenue.

Le registre complet des codes d'anomalie et leur sévérité (Erreur /
Avertissement / Information) est défini dans `core/anomalies.py`.

## Limites connues des données sources

**L1 — Champs absents du format V0.** RIB et Date d'affiliation n'existent
pas dans le format source V0 : les lignes issues de ce format (environ 72 %
du corpus total) sortiront avec ces deux colonnes vides. Une reprise
manuelle ou une demande de complément aux entreprises clientes est
nécessaire pour les fiabiliser. Le Genre, lui, est déduit automatiquement du
prénom quand c'est possible (voir plus haut) — les cas non déductibles
restent vides et journalisés en `GENDRE_MANQUANT`.

**L2 — Qualité des CIN.** Une part significative des CIN du corpus est non
conforme ou absente (complétés à 7 chiffres, invalides, ou factices). Les
cas comme des CIN factices séquentiels ou des booléens Excel non résolus
relèvent d'un problème à la source, pas d'un défaut de conversion.

**L3 — Rang source conservé tel quel pour le V1.** Sur demande des
utilisateurs métier, le rang fourni par la source V1 n'est plus corrigé :
famille sans adhérent, rangs dupliqués, rang réservé porté par la mauvaise
personne ou ordre des enfants incohérent avec leur âge se retrouvent tels
quels dans l'export, chacun journalisé avec le code correspondant. Une
reprise manuelle des cas signalés reste nécessaire côté métier. Le rang V0,
lui, continue d'être entièrement calculé (le format source ne le porte pas).

**L4 — Aucune fusion automatique.** Les doublons potentiels inter-fichiers
(même RIB sur deux N° Famille, par exemple en cas de migration de contrat)
sont signalés mais jamais fusionnés : la décision appartient au métier.

**L5 — Déduction du genre par prénom : une heuristique, pas une certitude.**
Le dictionnaire de prénoms utilisé est volontairement générique et non
exhaustif ; un prénom mixte, rare, ou absent du dictionnaire ne permet
aucune déduction. Chaque valeur déduite est journalisée en `GENDRE_DEVINE`
et doit être considérée comme une proposition à valider, jamais comme une
certitude équivalente à une valeur fournie par la source.

## Vérification sur le corpus réel

Le pipeline a été exécuté sur l'ensemble des fichiers de `data/samples/`
(29 fichiers, 32 onglets). Résultats mesurés, conformes aux volumétries de
référence :

- 19 534 lignes exportées (21 lignes fantômes retirées automatiquement),
- 8 225 lignes sources regroupées en familles ; une seule collision de
  numéro de famille intra-fichier a été détectée dans les données réelles
  (HUTCHINSON, 8 personnes partageant par erreur le même N° Famille), gérée
  par la règle `ADHERENT_MULTIPLE` sans perte de données,
- aucune collision de N° Famille entre fichiers différents,
- 4 076 genres déduits automatiquement du prénom sur les 14 027 lignes qui en
  étaient dépourvues (le reste, `GENDRE_MANQUANT`, correspond à des prénoms
  absents du dictionnaire ou à des lignes sans nom exploitable),
- 8 familles avec rangs source dupliqués détectées et journalisées
  (`RANG_DUPLIQUE`), conforme à l'audit initial des données ; ces rangs sont
  désormais conservés tels quels dans l'export plutôt que recalculés,
- conversion complète en moins de 5 secondes (largement sous la cible de 60 s).

## Tests

```bash
pytest
```

Les tests couvrent le dépivotage V0, le calcul des rangs (tri, jumeaux, cas
particuliers pour le V0 ; conservation du rang source et détection des
incohérences pour le V1), la déduction du genre par prénom, le nettoyage des
CIN/RIB/noms/dates, la détection V0/V1, l'export (feuilles, formats,
traçabilité), ainsi qu'un test d'intégration volumétrique sur le corpus réel
de `data/samples/` (ignoré automatiquement si ce dossier est vide). Toutes
les fixtures de test utilisent des données fabriquées — aucune n'est extraite
de `data/samples/`.
