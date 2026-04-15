# app.py
import streamlit as st
import pandas as pd
import plotly.graph_objects as go

from src import (
    read_xlsx, write_xlsx, ensure_sheets, validate_sheets,
    solve_linear_static_frame_core_mesh, results_to_sheets
)

st.set_page_config(page_title="Telaio 3D + Nucleo c.a. (mesh) — OpenSeesPy", layout="wide")

st.title("Telaio 3D + Nucleo in c.a. (mesh shell) — Streamlit + OpenSeesPy")
st.caption("Importa XLSX → modifica tabelle → Solve (OpenSeesPy) → esporta XLSX con risultati")

if "sheets" not in st.session_state:
    st.session_state.sheets = ensure_sheets({})
if "results" not in st.session_state:
    st.session_state.results = None

with st.sidebar:
    st.header("File")
    up = st.file_uploader("Carica input .xlsx", type=["xlsx"])
    if up is not None:
        st.session_state.sheets = ensure_sheets(read_xlsx(up.getvalue()))
        st.session_state.results = None
        st.success("XLSX caricato.")

    lc_df = st.session_state.sheets.get("load_cases", pd.DataFrame())
    if lc_df is not None and not lc_df.empty and "id" in lc_df.columns:
        lc_ids = [int(x) for x in lc_df["id"].dropna().tolist()] or [1]
    else:
        lc_ids = [1]
    active_lc = st.selectbox("Load case attivo", lc_ids, index=0)

    st.divider()
    st.header("Solve")
    seg = st.slider("Segmenti trapezio (beam_dist_loads)", 1, 50, 10, 1)
    shell_type = st.selectbox("Tipo shell", ["ShellMITC4"], index=0)

    if st.button("Valida modello"):
        errs = validate_sheets(st.session_state.sheets)
        if errs:
            st.error("Problemi trovati:\n" + "\n".join([f"• {e}" for e in errs]))
        else:
            st.success("OK: input coerente.")

    if st.button("Solve ▸ Linear Static"):
        errs = validate_sheets(st.session_state.sheets)
        if errs:
            st.error("Correggi prima gli errori:\n" + "\n".join([f"• {e}" for e in errs]))
        else:
            try:
                st.session_state.results = solve_linear_static_frame_core_mesh(
                    st.session_state.sheets,
                    int(active_lc),
                    beam_trapezoid_segments=seg,
                    geom_transf="Linear",
                    shell_element_type=shell_type,
                )
                st.success("Analisi completata.")
            except Exception as ex:
                st.exception(ex)

    st.divider()
    st.header("Export")
    out_sheets = st.session_state.sheets
    if st.session_state.results is not None:
        out_sheets = results_to_sheets(out_sheets, st.session_state.results)
    xbytes = write_xlsx(out_sheets)
    st.download_button("Scarica XLSX (con risultati)", data=xbytes, file_name="telaio3d_core_mesh_output.xlsx")


tabs = st.tabs([
    "nodes",
    "beam_elements",
    "beam_properties",
    "shell_elements",
    "shell_sections",
    "load_cases",
    "restraints",
    "node_loads",
    "beam_dist_loads",
    "masses",
    "results",
    "plot3d"
])


def edit_sheet(name: str, default_cols: list):
    df = st.session_state.sheets.get(name, pd.DataFrame(columns=default_cols))
    if df is None:
        df = pd.DataFrame(columns=default_cols)
    edited = st.data_editor(df, num_rows="dynamic", use_container_width=True, key=f"edit_{name}")
    st.session_state.sheets[name] = edited


with tabs[0]:
    st.subheader("nodes (id, x, y, z)")
    edit_sheet("nodes", ["id","x","y","z"])

with tabs[1]:
    st.subheader("beam_elements (id, n1, n2, prop)")
    edit_sheet("beam_elements", ["id","n1","n2","prop"])

with tabs[2]:
    st.subheader("beam_properties (id, name, A, E, G, J, Iy, Iz)")
    edit_sheet("beam_properties", ["id","name","A","E","G","J","Iy","Iz"])

with tabs[3]:
    st.subheader("shell_elements (id, n1, n2, n3, n4, sec)")
    st.caption("Nodi in ordine antiorario (CCW) nel piano dell'elemento.")
    edit_sheet("shell_elements", ["id","n1","n2","n3","n4","sec"])

with tabs[4]:
    st.subheader("shell_sections (id, name, E, nu, h, rho)")
    st.caption("Sezioni per shell: ElasticMembranePlateSection")
    edit_sheet("shell_sections", ["id","name","E","nu","h","rho"])

