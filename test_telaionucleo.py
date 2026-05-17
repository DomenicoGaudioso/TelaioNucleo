"""
Test suite per TelaioNucleo — funzioni pure senza OpenSeesPy attivo.

Modello ibrido beam + shell (ShellMITC4): testa le funzioni pure di I/O,
validazione e geometria senza invocare il solver OpenSeesPy.
"""
import sys
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

# ─── Mock openseespy prima di qualsiasi import da src ───────────────────────
sys.modules.setdefault("openseespy", MagicMock())
sys.modules.setdefault("openseespy.opensees", MagicMock())
# ────────────────────────────────────────────────────────────────────────────

from src import (  # noqa: E402
    OPTIONAL_SHEETS,
    REQUIRED_SHEETS,
    _apply_trapezoid_segmented_uniform,
    _pick_vecxz_for_element,
    ensure_sheets,
    read_xlsx,
    results_to_sheets,
    validate_sheets,
    write_xlsx,
)


# ─── Fixture ────────────────────────────────────────────────────────────────

def _sheets_validi():
    """Set minimo di fogli corretto per TelaioNucleo (beam + shell)."""
    return {
        "nodes": pd.DataFrame([
            {"id": 1, "x": 0.0, "y": 0.0, "z": 0.0},
            {"id": 2, "x": 5.0, "y": 0.0, "z": 0.0},
            {"id": 10, "x": 0.0, "y": 0.0, "z": 0.0},
            {"id": 11, "x": 0.0, "y": 3.0, "z": 0.0},
            {"id": 12, "x": 3.0, "y": 3.0, "z": 0.0},
            {"id": 13, "x": 3.0, "y": 0.0, "z": 0.0},
        ]),
        "beam_elements": pd.DataFrame([
            {"id": 1, "n1": 1, "n2": 2, "prop": 1},
        ]),
        "beam_properties": pd.DataFrame([
            {"id": 1, "name": "IPE300", "A": 5.38e-3, "E": 210000.0,
             "G": 80769.0, "J": 2.14e-7, "Iy": 3.69e-5, "Iz": 1.34e-5},
        ]),
        "shell_elements": pd.DataFrame([
            {"id": 100, "n1": 10, "n2": 11, "n3": 12, "n4": 13, "sec": 1},
        ]),
        "shell_sections": pd.DataFrame([
            {"id": 1, "name": "nucleo_ca", "E": 30000.0, "nu": 0.2, "h": 0.3, "rho": 2500.0},
        ]),
        "load_cases": pd.DataFrame([{"id": 1, "name": "LC1"}]),
        "restraints": pd.DataFrame([{
            "load_case_id": 1, "node_id": 1,
            "ux": True, "uy": True, "uz": True,
            "rx": True, "ry": True, "rz": True,
        }]),
        "node_loads": pd.DataFrame([{
            "load_case_id": 1, "node_id": 2,
            "fx": 0.0, "fy": -10.0, "fz": 0.0,
            "mx": 0.0, "my": 0.0, "mz": 0.0,
        }]),
        "beam_dist_loads": pd.DataFrame(),
        "masses": pd.DataFrame(),
    }


# ─── Test 1: ensure_sheets — tutti i fogli richiesti presenti ───────────────

def test_ensure_sheets_fogli_richiesti_nucleo():
    s = ensure_sheets({})
    for sh in REQUIRED_SHEETS:
        assert sh in s, f"Foglio richiesto assente in TelaioNucleo: {sh}"


# ─── Test 2: ensure_sheets — fogli opzionali presenti ───────────────────────

def test_ensure_sheets_fogli_opzionali_nucleo():
    s = ensure_sheets({})
    for sh in OPTIONAL_SHEETS:
        assert sh in s, f"Foglio opzionale assente in TelaioNucleo: {sh}"


# ─── Test 3: validate_sheets — input beam+shell valido → nessun errore ──────

def test_validate_sheets_beam_shell_valido():
    errs = validate_sheets(ensure_sheets(_sheets_validi()))
    assert errs == [], f"Errori inattesi con input valido: {errs}"


# ─── Test 4: validate_sheets — colonna n4 mancante in shell_elements ─────────

def test_validate_sheets_shell_elements_senza_n4():
    sheets = _sheets_validi()
    sheets["shell_elements"] = pd.DataFrame([
        {"id": 100, "n1": 10, "n2": 11, "n3": 12, "sec": 1}
    ])
    errs = validate_sheets(ensure_sheets(sheets))
    assert any("shell_elements" in e and "n4" in e for e in errs), \
        f"Colonna n4 mancante non rilevata: {errs}"


