# src.py
from __future__ import annotations

from io import BytesIO
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd
import openseespy.opensees as ops

# =========================================================
# XLSX I/O
# =========================================================
REQUIRED_SHEETS = [
    "nodes",
    "beam_elements",
    "beam_properties",
    "shell_elements",
    "shell_sections",
    "load_cases",
    "restraints",
    "node_loads",
]
OPTIONAL_SHEETS = [
    "beam_dist_loads",
    "masses",
]


def read_xlsx(file_bytes: bytes) -> Dict[str, pd.DataFrame]:
    bio = BytesIO(file_bytes)
    xls = pd.ExcelFile(bio, engine="openpyxl")
    data: Dict[str, pd.DataFrame] = {}
    for sh in xls.sheet_names:
        df = pd.read_excel(xls, sheet_name=sh, engine="openpyxl")
        df.columns = [str(c).strip() for c in df.columns]
        data[sh.strip().lower()] = df
    return data


def write_xlsx(sheets: Dict[str, pd.DataFrame]) -> bytes:
    bio = BytesIO()
    with pd.ExcelWriter(bio, engine="openpyxl") as w:
        for name, df in sheets.items():
            df.to_excel(w, index=False, sheet_name=name[:31])
    return bio.getvalue()


def ensure_sheets(sheets: Dict[str, pd.DataFrame]) -> Dict[str, pd.DataFrame]:
    out = dict(sheets)
    for sh in REQUIRED_SHEETS:
        if sh not in out or out[sh] is None:
            out[sh] = pd.DataFrame()
    for sh in OPTIONAL_SHEETS:
        if sh not in out or out[sh] is None:
            out[sh] = pd.DataFrame()
    return out


# =========================================================
# Validation
# =========================================================

def validate_sheets(sheets: Dict[str, pd.DataFrame]) -> List[str]:
    s = ensure_sheets(sheets)
    errs: List[str] = []

    def need(df: pd.DataFrame, cols: List[str], name: str):
        if df is None or df.empty:
            return
        miss = [c for c in cols if c not in df.columns]
        if miss:
            errs.append(f"{name}: mancano colonne {miss}")

    need(s["nodes"], ["id", "x", "y", "z"], "nodes")

    need(s["beam_elements"], ["id", "n1", "n2", "prop"], "beam_elements")
    need(s["beam_properties"], ["id", "name", "A", "E", "G", "J", "Iy", "Iz"], "beam_properties")

    need(s["shell_elements"], ["id", "n1", "n2", "n3", "n4", "sec"], "shell_elements")
    need(s["shell_sections"], ["id", "name", "E", "nu", "h", "rho"], "shell_sections")

    need(s["load_cases"], ["id", "name"], "load_cases")
    need(s["restraints"], ["load_case_id", "node_id", "ux", "uy", "uz", "rx", "ry", "rz"], "restraints")
    need(s["node_loads"], ["load_case_id", "node_id", "fx", "fy", "fz", "mx", "my", "mz"], "node_loads")

    if s["beam_dist_loads"] is not None and not s["beam_dist_loads"].empty:
        need(s["beam_dist_loads"], ["load_case_id", "elem_id", "qx0", "qx1", "qy0", "qy1", "qz0", "qz1"], "beam_dist_loads")

    if s["masses"] is not None and not s["masses"].empty:
        need(s["masses"], ["load_case_id", "node_id", "mx", "my", "mz"], "masses")

    return errs


# =========================================================
# OpenSees helpers
# =========================================================

def _analysis_linear_static():
    ops.system("BandGeneral")
    ops.numberer("RCM")
    ops.constraints("Plain")
    ops.test("NormDispIncr", 1e-12, 10)
    ops.algorithm("Linear")
    ops.integrator("LoadControl", 1.0)
    ops.analysis("Static")


