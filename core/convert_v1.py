"""
core.convert_v1
=================
Remappage du format source V1 (long, une ligne = une personne) vers le
format cible, §3. Les 11 colonnes du noyau sont toujours présentes ; seules
les colonnes surnuméraires varient selon le fichier (5 variantes, 12 à 16
colonnes) et sont purement ignorées. Le lecteur tolère les en-têtes
dupliqués (benetton, esol : "Date de radiation" x2) grâce à
`construire_index_entetes`, qui ne retient que la première occurrence.
Le Rang source est conservé à titre indicatif (F_RANG_SOURCE) pour être
comparé au rang recalculé par core.ranking, mais n'est jamais réutilisé tel
quel (§4, note sur la fiabilité du rang source).
"""
from __future__ import annotations

from core.anomalies import CollecteurAnomalies
from core.mapping import (
    F_CIN, F_CLIENT, F_COLONNE_SOURCE, F_DATE_AFFILIATION, F_DATE_NAISSANCE,
    F_FICHIER_SOURCE, F_GENDRE, F_INDEX_SOURCE, F_LIEN, F_LIGNE_SOURCE,
    F_NOM, F_NUM_FAMILLE, F_ONGLET_SOURCE, F_RANG, F_RANG_SOURCE, F_RIB,
    LIEN_ADHERENT, V1_COL_CIN, V1_COL_CLIENT, V1_COL_DATE_AFFILIATION,
    V1_COL_DATE_NAISSANCE, V1_COL_GENDRE, V1_COL_LIEN, V1_COL_NOM,
    V1_COL_NUM_FAMILLE, V1_COL_RANG, V1_COL_RIB, construire_index_entetes,
    normaliser_entete, normaliser_lien,
)
from core.normalize import (
    est_ligne_fantome, nettoyer_cin, nettoyer_nom, nettoyer_rib,
    nom_ordre_suspect, normaliser_gendre, parser_date,
)


def _valeur(ligne: tuple, index: dict[str, int], colonne: str) -> object:
    i = index.get(colonne)
    if i is None or i >= len(ligne):
        return None
    return ligne[i]


def _vide(v: object) -> bool:
    return v is None or str(v).strip() == ""


