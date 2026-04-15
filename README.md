# Telaio 3D + Nucleo in c.a. (mesh) — Streamlit + OpenSeesPy

Questa app è la versione "frame 3D" con un **nucleo in calcestruzzo armato** modellato come **mesh di shell**.

## Scelte OpenSeesPy

- Modello: `model('basic', '-ndm', 3, '-ndf', 6)`
- Telaio: `elasticBeamColumn` 3D (A, E, G, J, Iy, Iz)
- Nucleo: `ShellMITC4` con sezione `ElasticMembranePlateSection` (E, nu, spessore h, densità rho)

## Installazione

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Avvio

```bash
streamlit run app.py
```

## Formato XLSX

Fogli richiesti:
- `nodes`: id, x, y, z (tutti i nodi: telaio + mesh)
- `beam_elements`: id, n1, n2, prop
- `beam_properties`: id, name, A, E, G, J, Iy, Iz
- `shell_elements`: id, n1, n2, n3, n4, sec (nodi in CCW)
- `shell_sections`: id, name, E, nu, h, rho
- `load_cases`: id, name
- `restraints`: load_case_id, node_id, ux,uy,uz,rx,ry,rz
- `node_loads`: load_case_id, node_id, fx,fy,fz,mx,my,mz

Opzionali:
- `beam_dist_loads`: load_case_id, elem_id, qx0,qx1,qy0,qy1,qz0,qz1
- `masses`: load_case_id, node_id, mx, my, mz

## Output

Dopo Solve l'XLSX include:
- `results_nodal` (spostamenti+reazioni)
- `results_beam_localForce` (forze locali beam 3D)
- `results_shell_forces` (risposta shell: `forces` serializzata)
