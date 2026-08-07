from core.anomalies import formater_valeur_origine


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
