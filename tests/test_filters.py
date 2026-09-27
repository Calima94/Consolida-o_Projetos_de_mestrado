"""Sampling rate and IIR filters: the other fields of the thesis training screen."""

import argparse
import json

import numpy as np
import pytest

from mestrado_emg.features import (
    IDENTITY_SOS,
    LEGACY_SOS_BANDSTOP,
    LEGACY_SOS_HIGHPASS,
    LegacyFeatureConfig,
    add_pipeline_args,
    config_from_args,
    count_channels,
    design_filters,
    extract_features,
    filter_report,
    load_sos,
)


def _rows(sos):
    return "[" + ",".join("[" + ", ".join(repr(x) for x in row) + "]" for row in sos) + ",]"


def test_reads_the_thesis_app_filter_files(tmp_path):
    """Same layout as Train_Myo_Signals/Parameters/sos_*_filter.csv, trailing comma included."""
    arquivo = tmp_path / "sos_bandstop_filter.csv"
    arquivo.write_text(
        'Filter,Value,Description,\nsos_bandstop_,"' + _rows(LEGACY_SOS_BANDSTOP.tolist())
        + '",,55 hz bandstop\n'
    )  # fmt: skip
    np.testing.assert_allclose(load_sos(arquivo), LEGACY_SOS_BANDSTOP)


def test_reads_plain_json_and_npy(tmp_path):
    (tmp_path / "hp.txt").write_text(
        "\n".join(" ".join(map(str, row)) for row in LEGACY_SOS_HIGHPASS.tolist())
    )
    (tmp_path / "hp.json").write_text(json.dumps(LEGACY_SOS_HIGHPASS.tolist()))
    np.save(tmp_path / "hp.npy", LEGACY_SOS_HIGHPASS)
    for nome in ("hp.txt", "hp.json", "hp.npy"):
        np.testing.assert_allclose(load_sos(tmp_path / nome), LEGACY_SOS_HIGHPASS)


@pytest.mark.parametrize(
    "linhas, erro",
    [
        ([[1, 0, 0, 1, -2.5, 1.5]], "unstable"),
        ([[1, 0, 0, 1, 0]], "rows of 6"),
        ([[1, 0, 0, 0, 0, 0]], "a0 = 0"),
    ],
)
def test_bad_filters_are_refused(tmp_path, linhas, erro):
    arquivo = tmp_path / "f.json"
    arquivo.write_text(json.dumps(linhas))
    with pytest.raises(ValueError, match=erro):
        load_sos(arquivo)


def test_thesis_filters_move_with_the_sampling_rate():
    """The thesis coefficients were designed for 200 Hz; used at 1 kHz they act elsewhere."""
    a200 = filter_report(LEGACY_SOS_HIGHPASS.tolist(), LEGACY_SOS_BANDSTOP.tolist(), 200.0)
    a1000 = filter_report(LEGACY_SOS_HIGHPASS.tolist(), LEGACY_SOS_BANDSTOP.tolist(), 1000.0)
    assert a200["highpass_hz"] == pytest.approx(14.3, abs=0.3)
    assert a200["bandstop_hz"] == pytest.approx(60, abs=1)
    assert a1000["highpass_hz"] == pytest.approx(71.4, abs=1)
    assert a1000["bandstop_hz"] == pytest.approx(300, abs=3)


def test_designed_filters_cut_where_asked():
    hp, bs = design_filters(1000.0, 20.0, 60.0)
    r = filter_report(hp, bs, 1000.0)
    assert r["highpass_hz"] == pytest.approx(20, abs=0.5)
    assert r["bandstop_hz"] == pytest.approx(60, abs=1)
    assert design_filters(1000.0, 20.0, 0.0)[1] == IDENTITY_SOS


def _args(*argv):
    p = argparse.ArgumentParser()
    add_pipeline_args(p)
    return p.parse_args(list(argv))


def test_command_line_designed_filters(capsys):
    cfg = config_from_args(_args("--fs", "1000", "--filters", "design", "--window-ms", "200"), 4)
    assert (cfg.fs_hz, cfg.n_channels, cfg.samples_per_window) == (1000.0, 4, 200)
    assert cfg.filter_mode == "design" and cfg.tag() == "fs1000-c4-hp20-rf60-w200"
    assert "filtros projetados: passa-altas 20 Hz, rejeita-faixa 60 Hz" in capsys.readouterr().out


def test_command_line_filter_files(tmp_path, capsys):
    (tmp_path / "meu_passa_altas.json").write_text(json.dumps(LEGACY_SOS_HIGHPASS.tolist()))
    cfg = config_from_args(
        _args("--filters", "files", "--highpass-file", str(tmp_path / "meu_passa_altas.json"))
    )
    assert cfg.sos_bandstop == IDENTITY_SOS and cfg.tag() == "iir-meupassaalta-nenhum"
    assert "filtros dos arquivos meu_passa_altas.json e nenhum" in capsys.readouterr().out
    with pytest.raises(SystemExit, match="não consegui ler"):
        config_from_args(_args("--filters", "files", "--highpass-file", str(tmp_path / "x.csv")))


def test_thesis_filters_at_another_rate_warn(capsys):
    config_from_args(_args("--fs", "1000"), 4)
    saida = capsys.readouterr().out
    assert "corta em ~71 Hz" in saida and "use --filters design" in saida


def test_channels_come_from_the_recording(tmp_path):
    csv = tmp_path / "gestos.csv"
    csv.write_text("time,chanel1,chanel2,chanel3,chanel4,position\n0.0,1,2,3,4,0\n")
    assert count_channels(csv) == 4


def test_pipeline_runs_at_1khz_with_4_channels():
    cfg = LegacyFeatureConfig.for_sensor(fs_hz=1000.0, n_channels=4, window_ms=200.0)
    x = np.random.default_rng(3).normal(size=(1000, 4))
    assert extract_features(x, cfg).shape == (5, 4)


def test_old_bundles_keep_the_thesis_filters():
    antigo = LegacyFeatureConfig().to_dict()
    for chave in ("filter_mode", "highpass_hz", "mains_hz", "filter_files"):
        del antigo[chave]
    assert LegacyFeatureConfig.from_dict(antigo) == LegacyFeatureConfig()
