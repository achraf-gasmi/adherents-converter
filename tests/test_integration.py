"""Test d'intégration volumétrique sur le corpus réel (§8). Convertit
l'ensemble des fichiers de data/samples et vérifie les invariants du
consolidé. Ignoré automatiquement si le dossier est vide (les fichiers
sources ne sont pas nécessairement livrés avec le dépôt)."""
import time
from datetime import date
from pathlib import Path

import pytest

from core.anomalies import CollecteurAnomalies
from core.convert_v0 import convertir_v0
from core.convert_v1 import convertir_v1
from core.detection import VERSION_V0, VERSION_V1, detecter_classeur, lire_lignes_donnees
from core.mapping import (
    F_CIN, F_DATE_AFFILIATION, F_FICHIER_SOURCE, F_LIEN, F_NUM_FAMILLE,
    F_ONGLET_SOURCE, F_RANG, F_RIB, LIEN_CONJOINT,
)
from core.ranking import (
    calculer_rangs, detecter_doublons_inter_source, finaliser_champs_rang0,
    verifier_num_famille_unique,
)

SAMPLES = Path(__file__).resolve().parents[1] / "data" / "samples"

pytestmark = pytest.mark.skipif(
    not SAMPLES.exists() or not any(SAMPLES.glob("*.xlsx")),
    reason="data/samples est vide : test d'intégration volumétrique ignoré.",
)


@pytest.fixture(scope="module")
def resultat_corpus():
    collecteur = CollecteurAnomalies()
    toutes_lignes: list[dict] = []
    debut = time.time()

    for fichier in sorted(SAMPLES.glob("*.xlsx")):
        contenu = fichier.read_bytes()
        for detection in detecter_classeur(contenu, fichier.name):
            if detection.erreur or detection.version not in (VERSION_V0, VERSION_V1):
                continue
            lignes_source = lire_lignes_donnees(contenu, detection.nom_onglet)
            if detection.version == VERSION_V0:
                lignes = convertir_v0(lignes_source, detection.en_tetes_bruts, fichier.name, detection.nom_onglet, collecteur)
            else:
                lignes = convertir_v1(lignes_source, detection.en_tetes_bruts, fichier.name, detection.nom_onglet, collecteur)
            toutes_lignes.extend(lignes)

    calculer_rangs(toutes_lignes, collecteur, date_reference=date(2026, 8, 7))
    finaliser_champs_rang0(toutes_lignes, collecteur)
    verifier_num_famille_unique(toutes_lignes, collecteur)
    detecter_doublons_inter_source(toutes_lignes, collecteur)

    duree = time.time() - debut
    return toutes_lignes, collecteur, duree


def test_performance_moins_de_60_secondes(resultat_corpus):
    _, _, duree = resultat_corpus
    assert duree < 60


def test_num_famille_uniques_entre_fichiers(resultat_corpus):
    lignes, collecteur, _ = resultat_corpus
    assert not any(a.code == "COLLISION_NUM_FAMILLE" for a in collecteur.anomalies)


def test_rangs_dupliques_toujours_flagues(resultat_corpus):
    # Depuis la décision métier de ne plus corriger le rang source (V1), des
    # doublons de rang peuvent exister dans l'export : ils doivent toujours
    # être journalisés en RANG_DUPLIQUE, jamais silencieusement laissés tels
    # quels sans trace.
    lignes, collecteur, _ = resultat_corpus
    par_famille: dict[tuple, list[dict]] = {}
    for l in lignes:
        cle = (l[F_FICHIER_SOURCE], l[F_ONGLET_SOURCE], l[F_NUM_FAMILLE])
        if l[F_RANG] is not None:
            par_famille.setdefault(cle, []).append(l)
    familles_avec_doublon = 0
    for membres in par_famille.values():
        rangs = [m[F_RANG] for m in membres]
        if len(rangs) != len(set(rangs)):
            familles_avec_doublon += 1
    nb_anomalies_doublon = sum(1 for a in collecteur.anomalies if a.code == "RANG_DUPLIQUE")
    assert (familles_avec_doublon > 0) == (nb_anomalies_doublon > 0)


def test_rang_1_non_conjoint_toujours_flague(resultat_corpus):
    # Le rang source n'est plus corrigé : un rang 1 porté par une ligne qui
    # n'est pas le conjoint peut désormais apparaître dans l'export, mais
    # doit alors être signalé en RANG_INCOHERENT.
    lignes, collecteur, _ = resultat_corpus
    lignes_rang1_incoherentes = [l for l in lignes if l[F_RANG] == 1 and l[F_LIEN] != LIEN_CONJOINT]
    nb_anomalies = sum(1 for a in collecteur.anomalies if a.code == "RANG_INCOHERENT")
    if lignes_rang1_incoherentes:
        assert nb_anomalies > 0


def test_champs_rang0_uniquement(resultat_corpus):
    lignes, _, _ = resultat_corpus
    for l in lignes:
        if l[F_RANG] != 0:
            assert l[F_RIB] == ""
            assert l[F_CIN] == ""
            assert l[F_DATE_AFFILIATION] is None


def test_volume_total_stable_entre_deux_executions(resultat_corpus):
    lignes, _, _ = resultat_corpus
    assert len(lignes) == 19534


def test_aucune_donnee_image_dans_les_lignes(resultat_corpus):
    lignes, _, _ = resultat_corpus
    for l in lignes:
        for valeur in l.values():
            if isinstance(valeur, str):
                assert "base64" not in valeur.lower()
