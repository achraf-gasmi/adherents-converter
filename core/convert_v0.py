"""
core.convert_v0
=================
Dépivotage du format source V0 ("Export Familles", une ligne = une famille au
format large) vers des lignes cible (une ligne = une personne), §2. Le
mapping des colonnes se fait exclusivement par nom d'en-tête pour tolérer les
4 variantes de colonnes observées (19 à 22 colonnes selon les fichiers). La
colonne IMAGE (photos encodées en base64) est systématiquement ignorée mais
détectée pour déclencher l'avertissement de l'interface.
"""
from __future__ import annotations

from core.anomalies import CollecteurAnomalies
from core.mapping import (
    F_CIN, F_CLIENT, F_COLONNE_SOURCE, F_DATE_AFFILIATION, F_DATE_NAISSANCE,
    F_FICHIER_SOURCE, F_GENDRE, F_INDEX_SOURCE, F_LIEN, F_LIGNE_SOURCE,
    F_NOM, F_NUM_FAMILLE, F_ONGLET_SOURCE, F_RANG, F_RANG_SOURCE, F_RIB,
    F_VERSION_SOURCE, LIEN_ADHERENT, LIEN_CONJOINT, LIEN_ENFANT,
    V0_COL_ADHERENT, V0_COL_CIN, V0_COL_CLIENT, V0_COL_CONJOINT,
    V0_COL_DATE_NAISS, V0_COL_DATE_NAISS_CONJ, V0_COL_IMAGE, V0_COL_NUM_FAMILLE,
    V0_NB_ENFANTS_MAX, VERSION_V0, construire_index_entetes, normaliser_entete,
    v0_col_date_naiss_enfant, v0_col_enfant,
)
from core.normalize import (
    nettoyer_cin, nettoyer_nom, nom_ordre_suspect, parser_date, resoudre_gendre,
)


def _valeur(ligne: tuple, index: dict[str, int], colonne: str) -> object:
    i = index.get(colonne)
    if i is None or i >= len(ligne):
        return None
    return ligne[i]


def _vide(v: object) -> bool:
    return v is None or str(v).strip() == ""


def _nouvelle_ligne(fichier: str, onglet: str, ligne_source: int, client: str, num_famille: str) -> dict:
    return {
        F_FICHIER_SOURCE: fichier,
        F_ONGLET_SOURCE: onglet,
        F_LIGNE_SOURCE: ligne_source,
        F_COLONNE_SOURCE: "",
        F_INDEX_SOURCE: 0,
        F_RANG_SOURCE: None,
        F_VERSION_SOURCE: VERSION_V0,
        F_CLIENT: client,
        F_NUM_FAMILLE: num_famille,
        F_LIEN: "",
        F_GENDRE: "",
        F_NOM: "",
        F_DATE_NAISSANCE: None,
        F_DATE_AFFILIATION: None,
        F_RANG: None,
        F_RIB: "",
        F_CIN: "",
    }


