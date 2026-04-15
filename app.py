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
st.caption("Genera parametri → modifica tabelle → Solve (OpenSeesPy) → esporta XLSX con risultati")


def generate_nucleo(distanzeX: list, distanzeY: list, altezzeZ: list, 
                    posizione_nucleo: str, E: float, E_shell: float, h_shell: float):
    """Genera un telaio 3D con nucleo a U."""
    nodes = []
    beam_elements = []
    shell_elements = []
    
    x_cum = [0.0]
    for d in distanzeX:
        x_cum.append(x_cum[-1] + d)
    
    y_cum = [0.0]
    for d in distanzeY:
        y_cum.append(y_cum[-1] + d)
    
    z_cum = [0.0]
    for h in altezzeZ:
        z_cum.append(z_cum[-1] + h)
    
    node_id = 1
    node_map = {}
    
    for iz, z in enumerate(z_cum):
        for iy, y in enumerate(y_cum):
            for ix, x in enumerate(x_cum):
                node_map[(iz, iy, ix)] = node_id
                nodes.append({"id": node_id, "x": x, "y": y, "z": z})
                node_id += 1
    
    # Beam elements: pilastri
    beam_id = 1
    pilastri_ids = []
    travi_ids = []
    
    # Pilastri verticali
    for ix in range(len(x_cum)):
        for iy in range(len(y_cum)):
            for iz in range(1, len(z_cum)):
                n1 = node_map[(iz - 1, iy, ix)]
                n2 = node_map[(iz, iy, ix)]
                beam_elements.append({"id": beam_id, "n1": n1, "n2": n2, "prop": 1})
                pilastri_ids.append(beam_id)
                beam_id += 1
    
    # Travi X
    for iz in range(1, len(z_cum)):
        for iy in range(len(y_cum)):
            for ix in range(len(x_cum) - 1):
                n1 = node_map[(iz, iy, ix)]
                n2 = node_map[(iz, iy, ix + 1)]
                beam_elements.append({"id": beam_id, "n1": n1, "n2": n2, "prop": 1})
                travi_ids.append(beam_id)
                beam_id += 1
    
    # Travi Y
    for iz in range(1, len(z_cum)):
        for iy in range(len(y_cum) - 1):
            for ix in range(len(x_cum)):
                n1 = node_map[(iz, iy, ix)]
                n2 = node_map[(iz, iy + 1, ix)]
                beam_elements.append({"id": beam_id, "n1": n1, "n2": n2, "prop": 1})
                travi_ids.append(beam_id)
                beam_id += 1
    
    # Shell elements: nucleo a U (inizia da beam_id per evitare conflitti)
    shell_id = beam_id + 1
    nx, ny = len(x_cum), len(y_cum)
    
    # Posizioni nucleo
    pos_map = {
        "sx": (0, ny // 2),
        "dx": (nx - 1, ny // 2),
        "centro": (nx // 2, ny // 2),
        "sx_up": (0, 0),
        "dx_up": (nx - 1, 0),
        "sx_down": (0, ny - 1),
        "dx_down": (nx - 1, ny - 1),
    }
    
    base_x, base_y = pos_map.get(posizione_nucleo, (nx // 2, ny // 2))
    
    for iz in range(1, len(z_cum)):
        # Parete 1: verticale (asse X)
        if base_x > 0 and base_x < nx - 1:
            n1 = node_map[(iz, base_y, base_x)]
            n2 = node_map[(iz, base_y, base_x + 1)]
            n3 = node_map[(iz - 1, base_y, base_x + 1)]
            n4 = node_map[(iz - 1, base_y, base_x)]
            shell_elements.append({"id": shell_id, "n1": n1, "n2": n2, "n3": n3, "n4": n4, "sec": 1})
            shell_id += 1
        
        # Parete 2: orizzontale (asse Y)
        if base_y > 0 and base_y < ny - 1:
            n1 = node_map[(iz, base_y, base_x)]
            n2 = node_map[(iz, base_y + 1, base_x)]
            n3 = node_map[(iz - 1, base_y + 1, base_x)]
            n4 = node_map[(iz - 1, base_y, base_x)]
            shell_elements.append({"id": shell_id, "n1": n1, "n2": n2, "n3": n3, "n4": n4, "sec": 1})
            shell_id += 1
    
    # Carichi distribuiti su travi
    dist_loads = []
    qz = -2.0
    for tid in travi_ids:
        dist_loads.append({"load_case_id": 1, "elem_id": tid, "qx0": 0.0, "qx1": 0.0, "qy0": 0.0, "qy1": 0.0, "qz0": qz, "qz1": qz})
    dist_loads_df = pd.DataFrame(dist_loads)
    
    # Vincoli base
    restraints = []
    for ix in range(len(x_cum)):
        for iy in range(len(y_cum)):
            n = node_map[(0, iy, ix)]
            restraints.append({"load_case_id": 1, "node_id": n, "ux": 1, "uy": 1, "uz": 1, "rx": 1, "ry": 1, "rz": 1})
    restraints_df = pd.DataFrame(restraints)
    
    return {
        "nodes": pd.DataFrame(nodes),
        "beam_elements": pd.DataFrame(beam_elements),
        "beam_properties": pd.DataFrame([{"id": 1, "name": "cls_30", "A": 0.3, "E": E, "G": E/2.4, "J": 0.045, "Iy": 0.0225, "Iz": 0.015}]),
        "shell_elements": pd.DataFrame(shell_elements),
        "shell_sections": pd.DataFrame([{"id": 1, "name": "parete_20", "E": E_shell, "nu": 0.2, "h": h_shell, "rho": 2.5}]),
        "restraints": restraints_df,
        "beam_dist_loads": dist_loads_df,
    }


if "sheets" not in st.session_state:
    st.session_state.sheets = None
if "results" not in st.session_state:
    st.session_state.results = None
if "initialized" not in st.session_state:
    st.session_state.initialized = True

with st.sidebar:
    st.header("Generatore Nucleo c.a.")
    
    st.subheader("Geometry")
    lung_x_str = st.text_input("Lunghezze X (m)", "3.0, 3.0, 3.0", help="es: 3.0, 3.0, 3.0")
    larg_y_str = st.text_input("Larghezza Y (m)", "0.3, 3.0, 0.3", help="es: 0.3, 3.0, 0.3")
    altezze_z_str = st.text_input("Altezze Z (m)", "3.5, 3.0, 3.0", help="es: 3.5, 3.0, 3.0")
    
    st.subheader("Proprietà")
    col1, col2 = st.columns(2)
    with col1:
        E = st.number_input("E travi (MPa)", value=30000.0)
        pos_nucleo = st.selectbox("Posizione nucleo", ["sx", "dx", "centro"], help="sx=sinistra, dx=destra, centro=al centro")
    with col2:
        E_shell = st.number_input("E pareti (MPa)", value=25000.0)
        h_shell = st.number_input("h parete (m)", value=0.2)
    
    st.caption(f"📍 Nucleo a U in posizione: **{pos_nucleo.upper()}**")
    
    if st.button("Genera Nucleo"):
        try:
            dx = [float(x.strip()) for x in lung_x_str.split(",") if x.strip()]
            dy = [float(y.strip()) for y in larg_y_str.split(",") if y.strip()]
            dz = [float(z.strip()) for z in altezze_z_str.split(",") if z.strip()]
            
            sheets = generate_nucleo(dx, dy, dz, pos_nucleo, E, E_shell, h_shell)
            sheets["load_cases"] = pd.DataFrame([{"id": 1, "name": "permanente"}])
            sheets["node_loads"] = pd.DataFrame()
            sheets["masses"] = pd.DataFrame()
                
            st.session_state.sheets = ensure_sheets(sheets)
            st.session_state.results = None
            st.success(f"Generato: {len(sheets['nodes'])} nodi, {len(sheets['beam_elements'])} travi, {len(sheets['shell_elements'])} shell")
        except Exception as e:
            st.error(f"Errore: {e}")

    st.divider()
    st.header("File")
    up = st.file_uploader("Carica input .xlsx", type=["xlsx"])
    if up is not None:
        st.session_state.sheets = ensure_sheets(read_xlsx(up.getvalue()))
        st.session_state.results = None
        st.success("XLSX caricato.")

    if st.button("📂 Carica esempio predefinito"):
        sheets = generate_nucleo([3.0, 3.0, 3.0], [0.3, 3.0, 0.3], [3.5, 3.0, 3.0], "sx", 30000.0, 25000.0, 0.2)
        sheets["load_cases"] = pd.DataFrame([{"id": 1, "name": "permanente"}])
        sheets["node_loads"] = pd.DataFrame()
        sheets["masses"] = pd.DataFrame()
        st.session_state.sheets = ensure_sheets(sheets)
        st.session_state.results = None
        st.success("Esempio caricato!")

    if st.session_state.sheets is not None:
        lc_df = st.session_state.sheets.get("load_cases", pd.DataFrame())
        if lc_df is not None and not lc_df.empty and "id" in lc_df.columns:
            lc_ids = [int(x) for x in lc_df["id"].dropna().tolist()] or [1]
        else:
            lc_ids = [1]
    else:
        lc_ids = [1]
    active_lc = st.selectbox("Load case attivo", lc_ids, index=0)

    st.divider()
    st.header("Solve")
    seg = st.slider("Segmenti trapezio (beam_dist_loads)", 1, 50, 10, 1)
    shell_type = st.selectbox("Tipo shell", ["ShellMITC4"], index=0)

    if st.button("Valida modello"):
        if st.session_state.sheets is None:
            st.warning("Genera o carica un modello prima.")
        else:
            errs = validate_sheets(st.session_state.sheets)
            if errs:
                st.error("Problemi trovati:\n" + "\n".join([f"• {e}" for e in errs]))
            else:
                st.success("OK: input coerente.")

    if st.button("Solve ▸ Linear Static"):
        if st.session_state.sheets is None:
            st.warning("Genera o carica un modello prima.")
        else:
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
    if st.session_state.sheets is not None:
        out_sheets = st.session_state.sheets
        if st.session_state.results is not None:
            out_sheets = results_to_sheets(out_sheets, st.session_state.results)
        xbytes = write_xlsx(out_sheets)
        st.download_button("Scarica XLSX (con risultati)", data=xbytes, file_name="telaio3d_core_mesh_output.xlsx")
    else:
        st.warning("Genera o carica un modello prima.")


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
    if st.session_state.sheets is None:
        st.warning("Genera o carica un modello prima.")
        return
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
    if st.session_state.sheets is None:
        st.warning("Genera o carica un modello prima.")
    else:
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