def convertir_v1(
    lignes_source: list[tuple],
    en_tetes: list[object],
    nom_fichier: str,
    nom_onglet: str,
    collecteur: CollecteurAnomalies,
    *,
    uppercase_noms: bool = True,
    supprimer_lignes_fantomes: bool = True,
    completer_cin: bool = True,
    vider_cin_factices: bool = True,
) -> list[dict]:
    """Convertit les lignes brutes d'un onglet V1 (une ligne = une personne)
    en lignes cible. `lignes_source` doit commencer à la première ligne de
    DONNÉES (l'en-tête est fourni à part, ligne 1).
    """
    index = construire_index_entetes(en_tetes)
    resultats: list[dict] = []

    for position, ligne in enumerate(lignes_source):
        ligne_source_num = position + 2

        client = normaliser_entete(_valeur(ligne, index, V1_COL_CLIENT)) or ""
        num_famille_brut = _valeur(ligne, index, V1_COL_NUM_FAMILLE)
        num_famille = str(num_famille_brut).strip() if not _vide(num_famille_brut) else ""
        lien_brut = _valeur(ligne, index, V1_COL_LIEN)
        nom_brut = _valeur(ligne, index, V1_COL_NOM)
        date_brut = _valeur(ligne, index, V1_COL_DATE_NAISSANCE)
        rang_brut = _valeur(ligne, index, V1_COL_RANG)

        if est_ligne_fantome(lien_brut, nom_brut, date_brut, rang_brut):
            collecteur.ajouter(
                fichier_source=nom_fichier, onglet_source=nom_onglet, ligne_source=ligne_source_num,
                colonne_source="", code="LIGNE_FANTOME", num_famille=num_famille, nom="",
                champ_cible="", valeur_origine=None, valeur_retenue=None,
                message="Ligne sans Rang, Lien, Nom ni Date de naissance (seuls Client et N° Famille renseignés).",
            )
            if supprimer_lignes_fantomes:
                continue

        resultat = {
            F_FICHIER_SOURCE: nom_fichier,
            F_ONGLET_SOURCE: nom_onglet,
            F_LIGNE_SOURCE: ligne_source_num,
            F_COLONNE_SOURCE: "",
            F_INDEX_SOURCE: position,
            F_RANG_SOURCE: rang_brut,
            F_CLIENT: client,
            F_NUM_FAMILLE: num_famille,
            F_LIEN: lien_brut if lien_brut is not None else "",
            F_GENDRE: "",
            F_NOM: "",
            F_DATE_NAISSANCE: None,
            F_DATE_AFFILIATION: None,
            F_RANG: None,
            F_RIB: "",
            F_CIN: "",
        }

        nom_nettoye, modifie = nettoyer_nom(nom_brut, uppercase_noms)
        if _vide(nom_brut):
            resultat[F_NOM] = ""
        elif nom_nettoye == "":
            collecteur.ajouter(
                fichier_source=nom_fichier, onglet_source=nom_onglet, ligne_source=ligne_source_num,
                colonne_source=V1_COL_NOM, code="NOM_ILLISIBLE", num_famille=num_famille, nom="",
                champ_cible="Nom", valeur_origine=nom_brut, valeur_retenue=None,
                message="Le nom est devenu vide après nettoyage (astérisques, ponctuation...).",
            )
        else:
            if modifie:
                collecteur.ajouter(
                    fichier_source=nom_fichier, onglet_source=nom_onglet, ligne_source=ligne_source_num,
                    colonne_source=V1_COL_NOM, code="NOM_NETTOYE", num_famille=num_famille, nom=nom_nettoye,
                    champ_cible="Nom", valeur_origine=nom_brut, valeur_retenue=nom_nettoye,
                    message="Nom nettoyé (espaces, astérisques, ponctuation ou casse).",
                )
            if nom_ordre_suspect(nom_nettoye):
                collecteur.ajouter(
                    fichier_source=nom_fichier, onglet_source=nom_onglet, ligne_source=ligne_source_num,
                    colonne_source=V1_COL_NOM, code="NOM_ORDRE_SUSPECT", num_famille=num_famille, nom=nom_nettoye,
                    champ_cible="Nom", valeur_origine=nom_brut, valeur_retenue=nom_nettoye,
                    message="Ordre Prénom / NOM possible (à valider manuellement) ; valeur conservée telle quelle.",
                )
            resultat[F_NOM] = nom_nettoye

        date_naissance, invalide = parser_date(date_brut)
        if invalide:
            collecteur.ajouter(
                fichier_source=nom_fichier, onglet_source=nom_onglet, ligne_source=ligne_source_num,
                colonne_source=V1_COL_DATE_NAISSANCE, code="DATE_INVALIDE", num_famille=num_famille, nom=resultat[F_NOM],
                champ_cible="Date de naissance", valeur_origine=date_brut, valeur_retenue=None,
                message="Date de naissance illisible ; champ vidé.",
            )
        resultat[F_DATE_NAISSANCE] = date_naissance

        gendre_brut = _valeur(ligne, index, V1_COL_GENDRE)
        gendre = normaliser_gendre(gendre_brut)
        if gendre == "":
            collecteur.ajouter(
                fichier_source=nom_fichier, onglet_source=nom_onglet, ligne_source=ligne_source_num,
                colonne_source=V1_COL_GENDRE, code="GENDRE_MANQUANT", num_famille=num_famille, nom=resultat[F_NOM],
                champ_cible="Gendre", valeur_origine=gendre_brut, valeur_retenue=None,
                message="Genre manquant ou non reconnu dans la source.",
            )
        resultat[F_GENDRE] = gendre

        # Est-ce la ligne d'adhérent ? Approximation au moment de la lecture
        # (avant recalcul définitif du rang par core.ranking), utilisée
        # uniquement pour décider si un CIN vide doit être signalé (§5.3).
        est_adherent_probable = normaliser_lien(lien_brut) == LIEN_ADHERENT

        cin_brut = _valeur(ligne, index, V1_COL_CIN)
        resultat_cin = nettoyer_cin(cin_brut, completer_cin=completer_cin, vider_cin_factices=vider_cin_factices)
        if resultat_cin.code:
            collecteur.ajouter(
                fichier_source=nom_fichier, onglet_source=nom_onglet, ligne_source=ligne_source_num,
                colonne_source=V1_COL_CIN, code=resultat_cin.code, num_famille=num_famille, nom=resultat[F_NOM],
                champ_cible="Identité gouvernementale", valeur_origine=cin_brut, valeur_retenue=resultat_cin.valeur or None,
                message=resultat_cin.message,
            )
        elif resultat_cin.valeur == "" and _vide(cin_brut) and est_adherent_probable:
            collecteur.ajouter(
                fichier_source=nom_fichier, onglet_source=nom_onglet, ligne_source=ligne_source_num,
                colonne_source=V1_COL_CIN, code="CIN_MANQUANT_ADHERENT", num_famille=num_famille, nom=resultat[F_NOM],
                champ_cible="Identité gouvernementale", valeur_origine=cin_brut, valeur_retenue=None,
                message="Adhérent sans CIN dans la source.",
            )
        resultat[F_CIN] = resultat_cin.valeur

        rib_brut = _valeur(ligne, index, V1_COL_RIB)
        resultat_rib = nettoyer_rib(rib_brut)
        if resultat_rib.code:
            collecteur.ajouter(
                fichier_source=nom_fichier, onglet_source=nom_onglet, ligne_source=ligne_source_num,
                colonne_source=V1_COL_RIB, code=resultat_rib.code, num_famille=num_famille, nom=resultat[F_NOM],
                champ_cible="RIB", valeur_origine=rib_brut, valeur_retenue=resultat_rib.valeur or None,
                message=resultat_rib.message,
            )
        resultat[F_RIB] = resultat_rib.valeur

        date_affiliation_brut = _valeur(ligne, index, V1_COL_DATE_AFFILIATION)
        date_affiliation, invalide_affiliation = parser_date(date_affiliation_brut)
        if invalide_affiliation:
            collecteur.ajouter(
                fichier_source=nom_fichier, onglet_source=nom_onglet, ligne_source=ligne_source_num,
                colonne_source=V1_COL_DATE_AFFILIATION, code="DATE_INVALIDE", num_famille=num_famille, nom=resultat[F_NOM],
                champ_cible="Date d'affiliation", valeur_origine=date_affiliation_brut, valeur_retenue=None,
                message="Date d'affiliation illisible ; champ vidé.",
            )
        resultat[F_DATE_AFFILIATION] = date_affiliation

        resultats.append(resultat)

    return resultats