def _traiter_personne(
    *, fichier: str, onglet: str, ligne_source: int, client: str, num_famille: str,
    lien: str, nom_brut: object, date_brut: object, colonne_nom: str, colonne_date: str,
    index_source: int, uppercase_noms: bool, collecteur: CollecteurAnomalies,
) -> dict | None:
    """Construit la ligne cible d'une personne (adhérent, conjoint ou
    enfant-n) à partir des cellules brutes correspondantes. Renvoie None si
    ni le nom ni la date ne sont renseignés (le membre n'existe pas)."""
    if _vide(nom_brut) and _vide(date_brut):
        return None

    resultat = _nouvelle_ligne(fichier, onglet, ligne_source, client, num_famille)
    resultat[F_LIEN] = lien
    resultat[F_INDEX_SOURCE] = index_source
    resultat[F_COLONNE_SOURCE] = colonne_nom

    nom_nettoye, modifie = nettoyer_nom(nom_brut, uppercase_noms)
    if _vide(nom_brut) and not _vide(date_brut):
        resultat[F_NOM] = ""
    elif nom_nettoye == "":
        collecteur.ajouter(
            fichier_source=fichier, onglet_source=onglet, ligne_source=ligne_source,
            colonne_source=colonne_nom, code="NOM_ILLISIBLE", num_famille=num_famille, nom="",
            champ_cible="Nom", valeur_origine=nom_brut, valeur_retenue=None,
            message="Le nom est devenu vide après nettoyage (astérisques, ponctuation...).",
        )
        resultat[F_NOM] = ""
    else:
        if modifie:
            collecteur.ajouter(
                fichier_source=fichier, onglet_source=onglet, ligne_source=ligne_source,
                colonne_source=colonne_nom, code="NOM_NETTOYE", num_famille=num_famille, nom=nom_nettoye,
                champ_cible="Nom", valeur_origine=nom_brut, valeur_retenue=nom_nettoye,
                message="Nom nettoyé (espaces, astérisques, ponctuation ou casse).",
            )
        if nom_ordre_suspect(nom_nettoye):
            collecteur.ajouter(
                fichier_source=fichier, onglet_source=onglet, ligne_source=ligne_source,
                colonne_source=colonne_nom, code="NOM_ORDRE_SUSPECT", num_famille=num_famille, nom=nom_nettoye,
                champ_cible="Nom", valeur_origine=nom_brut, valeur_retenue=nom_nettoye,
                message="Ordre Prénom / NOM possible (à valider manuellement) ; valeur conservée telle quelle.",
            )
        resultat[F_NOM] = nom_nettoye

    date_naissance, invalide = parser_date(date_brut)
    if invalide:
        collecteur.ajouter(
            fichier_source=fichier, onglet_source=onglet, ligne_source=ligne_source,
            colonne_source=colonne_date, code="DATE_INVALIDE", num_famille=num_famille, nom=resultat[F_NOM],
            champ_cible="Date de naissance", valeur_origine=date_brut, valeur_retenue=None,
            message="Date de naissance illisible ; champ vidé.",
        )
    resultat[F_DATE_NAISSANCE] = date_naissance

    resultat_gendre = resoudre_gendre(None, resultat[F_NOM])
    if resultat_gendre.code == "GENDRE_DEVINE":
        dernier_mot = resultat[F_NOM].split()[-1] if resultat[F_NOM] else ""
        collecteur.ajouter(
            fichier_source=fichier, onglet_source=onglet, ligne_source=ligne_source,
            colonne_source="", code="GENDRE_DEVINE", num_famille=num_famille, nom=resultat[F_NOM],
            champ_cible="Gendre", valeur_origine=None, valeur_retenue=resultat_gendre.valeur,
            message=f"Genre absent du format source V0 ; déduit du prénom (\"{dernier_mot}\") -> à valider.",
        )
    elif resultat_gendre.code == "GENDRE_DEVINE_INCERTAIN":
        collecteur.ajouter(
            fichier_source=fichier, onglet_source=onglet, ligne_source=ligne_source,
            colonne_source="", code="GENDRE_DEVINE_INCERTAIN", num_famille=num_famille, nom=resultat[F_NOM],
            champ_cible="Gendre", valeur_origine=None, valeur_retenue=resultat_gendre.valeur,
            message="Genre absent du format source V0 ; prénom non reconnu, valeur déduite par heuristique de secours -> à valider impérativement.",
        )
    resultat[F_GENDRE] = resultat_gendre.valeur

    return resultat


