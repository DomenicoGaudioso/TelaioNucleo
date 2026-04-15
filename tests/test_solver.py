import pandas as pd
from src import ensure_sheets, solve_linear_static_frame_core_mesh


def test_minimal_frame_plus_one_shell_runs():
    # Minimal: one beam + one shell quad (flat) sharing no nodes.
    sheets = ensure_sheets({
        "nodes": pd.DataFrame([
            {"id": 1, "x": 0.0, "y": 0.0, "z": 0.0},
            {"id": 2, "x": 1.0, "y": 0.0, "z": 0.0},
            {"id": 10, "x": 0.0, "y": 0.0, "z": 0.0},
            {"id": 11, "x": 0.0, "y": 1.0, "z": 0.0},
            {"id": 12, "x": 1.0, "y": 1.0, "z": 0.0},
            {"id": 13, "x": 1.0, "y": 0.0, "z": 0.0},
        ]),
        "beam_elements": pd.DataFrame([
            {"id": 1, "n1": 1, "n2": 2, "prop": 1},
        ]),
        "beam_properties": pd.DataFrame([
            {"id": 1, "name": "beam", "A": 0.01, "E": 210000.0, "G": 80000.0, "J": 1e-6, "Iy": 2e-6, "Iz": 1e-6},
        ]),
        "shell_elements": pd.DataFrame([
            {"id": 100, "n1": 10, "n2": 11, "n3": 12, "n4": 13, "sec": 1},
        ]),
        "shell_sections": pd.DataFrame([
            {"id": 1, "name": "rcwall", "E": 30000.0, "nu": 0.2, "h": 0.2, "rho": 2500.0},
        ]),
        "load_cases": pd.DataFrame([
            {"id": 1, "name": "LC1"},
        ]),
        "restraints": pd.DataFrame([
            {"load_case_id": 1, "node_id": 1, "ux": True, "uy": True, "uz": True, "rx": True, "ry": True, "rz": True},
            {"load_case_id": 1, "node_id": 10, "ux": True, "uy": True, "uz": True, "rx": True, "ry": True, "rz": True},
            {"load_case_id": 1, "node_id": 11, "ux": True, "uy": True, "uz": True, "rx": True, "ry": True, "rz": True},
            {"load_case_id": 1, "node_id": 13, "ux": True, "uy": True, "uz": True, "rx": True, "ry": True, "rz": True},
        ]),
        "node_loads": pd.DataFrame([
            {"load_case_id": 1, "node_id": 2, "fx": 0.0, "fy": -10.0, "fz": 0.0, "mx": 0.0, "my": 0.0, "mz": 0.0},
            {"load_case_id": 1, "node_id": 12, "fx": 0.0, "fy": -1.0, "fz": 0.0, "mx": 0.0, "my": 0.0, "mz": 0.0},
        ]),
        "beam_dist_loads": pd.DataFrame(),
        "masses": pd.DataFrame(),
    })

    res = solve_linear_static_frame_core_mesh(sheets, 1)
    assert "results_nodal" in res
    nod = res["results_nodal"].set_index("node_id")
    assert nod.loc[2, "uy"] < 0.0
