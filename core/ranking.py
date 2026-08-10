"""
core.ranking
=============
Cœur métier de la conversion (§4). Deux modes de calcul du rang, selon la
version source :

- V0 : aucun rang n'existe dans la source (le format ne porte pas cette
  colonne) ; le rang est entièrement calculé (0 = adhérent, 1 = conjoint
  toujours réservé, 2+ = enfants triés par âge avec départage déterministe
  des jumeaux).
- V1 : le rang fourni par la source est désormais conservé tel quel dans
  l'export — décision métier validée après retour des utilisateurs : ne plus
  corriger le rang source. Le module se contente de détecter et journaliser
  les incohérences (famille sans adhérent, rangs dupliqués, rang réservé
  porté par la mauvaise personne, ordre des enfants incohérent avec leur
  âge...) sans jamais modifier la valeur exportée.

Le module effectue aussi les vérifications de cohérence familiale qui
nécessitent une vue d'ensemble sur la famille (filiation, doublons), quelle
que soit l'origine du rang. Opère sur des listes de dictionnaires (un dict =
une ligne cible en cours de construction) portant les champs internes
définis dans core.mapping.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date

from core.anomalies import CollecteurAnomalies
from core.mapping import (
    F_CIN, F_CLIENT, F_COLONNE_SOURCE, F_DATE_AFFILIATION, F_DATE_NAISSANCE,
    F_FICHIER_SOURCE, F_GENDRE, F_INDEX_SOURCE, F_LIEN, F_LIGNE_SOURCE,
    F_NOM, F_NUM_FAMILLE, F_ONGLET_SOURCE, F_RANG, F_RANG_SOURCE, F_RIB,
    F_VERSION_SOURCE, LIEN_ADHERENT, LIEN_CONJOINT, LIEN_ENFANT, VERSION_V1,
    normaliser_lien,
)

AGE_MINIMUM_ADHERENT = 16
ANNEE_MINIMUM_DATE = 1920


def _cle_tri_enfant(ligne: dict) -> tuple:
    return (ligne[F_DATE_NAISSANCE], ligne[F_NOM] or "", ligne[F_INDEX_SOURCE])


def _log(collecteur: CollecteurAnomalies, ligne: dict, *, code: str, champ_cible: str = "",
          colonne_source: str = "", valeur_origine: object = None, valeur_retenue: object = None,
          message: str = "") -> None:
    collecteur.ajouter(
        fichier_source=ligne[F_FICHIER_SOURCE],
        onglet_source=ligne[F_ONGLET_SOURCE],
        ligne_source=ligne[F_LIGNE_SOURCE],
        colonne_source=colonne_source,
        code=code,
        num_famille=ligne[F_NUM_FAMILLE],
        nom=ligne[F_NOM],
        champ_cible=champ_cible,
        valeur_origine=valeur_origine,
        valeur_retenue=valeur_retenue,
        message=message,
    )


def _detecter_doublons_intra_famille(lignes_famille: list[dict], collecteur: CollecteurAnomalies) -> None:
    """Même nom + même date de naissance dans une famille (§5.7). Ligne
    conservée dans tous les cas : décision humaine, jamais de fusion."""
    vus: dict[tuple, dict] = {}
    for ligne in lignes_famille:
        cle = (ligne[F_NOM] or "", ligne[F_DATE_NAISSANCE])
        if cle[0] == "" and cle[1] is None:
            continue
        if cle in vus:
            _log(
                collecteur, ligne, code="DOUBLON_INTRA_FAMILLE",
                message="Même nom et même date de naissance qu'une autre ligne de cette famille ; les deux lignes sont conservées.",
            )
        else:
            vus[cle] = ligne


# --------------------------------------------------------------------------
# V0 : le rang n'existe pas dans la source, il est entièrement calculé.
# --------------------------------------------------------------------------

def _traiter_famille_v0(lignes_famille: list[dict], collecteur: CollecteurAnomalies) -> None:
    """Assigne le rang de chaque personne d'une même famille V0 (§4) et
    journalise les anomalies liées au regroupement (adhérent multiple,
    conjoint multiple, famille sans adhérent, lien manquant)."""

    adherents: list[dict] = []
    conjoints: list[dict] = []
    enfants: list[dict] = []
    autres: list[dict] = []

    for ligne in lignes_famille:
        lien_brut = ligne[F_LIEN]
        lien = normaliser_lien(lien_brut)
        ligne[F_LIEN] = lien or ""
        if lien == LIEN_ADHERENT:
            adherents.append(ligne)
        elif lien == LIEN_CONJOINT:
            conjoints.append(ligne)
        elif lien == LIEN_ENFANT:
            enfants.append(ligne)
        else:
            autres.append(ligne)
            _log(
                collecteur, ligne, code="LIEN_MANQUANT", champ_cible="Lien",
                valeur_origine=lien_brut, valeur_retenue=None,
                message="Lien vide ou non reconnu ; ligne conservée sans rang.",
            )

    prochain_rang = 2
    extras: list[dict] = []

    if not adherents:
        reference = lignes_famille[0]
        _log(
            collecteur, reference, code="FAMILLE_SANS_ADHERENT",
            message="Aucune ligne avec Lien = Adhérent dans cette famille ; rangs recalculés sans adhérent de référence.",
        )
    else:
        adherents[0][F_RANG] = 0
        for supplementaire in adherents[1:]:
            _log(
                collecteur, supplementaire, code="ADHERENT_MULTIPLE", champ_cible="Rang",
                message="Plusieurs lignes avec Lien = Adhérent dans cette famille ; seule la première conserve le rang 0.",
            )
            extras.append(supplementaire)

    if conjoints:
        conjoints[0][F_RANG] = 1
        for supplementaire in conjoints[1:]:
            _log(
                collecteur, supplementaire, code="CONJOINT_MULTIPLE", champ_cible="Rang",
                message="Plusieurs lignes avec Lien = Conjoint dans cette famille ; seule la première conserve le rang 1.",
            )
            extras.append(supplementaire)

    enfants_avec_date = [e for e in enfants if e[F_DATE_NAISSANCE] is not None]
    enfants_sans_date = sorted(
        (e for e in enfants if e[F_DATE_NAISSANCE] is None), key=lambda e: e[F_INDEX_SOURCE]
    )
    enfants_avec_date.sort(key=_cle_tri_enfant)

    # Départage des jumeaux : même date de naissance -> tri secondaire par nom
    # puis par ordre source, déterministe et reproductible (§4).
    par_date: dict[date, list[dict]] = defaultdict(list)
    for e in enfants_avec_date:
        par_date[e[F_DATE_NAISSANCE]].append(e)
    for meme_date, groupe in par_date.items():
        if len(groupe) > 1:
            for enfant in groupe:
                _log(
                    collecteur, enfant, code="JUMEAUX_DEPARTAGES", champ_cible="Rang",
                    valeur_origine=meme_date.strftime("%d/%m/%Y"),
                    message="Plusieurs enfants nés le même jour ; ordre départagé par nom puis par ordre d'apparition dans la source.",
                )

    for enfant in enfants_sans_date:
        _log(
            collecteur, enfant, code="RANG_DATE_MANQUANTE", champ_cible="Date de naissance",
            message="Date de naissance manquante pour cet enfant ; placé en fin de fratrie, ordre source préservé.",
        )

    for enfant in enfants_avec_date + enfants_sans_date:
        enfant[F_RANG] = prochain_rang
        prochain_rang += 1

    for extra in sorted(extras, key=lambda e: e[F_INDEX_SOURCE]):
        extra[F_RANG] = prochain_rang
        prochain_rang += 1

    _detecter_doublons_intra_famille(lignes_famille, collecteur)


# --------------------------------------------------------------------------
# V1 : le rang source est désormais conservé tel quel (décision métier),
# uniquement contrôlé et signalé, jamais corrigé.
# --------------------------------------------------------------------------

def _assigner_rang_source(ligne: dict, collecteur: CollecteurAnomalies) -> None:
    brut = ligne.get(F_RANG_SOURCE)
    if brut is None or (isinstance(brut, str) and brut.strip() == ""):
        ligne[F_RANG] = None
        _log(
            collecteur, ligne, code="RANG_MANQUANT", champ_cible="Rang",
            valeur_origine=brut, valeur_retenue=None,
            message="Rang absent dans la source ; laissé vide (non recalculé).",
        )
        return
    try:
        ligne[F_RANG] = int(float(str(brut).strip()))
    except (TypeError, ValueError):
        ligne[F_RANG] = None
        _log(
            collecteur, ligne, code="RANG_MANQUANT", champ_cible="Rang",
            valeur_origine=brut, valeur_retenue=None,
            message="Rang illisible dans la source ; laissé vide (non recalculé).",
        )


def _traiter_famille_v1(lignes_famille: list[dict], collecteur: CollecteurAnomalies) -> None:
    """Conserve le rang fourni par la source V1 tel quel : la valeur écrite
    dans F_RANG est toujours la valeur source (éventuellement vide si
    absente/illisible), jamais une valeur recalculée. Détecte et journalise
    les incohérences sans jamais modifier le rang exporté."""

    adherents: list[dict] = []
    conjoints: list[dict] = []
    enfants: list[dict] = []
    autres: list[dict] = []

    for ligne in lignes_famille:
        lien_brut = ligne[F_LIEN]
        lien = normaliser_lien(lien_brut)
        ligne[F_LIEN] = lien or ""
        _assigner_rang_source(ligne, collecteur)
        if lien == LIEN_ADHERENT:
            adherents.append(ligne)
        elif lien == LIEN_CONJOINT:
            conjoints.append(ligne)
        elif lien == LIEN_ENFANT:
            enfants.append(ligne)
        else:
            autres.append(ligne)
            _log(
                collecteur, ligne, code="LIEN_MANQUANT", champ_cible="Lien",
                valeur_origine=lien_brut, valeur_retenue=None,
                message="Lien vide ou non reconnu ; rang source conservé tel quel.",
            )

    if not adherents:
        _log(
            collecteur, lignes_famille[0], code="FAMILLE_SANS_ADHERENT",
            message="Aucune ligne avec Lien = Adhérent dans cette famille ; rangs source conservés tels quels.",
        )
    for supplementaire in adherents[1:]:
        _log(
            collecteur, supplementaire, code="ADHERENT_MULTIPLE", champ_cible="Rang",
            valeur_origine=supplementaire[F_RANG], valeur_retenue=supplementaire[F_RANG],
            message="Plusieurs lignes avec Lien = Adhérent dans cette famille ; rangs source conservés tels quels.",
        )
    for supplementaire in conjoints[1:]:
        _log(
            collecteur, supplementaire, code="CONJOINT_MULTIPLE", champ_cible="Rang",
            valeur_origine=supplementaire[F_RANG], valeur_retenue=supplementaire[F_RANG],
            message="Plusieurs lignes avec Lien = Conjoint dans cette famille ; rangs source conservés tels quels.",
        )

    # Cohérence Lien <-> Rang, sans jamais corriger la valeur exportée.
    for ligne in adherents:
        if ligne[F_RANG] is not None and ligne[F_RANG] != 0:
            _log(
                collecteur, ligne, code="RANG_INCOHERENT", champ_cible="Rang",
                valeur_origine=ligne[F_RANG], valeur_retenue=ligne[F_RANG],
                message="Lien = Adhérent mais Rang source différent de 0 ; valeur source conservée telle quelle.",
            )
    for ligne in conjoints:
        if ligne[F_RANG] is not None and ligne[F_RANG] != 1:
            _log(
                collecteur, ligne, code="RANG_INCOHERENT", champ_cible="Rang",
                valeur_origine=ligne[F_RANG], valeur_retenue=ligne[F_RANG],
                message="Lien = Conjoint mais Rang source différent de 1 ; valeur source conservée telle quelle.",
            )
    for ligne in enfants + autres:
        if ligne[F_RANG] in (0, 1):
            role = ligne[F_LIEN] or "non reconnu"
            _log(
                collecteur, ligne, code="RANG_INCOHERENT", champ_cible="Rang",
                valeur_origine=ligne[F_RANG], valeur_retenue=ligne[F_RANG],
                message=f"Rang {ligne[F_RANG]} normalement réservé à l'adhérent/conjoint, incohérent avec Lien = {role} ; valeur source conservée telle quelle.",
            )

    # Rangs dupliqués au sein de la famille (le rang source n'étant plus
    # corrigé, deux lignes peuvent désormais porter le même rang).
    compte = Counter(l[F_RANG] for l in lignes_famille if l[F_RANG] is not None)
    for ligne in lignes_famille:
        if ligne[F_RANG] is not None and compte[ligne[F_RANG]] > 1:
            _log(
                collecteur, ligne, code="RANG_DUPLIQUE", champ_cible="Rang",
                valeur_origine=ligne[F_RANG], valeur_retenue=ligne[F_RANG],
                message=f"Le rang {ligne[F_RANG]} est porté par plusieurs lignes de cette famille ; valeurs source conservées telles quelles.",
            )

    # Ordre des enfants incohérent avec leur âge : indicatif uniquement,
    # aucun réordonnancement n'est effectué.
    enfants_avec_date_et_rang = [e for e in enfants if e[F_DATE_NAISSANCE] is not None and e[F_RANG] is not None]
    if len(enfants_avec_date_et_rang) > 1:
        par_rang = sorted(enfants_avec_date_et_rang, key=lambda e: e[F_RANG])
        par_age = sorted(enfants_avec_date_et_rang, key=_cle_tri_enfant)
        if [id(e) for e in par_rang] != [id(e) for e in par_age]:
            for enfant in enfants_avec_date_et_rang:
                _log(
                    collecteur, enfant, code="RANG_ENFANTS_DESORDONNES", champ_cible="Rang",
                    valeur_origine=enfant[F_RANG], valeur_retenue=enfant[F_RANG],
                    message="L'ordre des rangs des enfants ne correspond pas à l'ordre de leurs dates de naissance ; rangs source conservés tels quels.",
                )

    # Jumeaux : signalement informatif uniquement, aucun départage n'est
    # effectué puisque le rang source n'est plus modifié.
    par_date: dict[date, list[dict]] = defaultdict(list)
    for e in enfants:
        if e[F_DATE_NAISSANCE] is not None:
            par_date[e[F_DATE_NAISSANCE]].append(e)
    for meme_date, groupe in par_date.items():
        if len(groupe) > 1:
            for enfant in groupe:
                _log(
                    collecteur, enfant, code="JUMEAUX_DEPARTAGES", champ_cible="Rang",
                    valeur_origine=meme_date.strftime("%d/%m/%Y"),
                    message="Plusieurs enfants nés le même jour ; rangs source conservés tels quels, ordre à vérifier manuellement.",
                )

    _detecter_doublons_intra_famille(lignes_famille, collecteur)


def _verifier_dates_famille(lignes_famille: list[dict], collecteur: CollecteurAnomalies, date_reference: date) -> None:
    """Vérifications de cohérence des dates qui nécessitent le contexte de
    la famille (filiation) ou une date de référence (âge, futur) — §5.5."""

    adherent = next((l for l in lignes_famille if l[F_RANG] == 0), None)
    date_adherent = adherent[F_DATE_NAISSANCE] if adherent else None

    for ligne in lignes_famille:
        naissance = ligne[F_DATE_NAISSANCE]
        if naissance is None:
            continue
        if naissance > date_reference:
            _log(
                collecteur, ligne, code="DATE_FUTURE", champ_cible="Date de naissance",
                valeur_origine=naissance.strftime("%d/%m/%Y"), valeur_retenue=naissance.strftime("%d/%m/%Y"),
                message="Date de naissance postérieure à la date du jour ; valeur conservée pour vérification.",
            )
        if naissance.year < ANNEE_MINIMUM_DATE:
            _log(
                collecteur, ligne, code="DATE_ABERRANTE", champ_cible="Date de naissance",
                valeur_origine=naissance.strftime("%d/%m/%Y"), valeur_retenue=naissance.strftime("%d/%m/%Y"),
                message=f"Date de naissance antérieure à {ANNEE_MINIMUM_DATE} ; valeur conservée pour vérification.",
            )

    if adherent is not None and date_adherent is not None:
        age_adherent = _age_en_annees(date_adherent, date_reference)
        if age_adherent < AGE_MINIMUM_ADHERENT:
            _log(
                collecteur, adherent, code="AGE_ADHERENT_SUSPECT", champ_cible="Date de naissance",
                valeur_origine=date_adherent.strftime("%d/%m/%Y"), valeur_retenue=date_adherent.strftime("%d/%m/%Y"),
                message=f"Adhérent âgé de {age_adherent} ans (< {AGE_MINIMUM_ADHERENT} ans) ; valeur conservée pour vérification.",
            )
        for ligne in lignes_famille:
            if ligne[F_LIEN] != LIEN_ENFANT or ligne[F_DATE_NAISSANCE] is None:
                continue
            if ligne[F_DATE_NAISSANCE] <= date_adherent:
                _log(
                    collecteur, ligne, code="FILIATION_IMPOSSIBLE", champ_cible="Date de naissance",
                    valeur_origine=ligne[F_DATE_NAISSANCE].strftime("%d/%m/%Y"),
                    valeur_retenue=ligne[F_DATE_NAISSANCE].strftime("%d/%m/%Y"),
                    message="Enfant né avant ou en même temps que l'adhérent ; valeur conservée pour vérification.",
                )


def _age_en_annees(naissance: date, reference: date) -> int:
    age = reference.year - naissance.year
    if (reference.month, reference.day) < (naissance.month, naissance.day):
        age -= 1
    return age


def calculer_rangs(lignes: list[dict], collecteur: CollecteurAnomalies, date_reference: date | None = None) -> None:
    """Point d'entrée principal : regroupe `lignes` par famille (fichier +
    onglet + N° Famille) et détermine le rang de chaque personne — calculé
    pour le V0 (§4), conservé tel quel pour le V1 (décision métier). Modifie
    `lignes` en place (champ F_RANG) et journalise les anomalies via
    `collecteur`. Les groupes sont traités dans un ordre stable pour que le
    résultat soit reproductible d'une exécution à l'autre.
    """
    date_reference = date_reference or date.today()

    groupes: dict[tuple, list[dict]] = defaultdict(list)
    for ligne in lignes:
        cle = (ligne[F_FICHIER_SOURCE], ligne[F_ONGLET_SOURCE], ligne[F_NUM_FAMILLE])
        groupes[cle].append(ligne)

    for cle in sorted(groupes.keys()):
        lignes_famille = groupes[cle]
        if lignes_famille[0].get(F_VERSION_SOURCE) == VERSION_V1:
            _traiter_famille_v1(lignes_famille, collecteur)
        else:
            _traiter_famille_v0(lignes_famille, collecteur)
        _verifier_dates_famille(lignes_famille, collecteur, date_reference)


_CHAMPS_RANG0_UNIQUEMENT = [
    (F_RIB, "RIB"),
    (F_CIN, "Identité gouvernementale"),
]


def finaliser_champs_rang0(lignes: list[dict], collecteur: CollecteurAnomalies) -> None:
    """Garantit la règle du format cible : RIB, Date d'affiliation et
    Identité gouvernementale ne sont renseignés que sur la ligne de rang 0
    (§1). Toute valeur résiduelle sur une ligne de rang ≠ 0 (ex. adhérent
    surnuméraire requalifié par ADHERENT_MULTIPLE) est vidée et journalisée
    en CHAMP_NON_REPRIS plutôt que silencieusement perdue."""
    champs = _CHAMPS_RANG0_UNIQUEMENT + [(F_DATE_AFFILIATION, "Date d'affiliation")]
    for ligne in lignes:
        if ligne[F_RANG] == 0:
            continue
        for champ, libelle in champs:
            valeur = ligne.get(champ)
            if valeur is None or (isinstance(valeur, str) and valeur == ""):
                continue
            valeur_affichee = valeur.strftime("%d/%m/%Y") if hasattr(valeur, "strftime") else valeur
            _log(
                collecteur, ligne, code="CHAMP_NON_REPRIS", champ_cible=libelle,
                valeur_origine=valeur_affichee, valeur_retenue=None,
                message=f"{libelle} n'est repris que sur la ligne de rang 0 ; valeur non exportée pour cette ligne de rang {ligne[F_RANG]}.",
            )
            ligne[champ] = None if champ == F_DATE_AFFILIATION else ""


def verifier_num_famille_unique(lignes: list[dict], collecteur: CollecteurAnomalies) -> None:
    """COLLISION_NUM_FAMILLE (§5.7) : un même N° Famille ne doit apparaître
    que dans un seul (fichier source, onglet source) sur l'ensemble du lot
    consolidé."""
    sources_par_famille: dict[str, set[tuple]] = defaultdict(set)
    for ligne in lignes:
        sources_par_famille[ligne[F_NUM_FAMILLE]].add((ligne[F_FICHIER_SOURCE], ligne[F_ONGLET_SOURCE]))

    for num_famille, sources in sources_par_famille.items():
        if len(sources) > 1:
            for ligne in lignes:
                if ligne[F_NUM_FAMILLE] == num_famille:
                    _log(
                        collecteur, ligne, code="COLLISION_NUM_FAMILLE", champ_cible="N° Famille",
                        valeur_origine=num_famille, valeur_retenue=num_famille,
                        message=f"N° Famille {num_famille} présent dans plusieurs fichiers/onglets sources : {sorted(sources)}.",
                    )


def detecter_doublons_inter_source(lignes: list[dict], collecteur: CollecteurAnomalies) -> None:
    """DOUBLON_INTER_SOURCE (§5.7) : même RIB non vide rattaché à deux
    N° Famille différents sur l'ensemble du lot consolidé. Ne fusionne
    jamais automatiquement : signalement uniquement, décision humaine."""
    lignes_par_rib: dict[str, list[dict]] = defaultdict(list)
    for ligne in lignes:
        rib = ligne.get(F_RIB)
        if rib:
            lignes_par_rib[rib].append(ligne)

    for rib, groupe in lignes_par_rib.items():
        familles = {l[F_NUM_FAMILLE] for l in groupe}
        if len(familles) > 1:
            for ligne in groupe:
                _log(
                    collecteur, ligne, code="DOUBLON_INTER_SOURCE", champ_cible="RIB",
                    valeur_origine=rib, valeur_retenue=rib,
                    message=f"RIB {rib} présent sur plusieurs N° Famille : {sorted(familles)} ; migration de contrat probable, aucune fusion automatique.",
                )