def convertir_v0(
    lignes_source: list[tuple],
    en_tetes: list[object],
    nom_fichier: str,
    nom_onglet: str,
    collecteur: CollecteurAnomalies,
    *,
    uppercase_noms: bool = True,
    completer_cin: bool = True,
    vider_cin_factices: bool = True,
) -> list[dict]:
    """Convertit les lignes brutes d'un onglet V0 (une ligne = une famille)
    en lignes cible (une ligne = une personne). `lignes_source` doit
    commencer à la première ligne de DONNÉES (l'en-tête est fourni à part).
    """
    index = construire_index_entetes(en_tetes)
    colonnes_reconnues = set(index.keys())
    image_presente_colonne = V0_COL_IMAGE in colonnes_reconnues

    resultats: list[dict] = []

    for position, ligne in enumerate(lignes_source):
        ligne_source_num = position + 2  # +1 pour l'en-tête, +1 car position est 0-based
        client = normaliser_entete(_valeur(ligne, index, V0_COL_CLIENT)) or ""
        num_famille_brut = _valeur(ligne, index, V0_COL_NUM_FAMILLE)
        num_famille = str(num_famille_brut).strip() if not _vide(num_famille_brut) else ""

        if image_presente_colonne and not _vide(_valeur(ligne, index, V0_COL_IMAGE)):
            collecteur.ajouter(
                fichier_source=nom_fichier, onglet_source=nom_onglet, ligne_source=ligne_source_num,
                colonne_source=V0_COL_IMAGE, code="IMAGE_BASE64_DETECTEE", num_famille=num_famille,
                champ_cible="", valeur_origine="[image encodée]", valeur_retenue=None,
                message="Colonne IMAGE non vide (photo encodée en base64) ; donnée personnelle ignorée, jamais exportée.",
            )

        # Adhérent
        adherent = _traiter_personne(
            fichier=nom_fichier, onglet=nom_onglet, ligne_source=ligne_source_num, client=client,
            num_famille=num_famille, lien=LIEN_ADHERENT,
            nom_brut=_valeur(ligne, index, V0_COL_ADHERENT), date_brut=_valeur(ligne, index, V0_COL_DATE_NAISS),
            colonne_nom=V0_COL_ADHERENT, colonne_date=V0_COL_DATE_NAISS, index_source=0,
            uppercase_noms=uppercase_noms, collecteur=collecteur,
        )
        if adherent is not None:
            if V0_COL_CIN in colonnes_reconnues:
                cin_brut = _valeur(ligne, index, V0_COL_CIN)
                resultat_cin = nettoyer_cin(cin_brut, completer_cin=completer_cin, vider_cin_factices=vider_cin_factices)
                if resultat_cin.code:
                    collecteur.ajouter(
                        fichier_source=nom_fichier, onglet_source=nom_onglet, ligne_source=ligne_source_num,
                        colonne_source=V0_COL_CIN, code=resultat_cin.code, num_famille=num_famille,
                        nom=adherent[F_NOM], champ_cible="Identité gouvernementale",
                        valeur_origine=cin_brut, valeur_retenue=resultat_cin.valeur or None,
                        message=resultat_cin.message,
                    )
                if resultat_cin.valeur == "" and _vide(cin_brut):
                    collecteur.ajouter(
                        fichier_source=nom_fichier, onglet_source=nom_onglet, ligne_source=ligne_source_num,
                        colonne_source=V0_COL_CIN, code="CIN_MANQUANT_ADHERENT", num_famille=num_famille,
                        nom=adherent[F_NOM], champ_cible="Identité gouvernementale",
                        valeur_origine=cin_brut, valeur_retenue=None,
                        message="Adhérent sans CIN dans la source.",
                    )
                adherent[F_CIN] = resultat_cin.valeur
            else:
                # Colonne CIN absente du fichier (variantes BOBA/COATS, 19 colonnes) :
                # pas d'anomalie par personne, seulement une alerte au niveau du
                # fichier affichée par l'interface (cf. OngletDetecte.cin_absente).
                adherent[F_CIN] = ""
            resultats.append(adherent)

        # Conjoint
        conjoint = _traiter_personne(
            fichier=nom_fichier, onglet=nom_onglet, ligne_source=ligne_source_num, client=client,
            num_famille=num_famille, lien=LIEN_CONJOINT,
            nom_brut=_valeur(ligne, index, V0_COL_CONJOINT), date_brut=_valeur(ligne, index, V0_COL_DATE_NAISS_CONJ),
            colonne_nom=V0_COL_CONJOINT, colonne_date=V0_COL_DATE_NAISS_CONJ, index_source=0,
            uppercase_noms=uppercase_noms, collecteur=collecteur,
        )
        if conjoint is not None:
            resultats.append(conjoint)

        # Enfants 1 à 5
        for n in range(1, V0_NB_ENFANTS_MAX + 1):
            col_nom = v0_col_enfant(n)
            col_date = v0_col_date_naiss_enfant(n)
            if col_nom not in colonnes_reconnues:
                continue
            enfant = _traiter_personne(
                fichier=nom_fichier, onglet=nom_onglet, ligne_source=ligne_source_num, client=client,
                num_famille=num_famille, lien=LIEN_ENFANT,
                nom_brut=_valeur(ligne, index, col_nom), date_brut=_valeur(ligne, index, col_date),
                colonne_nom=col_nom, colonne_date=col_date, index_source=n,
                uppercase_noms=uppercase_noms, collecteur=collecteur,
            )
            if enfant is not None:
                resultats.append(enfant)

    return resultats