with tabs[5]:
    st.subheader("load_cases (id, name)")
    edit_sheet("load_cases", ["id","name"])

with tabs[6]:
    st.subheader("restraints (load_case_id, node_id, ux,uy,uz,rx,ry,rz)")
    edit_sheet("restraints", ["load_case_id","node_id","ux","uy","uz","rx","ry","rz"])

with tabs[7]:
    st.subheader("node_loads (load_case_id, node_id, fx,fy,fz,mx,my,mz)")
    edit_sheet("node_loads", ["load_case_id","node_id","fx","fy","fz","mx","my","mz"])

with tabs[8]:
    st.subheader("beam_dist_loads (load_case_id, elem_id, qx0,qx1,qy0,qy1,qz0,qz1)")
    edit_sheet("beam_dist_loads", ["load_case_id","elem_id","qx0","qx1","qy0","qy1","qz0","qz1"])

with tabs[9]:
    st.subheader("masses (load_case_id, node_id, mx, my, mz)")
    edit_sheet("masses", ["load_case_id","node_id","mx","my","mz"])

with tabs[10]:
    st.subheader("results")
    if st.session_state.results is None:
        st.info("Esegui Solve per vedere i risultati.")
    else:
        st.markdown("### results_nodal")
        st.dataframe(st.session_state.results["results_nodal"], use_container_width=True)
        st.markdown("### results_beam_localForce")
        st.dataframe(st.session_state.results["results_beam_localForce"], use_container_width=True)
        st.markdown("### results_shell_forces")
        st.dataframe(st.session_state.results["results_shell_forces"], use_container_width=True)

with tabs[11]:
    st.subheader("plot3d")
    nodes = st.session_state.sheets.get("nodes", pd.DataFrame())
    be = st.session_state.sheets.get("beam_elements", pd.DataFrame())
    se = st.session_state.sheets.get("shell_elements", pd.DataFrame())

    if nodes is None or nodes.empty:
        st.info("Inserisci nodes.")
    else:
        coords = {int(r["id"]):(float(r["x"]), float(r["y"]), float(r["z"])) for _, r in nodes.iterrows() if pd.notna(r.get("id"))}
        fig = go.Figure()

        # beams
        if be is not None and not be.empty:
            for _, e in be.iterrows():
                n1 = int(e["n1"]); n2 = int(e["n2"])
                if n1 not in coords or n2 not in coords:
                    continue
                x1,y1,z1 = coords[n1]; x2,y2,z2 = coords[n2]
                fig.add_trace(go.Scatter3d(x=[x1,x2], y=[y1,y2], z=[z1,z2], mode='lines',
                                           line=dict(color='#444', width=5), name='beam', showlegend=False))

        # shells as edges
        if se is not None and not se.empty:
            for _, e in se.iterrows():
                n = [int(e[k]) for k in ["n1","n2","n3","n4"]]
                if any(ni not in coords for ni in n):
                    continue
                poly = n + [n[0]]
                xs = [coords[i][0] for i in poly]
                ys = [coords[i][1] for i in poly]
                zs = [coords[i][2] for i in poly]
                fig.add_trace(go.Scatter3d(x=xs, y=ys, z=zs, mode='lines',
                                           line=dict(color='#888', width=2), name='shell', showlegend=False))

        # deformata (solo traslazioni)
        if st.session_state.results is not None:
            scale = st.slider("Scala deformata", 0.0, 500.0, 50.0, 1.0)
            disp = st.session_state.results["results_nodal"].set_index("node_id")
            dcoords = {}
            for nid,(x,y,z) in coords.items():
                ux = float(disp.loc[nid, "ux"]) if nid in disp.index else 0.0
                uy = float(disp.loc[nid, "uy"]) if nid in disp.index else 0.0
                uz = float(disp.loc[nid, "uz"]) if nid in disp.index else 0.0
                dcoords[nid] = (x + scale*ux, y + scale*uy, z + scale*uz)

            if be is not None and not be.empty:
                for _, e in be.iterrows():
                    n1 = int(e["n1"]); n2 = int(e["n2"])
                    if n1 not in dcoords or n2 not in dcoords:
                        continue
                    x1,y1,z1 = dcoords[n1]; x2,y2,z2 = dcoords[n2]
                    fig.add_trace(go.Scatter3d(x=[x1,x2], y=[y1,y2], z=[z1,z2], mode='lines',
                                               line=dict(color='#1f77b4', width=6), showlegend=False))

        fig.update_layout(scene=dict(xaxis_title='X', yaxis_title='Y', zaxis_title='Z'),
                          margin=dict(l=0,r=0,t=0,b=0), height=700)
        st.plotly_chart(fig, use_container_width=True)
