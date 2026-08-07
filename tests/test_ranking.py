from datetime import date

from core.anomalies import CollecteurAnomalies
from core.mapping import (
    F_CIN, F_CLIENT, F_COLONNE_SOURCE, F_DATE_AFFILIATION, F_DATE_NAISSANCE,
    F_FICHIER_SOURCE, F_GENDRE, F_INDEX_SOURCE, F_LIEN, F_LIGNE_SOURCE,
    F_NOM, F_NUM_FAMILLE, F_ONGLET_SOURCE, F_RANG, F_RANG_SOURCE, F_RIB,
    LIEN_ADHERENT, LIEN_CONJOINT, LIEN_ENFANT,
)
from core.ranking import calculer_rangs


def _ligne(lien, nom, naissance, num_famille="F1", index_source=0, fichier="X.xlsx", onglet="Feuille1"):
    return {
        F_FICHIER_SOURCE: fichier, F_ONGLET_SOURCE: onglet, F_LIGNE_SOURCE: 2,
        F_COLONNE_SOURCE: "", F_INDEX_SOURCE: index_source, F_RANG_SOURCE: None,
        F_CLIENT: "CLIENT", F_NUM_FAMILLE: num_famille, F_LIEN: lien, F_GENDRE: "",
        F_NOM: nom, F_DATE_NAISSANCE: naissance, F_DATE_AFFILIATION: None,
        F_RANG: None, F_RIB: "", F_CIN: "",
    }


def test_tri_enfants_par_date():
    lignes = [
        _ligne(LIEN_ADHERENT, "PERE", date(1980, 1, 1)),
        _ligne(LIEN_CONJOINT, "MERE", date(1982, 1, 1)),
        _ligne(LIEN_ENFANT, "ENFANT_2006", date(2006, 1, 1), index_source=1),
        _ligne(LIEN_ENFANT, "ENFANT_2007", date(2007, 1, 1), index_source=2),
        _ligne(LIEN_ENFANT, "ENFANT_2002", date(2002, 1, 1), index_source=3),
    ]
    collecteur = CollecteurAnomalies()
    calculer_rangs(lignes, collecteur, date_reference=date(2026, 1, 1))

    par_nom = {l[F_NOM]: l[F_RANG] for l in lignes}
    assert par_nom["ENFANT_2006"] == 3
    assert par_nom["ENFANT_2007"] == 4
    assert par_nom["ENFANT_2002"] == 2


def test_famille_sans_conjoint_rang1_inutilise():
    lignes = [
        _ligne(LIEN_ADHERENT, "PERE", date(1980, 1, 1)),
        _ligne(LIEN_ENFANT, "AINE", date(2005, 1, 1), index_source=1),
        _ligne(LIEN_ENFANT, "CADET", date(2008, 1, 1), index_source=2),
    ]
    collecteur = CollecteurAnomalies()
    calculer_rangs(lignes, collecteur, date_reference=date(2026, 1, 1))

    rangs = sorted(l[F_RANG] for l in lignes)
    assert rangs == [0, 2, 3]


def test_jumeaux_departages_de_facon_deterministe():
    def construire():
        return [
            _ligne(LIEN_ADHERENT, "DUPONT PARENT", date(1969, 1, 31)),
            _ligne(LIEN_ENFANT, "DUPONT ENFANT UN", date(2011, 3, 6), index_source=1),
            _ligne(LIEN_ENFANT, "DUPONT ENFANT DEUX", date(2011, 3, 6), index_source=2),
        ]

    lignes_1 = construire()
    calculer_rangs(lignes_1, CollecteurAnomalies(), date_reference=date(2026, 1, 1))
    lignes_2 = construire()
    calculer_rangs(lignes_2, CollecteurAnomalies(), date_reference=date(2026, 1, 1))

    rangs_1 = {l[F_NOM]: l[F_RANG] for l in lignes_1}
    rangs_2 = {l[F_NOM]: l[F_RANG] for l in lignes_2}
    assert rangs_1 == rangs_2
    # On vérifie la reproductibilité et l'unicité des rangs ; le tri exact
    # entre les deux enfants (par nom) est un détail d'implémentation.
    assert sorted(rangs_1.values()) == [0, 2, 3]


def test_jumeaux_genere_anomalie_information():
    lignes = [
        _ligne(LIEN_ADHERENT, "PERE", date(1980, 1, 1)),
        _ligne(LIEN_ENFANT, "A", date(2010, 6, 1), index_source=1),
        _ligne(LIEN_ENFANT, "B", date(2010, 6, 1), index_source=2),
    ]
    collecteur = CollecteurAnomalies()
    calculer_rangs(lignes, collecteur, date_reference=date(2026, 1, 1))
    codes = [a.code for a in collecteur.anomalies]
    assert codes.count("JUMEAUX_DEPARTAGES") == 2


def test_famille_sans_adherent():
    lignes = [
        _ligne(LIEN_CONJOINT, "SEUL", date(1980, 1, 1)),
    ]
    collecteur = CollecteurAnomalies()
    calculer_rangs(lignes, collecteur, date_reference=date(2026, 1, 1))
    assert any(a.code == "FAMILLE_SANS_ADHERENT" for a in collecteur.anomalies)


def test_conjoint_toujours_rang_1_meme_sans_adherent_multiple():
    lignes = [
        _ligne(LIEN_ADHERENT, "PERE", date(1980, 1, 1)),
        _ligne(LIEN_ADHERENT, "AUTRE_ADHERENT", date(1981, 1, 1), index_source=1),
        _ligne(LIEN_CONJOINT, "MERE", date(1982, 1, 1), index_source=2),
    ]
    collecteur = CollecteurAnomalies()
    calculer_rangs(lignes, collecteur, date_reference=date(2026, 1, 1))
    par_nom = {l[F_NOM]: l[F_RANG] for l in lignes}
    assert par_nom["PERE"] == 0
    assert par_nom["MERE"] == 1
    assert par_nom["AUTRE_ADHERENT"] not in (0, 1)
    assert any(a.code == "ADHERENT_MULTIPLE" for a in collecteur.anomalies)


def test_filiation_impossible():
    lignes = [
        _ligne(LIEN_ADHERENT, "ADHERENT TROP JEUNE", date(2016, 1, 1)),
        _ligne(LIEN_ENFANT, "ENFANT_2003", date(2003, 1, 1), index_source=1),
    ]
    collecteur = CollecteurAnomalies()
    calculer_rangs(lignes, collecteur, date_reference=date(2026, 1, 1))
    assert any(a.code == "FILIATION_IMPOSSIBLE" for a in collecteur.anomalies)


def test_age_adherent_suspect():
    lignes = [_ligne(LIEN_ADHERENT, "TROP_JEUNE", date(2020, 1, 1))]
    collecteur = CollecteurAnomalies()
    calculer_rangs(lignes, collecteur, date_reference=date(2026, 1, 1))
    assert any(a.code == "AGE_ADHERENT_SUSPECT" for a in collecteur.anomalies)


def test_date_future():
    lignes = [
        _ligne(LIEN_ADHERENT, "PERE", date(1980, 1, 1)),
        _ligne(LIEN_CONJOINT, "FUTUR", date(2028, 6, 28), index_source=1),
    ]
    collecteur = CollecteurAnomalies()
    calculer_rangs(lignes, collecteur, date_reference=date(2026, 1, 1))
    assert any(a.code == "DATE_FUTURE" for a in collecteur.anomalies)
