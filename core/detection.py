"""
core.detection
===============
Détecte, pour chaque onglet d'un classeur Excel importé, s'il s'agit du
format source V0 ("Export Familles", large) ou V1 (long), à partir de la
signature en cellule A1 (§2 et §3). Effectue en un seul passage de lecture
un état des lieux rapide (nombre de lignes/familles, présence d'images
encodées, taux de CIN manquants) afin d'alimenter les bandeaux d'alerte de
l'interface avant même la conversion complète.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from io import BytesIO

import openpyxl

from core.mapping import (
    LIEN_ADHERENT, SIGNATURE_V0, SIGNATURE_V1, V0_COL_ADHERENT, V0_COL_CIN,
    V0_COL_IMAGE, V0_COL_NUM_FAMILLE, V1_COL_CIN, V1_COL_LIEN,
    V1_COL_NUM_FAMILLE, VERSION_V0, VERSION_V1, construire_index_entetes,
    normaliser_entete, normaliser_lien,
)

VERSION_INCONNUE = "Inconnue"


@dataclass
class OngletDetecte:
    """Résultat de la détection pour un onglet donné d'un classeur."""

    nom_fichier: str
    nom_onglet: str
    version: str
    en_tetes: list[str] = field(default_factory=list)
    en_tetes_bruts: list[object] = field(default_factory=list)
    nb_lignes: int = 0
    nb_familles: int = 0
    image_non_vide: bool = False
    cin_absente: bool = False
    pct_sans_cin: float | None = None
    erreur: str | None = None


def _lire_en_tetes(feuille) -> list[object]:
    try:
        premiere_ligne = next(feuille.iter_rows(min_row=1, max_row=1, values_only=True))
    except StopIteration:
        return []
    return list(premiere_ligne)


def _vide(v: object) -> bool:
    return v is None or str(v).strip() == ""


def _analyser_donnees(feuille, version: str, index: dict[str, int]) -> tuple[int, int, bool, bool, float | None]:
    """Un seul passage sur les lignes de données pour calculer : nombre de
    lignes non vides, nombre de familles, présence d'image non vide (V0),
    absence de colonne CIN, et pourcentage d'adhérents sans CIN."""
    nb_lignes = 0
    familles: set[str] = set()
    image_non_vide = False
    nb_familles_sans_cin = 0

    if version == VERSION_V0:
        i_famille = index.get(V0_COL_NUM_FAMILLE)
        i_image = index.get(V0_COL_IMAGE)
        i_cin = index.get(V0_COL_CIN)
        cin_absente = i_cin is None
        for ligne in feuille.iter_rows(min_row=2, values_only=True):
            if not any(c is not None and str(c).strip() != "" for c in ligne):
                continue
            nb_lignes += 1
            if i_famille is not None and i_famille < len(ligne):
                familles.add(str(ligne[i_famille]))
            else:
                familles.add(str(nb_lignes))
            if not image_non_vide and i_image is not None and i_image < len(ligne):
                if not _vide(ligne[i_image]):
                    image_non_vide = True
            if cin_absente or (i_cin is not None and i_cin < len(ligne) and _vide(ligne[i_cin])):
                nb_familles_sans_cin += 1
        nb_familles = len(familles) if familles else nb_lignes
        pct = round(100 * nb_familles_sans_cin / nb_familles, 1) if nb_familles else None
        return nb_lignes, nb_familles, image_non_vide, cin_absente, pct

    # V1 : une ligne = une personne ; on compte les familles distinctes et
    # le taux de CIN manquant côté adhérent uniquement (§5.3).
    i_famille = index.get(V1_COL_NUM_FAMILLE)
    i_lien = index.get(V1_COL_LIEN)
    i_cin = index.get(V1_COL_CIN)
    cin_absente = i_cin is None
    nb_adherents = 0
    for ligne in feuille.iter_rows(min_row=2, values_only=True):
        if not any(c is not None and str(c).strip() != "" for c in ligne):
            continue
        nb_lignes += 1
        if i_famille is not None and i_famille < len(ligne):
            familles.add(str(ligne[i_famille]))
        lien_val = ligne[i_lien] if i_lien is not None and i_lien < len(ligne) else None
        if normaliser_lien(lien_val) == LIEN_ADHERENT:
            nb_adherents += 1
            if cin_absente or (i_cin is not None and i_cin < len(ligne) and _vide(ligne[i_cin])):
                nb_familles_sans_cin += 1
    nb_familles = len(familles)
    pct = round(100 * nb_familles_sans_cin / nb_adherents, 1) if nb_adherents else None
    return nb_lignes, nb_familles, False, cin_absente, pct


def detecter_classeur(contenu: bytes, nom_fichier: str) -> list[OngletDetecte]:
    """Ouvre un classeur (bytes) et détecte la version de chacun de ses onglets.

    Un fichier illisible ne doit jamais interrompre le traitement du lot :
    en cas d'erreur d'ouverture, un unique OngletDetecte "en erreur" est
    renvoyé pour que l'appelant puisse l'afficher et continuer avec les
    autres fichiers.
    """
    try:
        classeur = openpyxl.load_workbook(BytesIO(contenu), read_only=True, data_only=True)
    except Exception as exc:  # noqa: BLE001 - on veut capturer toute erreur de lecture
        return [
            OngletDetecte(
                nom_fichier=nom_fichier,
                nom_onglet="",
                version=VERSION_INCONNUE,
                erreur=f"Fichier illisible : {exc}",
            )
        ]

    resultats: list[OngletDetecte] = []
    for nom_onglet in classeur.sheetnames:
        try:
            feuille = classeur[nom_onglet]
            en_tetes_bruts = _lire_en_tetes(feuille)
            en_tetes = [normaliser_entete(v) for v in en_tetes_bruts]
            signature = en_tetes[0] if en_tetes else ""
            if signature == SIGNATURE_V0:
                version = VERSION_V0
            elif signature == SIGNATURE_V1:
                version = VERSION_V1
            else:
                version = VERSION_INCONNUE

            if version == VERSION_INCONNUE:
                resultats.append(
                    OngletDetecte(
                        nom_fichier=nom_fichier, nom_onglet=nom_onglet, version=version,
                        en_tetes=en_tetes, en_tetes_bruts=en_tetes_bruts,
                    )
                )
                continue

            index = construire_index_entetes(en_tetes_bruts)
            nb_lignes, nb_familles, image_non_vide, cin_absente, pct_sans_cin = _analyser_donnees(feuille, version, index)
            resultats.append(
                OngletDetecte(
                    nom_fichier=nom_fichier, nom_onglet=nom_onglet, version=version,
                    en_tetes=en_tetes, en_tetes_bruts=en_tetes_bruts,
                    nb_lignes=nb_lignes, nb_familles=nb_familles,
                    image_non_vide=image_non_vide, cin_absente=cin_absente, pct_sans_cin=pct_sans_cin,
                )
            )
        except Exception as exc:  # noqa: BLE001
            resultats.append(
                OngletDetecte(
                    nom_fichier=nom_fichier,
                    nom_onglet=nom_onglet,
                    version=VERSION_INCONNUE,
                    erreur=f"Onglet illisible : {exc}",
                )
            )
    return resultats
