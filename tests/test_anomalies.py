import pandas as pd
import pytest

from core.anomalies import COLONNES_ANOMALIES, CollecteurAnomalies, formater_valeur_origine


def test_espace_insecable_rendu_visible():
    valeur = f"9{chr(0x00A0)}292{chr(0x00A0)}762"
    resultat = formater_valeur_origine(valeur)
    assert chr(0x00A0) not in resultat
    assert "·" in resultat


def test_valeurs_ambigues_explicites():
    assert formater_valeur_origine(None) == "[vide]"
    assert formater_valeur_origine("") == "[vide]"
    assert formater_valeur_origine("   ") == "[vide]"
    assert formater_valeur_origine(False) == "[False]"
    assert formater_valeur_origine(True) == "[True]"


def test_valeur_normale_inchangee():
    assert formater_valeur_origine("05705239") == "05705239"


def test_vers_ligne_valeur_retenue_toujours_str_ou_vide():
    # Certaines anomalies (ex. RANG_INCOHERENT, RANG_DUPLIQUE) transportent
    # un entier en valeur_retenue (le rang). La colonne "Valeur retenue" doit
    # rester d'un type homogène (str) quel que soit le code, sous peine de
    # faire planter la sérialisation Arrow de Streamlit (colonne "object"
    # mêlant str et int).
    collecteur = CollecteurAnomalies()
    collecteur.ajouter(
        fichier_source="A.xlsx", onglet_source="Sheet1", ligne_source=2,
        code="RANG_INCOHERENT", num_famille="F1", nom="X",
        valeur_origine=5, valeur_retenue=5,
    )
    collecteur.ajouter(
        fichier_source="A.xlsx", onglet_source="Sheet1", ligne_source=3,
        code="CIN_COMPLETE", num_famille="F2", nom="Y",
        valeur_origine="1234567", valeur_retenue="01234567",
    )
    collecteur.ajouter(
        fichier_source="A.xlsx", onglet_source="Sheet1", ligne_source=4,
        code="CHAMP_NON_REPRIS", num_famille="F3", nom="Z",
        valeur_origine="x", valeur_retenue=None,
    )

    for anomalie in collecteur.anomalies:
        ligne = anomalie.vers_ligne()
        valeur_retenue = ligne[COLONNES_ANOMALIES.index("Valeur retenue")]
        assert isinstance(valeur_retenue, str)


def test_dataframe_anomalies_mixtes_serialisable_par_pyarrow():
    # Reproduit exactement ce que fait Streamlit (st.dataframe) : convertir
    # la liste d'anomalies en DataFrame puis en table Arrow. Un rang (int)
    # mélangé à des valeurs texte dans "Valeur retenue" faisait planter cette
    # conversion avant correction.
    pyarrow = pytest.importorskip("pyarrow")

    collecteur = CollecteurAnomalies()
    collecteur.ajouter(
        fichier_source="A.xlsx", onglet_source="Sheet1", ligne_source=2,
        code="RANG_DUPLIQUE", num_famille="F1", nom="X",
        valeur_origine=2, valeur_retenue=2,
    )
    collecteur.ajouter(
        fichier_source="A.xlsx", onglet_source="Sheet1", ligne_source=3,
        code="CIN_COMPLETE", num_famille="F2", nom="Y",
        valeur_origine="1234567", valeur_retenue="01234567",
    )

    df = pd.DataFrame([a.vers_ligne() for a in collecteur.anomalies], columns=COLONNES_ANOMALIES)
    pyarrow.Table.from_pandas(df)  # ne doit lever aucune exception