def _pick_vecxz_for_element(p1: Tuple[float, float, float], p2: Tuple[float, float, float]) -> List[float]:
    """Pick a vecxz not parallel to element x-axis.

    For geomTransf Linear in 3D you must pass vecxz to define local x-z plane.
    """
    dx = np.array([p2[0]-p1[0], p2[1]-p1[1], p2[2]-p1[2]], dtype=float)
    n = float(np.linalg.norm(dx))
    if n == 0.0:
        return [0.0, 0.0, 1.0]
    ex = dx / n
    if abs(float(ex.dot(np.array([0.0, 0.0, 1.0])))) > 0.9:
        return [0.0, 1.0, 0.0]
    return [0.0, 0.0, 1.0]


def _apply_trapezoid_segmented_uniform(eleTag: int, qx0: float, qx1: float, qy0: float, qy1: float, qz0: float, qz1: float, nseg: int):
    """Approximate linearly varying distributed load with multiple uniform -beamUniform loads.

    For 3D beams, eleLoad -beamUniform expects Wy, Wz and optional Wx.
    """
    nseg = max(1, int(nseg))
    for k in range(nseg):
        sm = (k + 0.5) / nseg
        qx = qx0 + (qx1 - qx0) * sm
        qy = qy0 + (qy1 - qy0) * sm
        qz = qz0 + (qz1 - qz0) * sm
        ops.eleLoad("-ele", int(eleTag), "-type", "-beamUniform", float(qy), float(qz), float(qx))


# =========================================================
# Solver: 3D frame + RC core as shell mesh
# =========================================================

