"""The course's LSTM (mestrado_emg.lstm_gestos): windows and splits as in its notebook,
and a short training where PyTorch exists (the mestrado-lstm image)."""

import numpy as np
import pandas as pd
import pytest

from mestrado_emg.lstm_gestos import Hiper, dividir, janelas, pasta


def _gestos_csv(path, pessoas=(1, 2), gestos=(0, 1), n=450, canais=2, seed=0):
    """The layout of scripts/fetch_gesture_data.sh, one block per recording."""
    rng = np.random.default_rng(seed)
    blocos = []
    for p in pessoas:
        for g in gestos:
            bloco = {"time": np.arange(n) / 1000}
            for c in range(1, canais + 1):
                bloco[f"channel{c}"] = rng.normal(scale=1 + 3 * g, size=n)
            bloco["participante"] = p
            bloco["position"] = f"gesto_{g}"
            blocos.append(pd.DataFrame(bloco))
    pd.concat(blocos).to_csv(path, index=False)
    return path


def test_windows_are_cut_and_smoothed_like_the_notebook(tmp_path):
    csv = _gestos_csv(tmp_path / "g.csv")
    X, y, grupo = janelas(csv)
    assert X.shape == (8, 200, 2)  # 450 samples: 2 windows of 200 per recording
    assert y.tolist() == [0, 0, 1, 1] * 2
    assert grupo.tolist() == [1] * 4 + [2] * 4
    primeira = np.abs(pd.read_csv(csv)[["channel1", "channel2"]].to_numpy()[:200])
    media = np.convolve(primeira[:, 0], np.ones(20) / 20, mode="same")
    np.testing.assert_allclose(X[0][:, 0], media)
    np.testing.assert_allclose(X[0][:, 1], primeira[:, 1])  # the notebook skips the last channel


def test_the_notebook_split_overlaps_and_the_honest_ones_do_not():
    grupo = np.repeat([1, 2, 3, 4], 250)
    rng = np.random.default_rng(0)
    ((_, treino, teste),) = dividir("notebook", grupo, rng)
    assert (len(treino), len(teste)) == (800, 200)
    assert 0.7 < np.isin(teste, treino).mean() < 0.9  # ~80 %, as in the course
    ((_, treino, teste),) = dividir("sorteio", grupo, rng)
    assert not np.isin(teste, treino).any() and len(treino) + len(teste) == 1000
    folds = list(dividir("participante", grupo, rng))
    assert [nome for nome, *_ in folds] == ["1", "2", "3", "4"]
    for nome, treino, teste in folds:
        assert set(grupo[teste]) == {int(nome)} and int(nome) not in set(grupo[treino])
        assert len(treino) + len(teste) == 1000
    assert pasta("data/gestos_1khz.csv") == "gestos-1khz_lstm"
    assert pasta("gestos_1khz.csv", 20) == "gestos-1khz_lstm-e20"


def test_a_short_training_runs_end_to_end(tmp_path):
    pytest.importorskip("torch", reason="PyTorch is only in the mestrado-lstm image")
    from mestrado_emg.lstm_gestos import figuras, resumo_md, rodar

    csv = _gestos_csv(tmp_path / "g.csv", pessoas=(1, 2, 3), n=1000, canais=4)
    rel = rodar(csv, Hiper(epocas=3, lote=16), repeticoes=1, processos=2)
    assert set(rel["resumo"]) == {"notebook", "sorteio", "participante"}
    assert rel["resumo"]["sorteio"]["sobreposicao"] == 0
    assert list(rel["resumo"]["participante"]["por_participante"]) == ["1", "2", "3"]
    assert len(rel["treinos"]) == 5  # notebook, sorteio and one per participant
    figuras(rel, tmp_path)
    assert (tmp_path / "acuracia.png").exists() and (tmp_path / "confusao.png").exists()
    assert "participante novo" in resumo_md(rel)