# ─── Test 5: validate_sheets — colonna Iz mancante in beam_properties ────────

def test_validate_sheets_beam_properties_senza_iz():
    sheets = _sheets_validi()
    sheets["beam_properties"] = pd.DataFrame([
        {"id": 1, "name": "IPE300", "A": 5.38e-3, "E": 210000.0,
         "G": 80769.0, "J": 2.14e-7, "Iy": 3.69e-5}
    ])
    errs = validate_sheets(ensure_sheets(sheets))
    assert any("beam_properties" in e and "Iz" in e for e in errs), \
        f"Colonna Iz mancante non rilevata: {errs}"


# ─── Test 6: validate_sheets — colonna nu mancante in shell_sections ─────────

def test_validate_sheets_shell_sections_senza_nu():
    sheets = _sheets_validi()
    sheets["shell_sections"] = pd.DataFrame([
        {"id": 1, "name": "nucleo", "E": 30000.0, "h": 0.3, "rho": 2500.0}
    ])
    errs = validate_sheets(ensure_sheets(sheets))
    assert any("shell_sections" in e and "nu" in e for e in errs), \
        f"Colonna nu mancante non rilevata: {errs}"


# ─── Test 7: _pick_vecxz_for_element — trave orizzontale → vecxz = [0, 0, 1] ─

def test_pick_vecxz_trave_orizzontale():
    result = _pick_vecxz_for_element((0.0, 0.0, 0.0), (5.0, 0.0, 0.0))
    assert result == [0.0, 0.0, 1.0], \
        f"Trave orizzontale: atteso [0,0,1], ottenuto {result}"


# ─── Test 8: _pick_vecxz_for_element — colonna verticale → vecxz = [0, 1, 0] ─

def test_pick_vecxz_colonna_verticale():
    result = _pick_vecxz_for_element((0.0, 0.0, 0.0), (0.0, 0.0, 4.0))
    assert result == [0.0, 1.0, 0.0], \
        f"Colonna verticale: atteso [0,1,0], ottenuto {result}"


# ─── Test 9: write_xlsx / read_xlsx — roundtrip conserva beam e shell ────────

def test_roundtrip_xlsx_beam_shell():
    sheets = ensure_sheets(_sheets_validi())
    raw = write_xlsx(sheets)
    assert isinstance(raw, bytes) and len(raw) > 0, \
        "write_xlsx deve produrre bytes non vuoti"
    recovered = ensure_sheets(read_xlsx(raw))
    assert not recovered["nodes"].empty, "Nodi devono essere recuperati"
    assert len(recovered["nodes"]) == 6, "Numero nodi deve corrispondere"
    assert not recovered["shell_sections"].empty, "shell_sections deve essere recuperato"
    assert float(recovered["shell_sections"].iloc[0]["nu"]) == pytest.approx(0.2)


# ─── Test 10: results_to_sheets — merge beam + shell + nodal ─────────────────

def test_results_to_sheets_merge_beam_shell():
    base = ensure_sheets(_sheets_validi())
    results = {
        "results_nodal": pd.DataFrame([{"node_id": 1, "ux": 0.0}]),
        "results_beam_localForce": pd.DataFrame([{"id": 1, "Fx_i": 0.0, "Fx_j": 0.0}]),
        "results_shell_forces": pd.DataFrame([{"id": 100, "forces": "0.0 0.0"}]),
    }
    merged = results_to_sheets(base, results)
    assert "results_nodal" in merged
    assert "results_beam_localForce" in merged
    assert "results_shell_forces" in merged
    assert "nodes" in merged


# ─── Test 11: _apply_trapezoid_segmented_uniform — nseg chiamate a eleLoad ───

def test_apply_trapezoid_nucleo_nseg():
    with patch("src.ops") as mock_ops:
        _apply_trapezoid_segmented_uniform(
            eleTag=1,
            qx0=0.0, qx1=0.0,
            qy0=-5.0, qy1=-7.0,
            qz0=0.0, qz1=0.0,
            nseg=3,
        )
        assert mock_ops.eleLoad.call_count == 3, \
            f"Attese 3 chiamate a eleLoad, ottenute {mock_ops.eleLoad.call_count}"


# ─── Test 12: validate_sheets — fogli vuoti non generano errori ──────────────

def test_validate_sheets_fogli_vuoti_nucleo():
    errs = validate_sheets(ensure_sheets({}))
    assert errs == [], f"Fogli vuoti non devono generare errori: {errs}"