def solve_linear_static_frame_core_mesh(
    sheets: Dict[str, pd.DataFrame],
    load_case_id: int,
    beam_trapezoid_segments: int = 10,
    geom_transf: str = "Linear",
    shell_element_type: str = "ShellMITC4",
) -> Dict[str, pd.DataFrame]:
    """Linear static analysis in OpenSeesPy for:

    - 3D frame: elasticBeamColumn (A,E,G,J,Iy,Iz)
    - RC core walls: shell mesh using ShellMITC4 with ElasticMembranePlateSection

    Notes:
    - ShellMITC4 requires ndm=3, ndf=6 and a SectionForceDeformation that must be
      PlateFiberSection or ElasticMembranePlateSection.
    - ElasticMembranePlateSection is isotropic: E, nu, thickness h, density rho.
    """
    s = ensure_sheets(sheets)
    errs = validate_sheets(s)
    if errs:
        raise ValueError("Input non valido:\n- " + "\n- ".join(errs))

    # copy
    nodes = s["nodes"].copy()
    b_elems = s["beam_elements"].copy()
    b_props = s["beam_properties"].copy()
    sh_elems = s["shell_elements"].copy()
    sh_secs = s["shell_sections"].copy()

    # normalize ints
    nodes["id"] = nodes["id"].astype(int)
    b_elems["id"] = b_elems["id"].astype(int)
    b_elems["n1"] = b_elems["n1"].astype(int)
    b_elems["n2"] = b_elems["n2"].astype(int)
    b_elems["prop"] = b_elems["prop"].astype(int)
    b_props["id"] = b_props["id"].astype(int)

    sh_elems["id"] = sh_elems["id"].astype(int)
    for c in ["n1","n2","n3","n4","sec"]:
        sh_elems[c] = sh_elems[c].astype(int)
    sh_secs["id"] = sh_secs["id"].astype(int)

    coords = {int(r["id"]): (float(r["x"]), float(r["y"]), float(r["z"])) for _, r in nodes.iterrows()}
    bprop = {int(r["id"]): r for _, r in b_props.iterrows()}
    shsec = {int(r["id"]): r for _, r in sh_secs.iterrows()}

    # wipe
    ops.wipe()
    ops.model("basic", "-ndm", 3, "-ndf", 6)

    # nodes
    for nid,(x,y,z) in coords.items():
        ops.node(nid, x, y, z)

    # masses optional
    ms = s.get("masses", pd.DataFrame())
    if ms is not None and not ms.empty:
        ms = ms[ms["load_case_id"].astype(int) == int(load_case_id)].copy()
        for _, r in ms.iterrows():
            nid = int(r["node_id"])
            mx = float(r.get("mx", 0.0))
            my = float(r.get("my", 0.0))
            mz = float(r.get("mz", 0.0))
            ops.mass(nid, mx, my, mz, 0.0, 0.0, 0.0)

    # restraints
    rr = s["restraints"]
    if rr is not None and not rr.empty:
        rr = rr[rr["load_case_id"].astype(int) == int(load_case_id)].copy()
        for _, r in rr.iterrows():
            nid = int(r["node_id"])
            ux = 1 if bool(r.get("ux", False)) else 0
            uy = 1 if bool(r.get("uy", False)) else 0
            uz = 1 if bool(r.get("uz", False)) else 0
            rx = 1 if bool(r.get("rx", False)) else 0
            ry = 1 if bool(r.get("ry", False)) else 0
            rz = 1 if bool(r.get("rz", False)) else 0
            ops.fix(nid, ux, uy, uz, rx, ry, rz)

    # shell sections: ElasticMembranePlateSection
    # section('ElasticMembranePlateSection', secTag, E, nu, h, rho)
    for sec_id, r in shsec.items():
        E = float(r["E"])
        nu = float(r["nu"])
        h = float(r["h"])
        rho = float(r.get("rho", 0.0))
        ops.section("ElasticMembranePlateSection", int(sec_id), E, nu, h, rho)

    # coordinate transformations for beams (per orientation)
    transf_tags = {}
    next_transf = 1

    def get_transf(n1: int, n2: int) -> int:
        nonlocal next_transf
        vecxz = tuple(_pick_vecxz_for_element(coords[n1], coords[n2]))
        key = (geom_transf, vecxz)
        if key in transf_tags:
            return transf_tags[key]
        tag = next_transf
        next_transf += 1
        ops.geomTransf(str(geom_transf), tag, *vecxz)
        transf_tags[key] = tag
        return tag

    # beam elements: elasticBeamColumn 3D
    for _, e in b_elems.iterrows():
        etag = int(e["id"])
        n1 = int(e["n1"])
        n2 = int(e["n2"])
        pid = int(e["prop"])
        if pid not in bprop:
            raise ValueError(f"beam_elements id={etag}: prop {pid} non trovata")
        pr = bprop[pid]
        A = float(pr["A"])
        E = float(pr["E"])
        G = float(pr["G"])
        J = float(pr["J"])
        Iy = float(pr["Iy"])
        Iz = float(pr["Iz"])
        ttag = get_transf(n1, n2)
        ops.element("elasticBeamColumn", etag, n1, n2, A, E, G, J, Iy, Iz, ttag)

    # shell elements: ShellMITC4 (or other shell types) - 4 nodes CCW
    for _, e in sh_elems.iterrows():
        etag = int(e["id"])
        n1 = int(e["n1"]); n2 = int(e["n2"]); n3 = int(e["n3"]); n4 = int(e["n4"])
        sec = int(e["sec"])
        if sec not in shsec:
            raise ValueError(f"shell_elements id={etag}: sec {sec} non trovata")
        # element('ShellMITC4', tag, n1,n2,n3,n4, secTag)
        ops.element(str(shell_element_type), etag, n1, n2, n3, n4, sec)

    # loads
    ops.timeSeries("Linear", 1)
    ops.pattern("Plain", 1, 1)

    # nodal loads (apply to both frame and shell nodes)
    nl = s["node_loads"]
    if nl is not None and not nl.empty:
        nl = nl[nl["load_case_id"].astype(int) == int(load_case_id)].copy()
        for _, r in nl.iterrows():
            nid = int(r["node_id"])
            fx = float(r.get("fx", 0.0))
            fy = float(r.get("fy", 0.0))
            fz = float(r.get("fz", 0.0))
            mx = float(r.get("mx", 0.0))
            my = float(r.get("my", 0.0))
            mz = float(r.get("mz", 0.0))
            ops.load(nid, fx, fy, fz, mx, my, mz)

    # beam distributed loads
    bdl = s.get("beam_dist_loads", pd.DataFrame())
    if bdl is not None and not bdl.empty:
        bdl = bdl[bdl["load_case_id"].astype(int) == int(load_case_id)].copy()
        for _, r in bdl.iterrows():
            etag = int(r["elem_id"])
            qx0 = float(r.get("qx0", 0.0)); qx1 = float(r.get("qx1", 0.0))
            qy0 = float(r.get("qy0", 0.0)); qy1 = float(r.get("qy1", 0.0))
            qz0 = float(r.get("qz0", 0.0)); qz1 = float(r.get("qz1", 0.0))
            _apply_trapezoid_segmented_uniform(etag, qx0,qx1,qy0,qy1,qz0,qz1, beam_trapezoid_segments)

    # analysis
    _analysis_linear_static()
    ok = ops.analyze(1)
    if ok != 0:
        raise RuntimeError(f"OpenSees analyze failed with code={ok}")

    ops.reactions()

    # outputs
    nodal_rows = []
    for nid in coords.keys():
        disp = [float(ops.nodeDisp(nid, i)) for i in range(1, 7)]
        reac = [float(ops.nodeReaction(nid, i)) for i in range(1, 7)]
        nodal_rows.append({
            "node_id": int(nid),
            "ux": disp[0], "uy": disp[1], "uz": disp[2],
            "rx": disp[3], "ry": disp[4], "rz": disp[5],
            "Fx": reac[0], "Fy": reac[1], "Fz": reac[2],
            "Mx": reac[3], "My": reac[4], "Mz": reac[5],
        })

    # beam forces local (12)
    beam_rows = []
    for _, e in b_elems.iterrows():
        etag = int(e["id"])
        lf = ops.eleResponse(etag, "localForce")
        lf = list(lf) if lf is not None else []
        if len(lf) < 12:
            lf = (lf + [0.0]*12)[:12]
        beam_rows.append({
            "id": etag,
            "n1": int(e["n1"]), "n2": int(e["n2"]),
            "Fx_i": float(lf[0]), "Fy_i": float(lf[1]), "Fz_i": float(lf[2]),
            "Mx_i": float(lf[3]), "My_i": float(lf[4]), "Mz_i": float(lf[5]),
            "Fx_j": float(lf[6]), "Fy_j": float(lf[7]), "Fz_j": float(lf[8]),
            "Mx_j": float(lf[9]), "My_j": float(lf[10]), "Mz_j": float(lf[11]),
        })

    # shell results: store raw 'forces' vector (shell supports 'forces' query)
    shell_rows = []
    for _, e in sh_elems.iterrows():
        etag = int(e["id"])
        forces = ops.eleResponse(etag, "forces")
        forces = list(forces) if forces is not None else []
        shell_rows.append({
            "id": etag,
            "n1": int(e["n1"]), "n2": int(e["n2"]), "n3": int(e["n3"]), "n4": int(e["n4"]),
            "sec": int(e["sec"]),
            "forces": " ".join([str(float(x)) for x in forces])
        })

    return {
        "results_nodal": pd.DataFrame(nodal_rows),
        "results_beam_localForce": pd.DataFrame(beam_rows),
        "results_shell_forces": pd.DataFrame(shell_rows),
    }


def results_to_sheets(base_sheets: Dict[str, pd.DataFrame], results: Dict[str, pd.DataFrame]) -> Dict[str, pd.DataFrame]:
    out = dict(base_sheets)
    for k, df in results.items():
        out[k] = df
    return out
