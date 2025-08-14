import streamlit as st
import pandas as pd
from io import BytesIO
from datetime import datetime
from calc import (
    compute_realizado,
    meses_simulaveis,
    calc_por_margem,
    base_pis_cofins,
    irpj_csll_trimestrais,
    MARGENS,
)

st.set_page_config(page_title="Simulação de Faturamento 2025", layout="wide")

MESES_PT = {
    1: "Jan", 2: "Fev", 3: "Mar", 4: "Abr", 5: "Mai", 6: "Jun",
    7: "Jul", 8: "Ago", 9: "Set", 10: "Out", 11: "Nov", 12: "Dez",
}


def fmt_brl(v: float) -> str:
    try:
        return f"R$ {float(v):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except Exception:
        return "R$ 0,00"


def to_excel(df: pd.DataFrame) -> bytes:
    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df.to_excel(writer, index=False)
    return buffer.getvalue()


@st.cache_data(ttl=300)
def load_data(owner: str, repo: str, branch: str, path: str) -> pd.DataFrame:
    url = f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{path}"
    try:
        return pd.read_excel(url, engine="openpyxl")
    except Exception:
        try:
            return pd.read_excel(path, engine="openpyxl")
        except Exception:
            return pd.DataFrame()


def propagate_lat():
    df = st.session_state["tabela"].copy()
    idx = (st.session_state.get("mes_sel", 202501) % 100) - 1
    val = df.at[idx, "LAT"]
    locked = st.session_state.get("locked", [])
    for j in range(idx + 1, 12):
        if j not in locked:
            df.at[j, "LAT"] = val
    st.session_state["tabela"] = df


def reset_lat():
    df = st.session_state["tabela"].copy()
    df["LAT"] = 0.0
    for j, v in st.session_state.get("real_lat", {}).items():
        df.at[j, "LAT"] = v
    st.session_state["tabela"] = df


# =========================
# Sidebar
# =========================
DEFAULTS = {
    "owner": "eduardoveiculos",
    "repo": "SIMULA-AO-DE-FATURAMENTO",
    "branch": "main",
    "path": "resultado_eduardo_veiculos.xlsx",
}

with st.sidebar:
    st.header("Simulação")
    ano = st.selectbox("Ano", [2025], index=0)
    sim_vigente = st.checkbox("Simular mês vigente", value=False)
    base_tipo = st.segmented_control(
        "Base PIS/COFINS",
        options=["Lucro do mês (LAT)", "Receita (FAT)", "Margem (FAT*m)"],
        default="Lucro do mês (LAT)",
    )
    col1, col2 = st.columns(2)
    aliq_pis = col1.number_input(
        "PIS (%)", min_value=0.0, max_value=10.0, value=0.65, step=0.01
    )
    aliq_cof = col2.number_input(
        "COFINS (%)", min_value=0.0, max_value=10.0, value=3.0, step=0.1
    )
    st.divider()
    colA, colB = st.columns(2)
    if colA.button("Propagar LAT para próximos meses", key="btn_propag"):
        propagate_lat()
    if colB.button("Zerar simulação", type="secondary", key="btn_zerar"):
        reset_lat()

with st.expander("Fonte de dados (opcional)", expanded=False):
    st.caption("Parâmetros avançados para debugging")
    owner = st.text_input("Owner", value=DEFAULTS["owner"])
    repo = st.text_input("Repo", value=DEFAULTS["repo"])
    branch = st.text_input("Branch", value=DEFAULTS["branch"])
    path = st.text_input("Path", value=DEFAULTS["path"])

# =========================
# Carregamento de dados
# =========================
df_raw = load_data(owner, repo, branch, path)
realizado = compute_realizado(df_raw) if not df_raw.empty else pd.DataFrame()

lat_map_real: dict[int, float] = {}
if not realizado.empty:
    for idx, row in realizado.iterrows():
        if row["LAT"] > 0:
            lat_map_real[idx - 1] = float(row["LAT"])

if "tabela" not in st.session_state:
    st.session_state["tabela"] = pd.DataFrame(
        {
            "Mês": [MESES_PT[i] for i in range(1, 13)],
            "LAT": [0.0] * 12,
            "Obs": [""] * 12,
        }
    )
    st.session_state["locked"] = list(lat_map_real.keys())
    st.session_state["real_lat"] = lat_map_real
    for j, v in lat_map_real.items():
        st.session_state["tabela"].at[j, "LAT"] = v

# Botão para preencher YTD
if st.button("Preencher pelos valores reais YTD"):
    for j, v in lat_map_real.items():
        st.session_state["tabela"].at[j, "LAT"] = v
        if j not in st.session_state["locked"]:
            st.session_state["locked"].append(j)

# Data editor
mask = pd.DataFrame(False, index=st.session_state["tabela"].index, columns=st.session_state["tabela"].columns)
mask.loc[st.session_state["locked"], "LAT"] = True
df_edit = st.data_editor(
    st.session_state["tabela"],
    column_config={
        "Mês": st.column_config.Column(disabled=True),
        "LAT": st.column_config.NumberColumn("LAT (R$)", min_value=0.0, format="R$ %,.2f"),
        "Obs": st.column_config.TextColumn("Obs"),
    },
    disabled=mask,
    num_rows="fixed",
    use_container_width=True,
)
st.session_state["tabela"] = df_edit

# =========================
# KPIs YTD
# =========================
if not realizado.empty:
    ytd = realizado.sum()
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Entradas", fmt_brl(ytd["Compras"]))
    c2.metric("Saídas", fmt_brl(ytd["FAT"]))
    c3.metric("LAT", fmt_brl(ytd["LAT"]))
    c4.metric("Lucro Líquido", fmt_brl(ytd["LL"]))
    c5.metric("Consumo", fmt_brl(ytd["CONSUMO"]))

# =========================
# Mês selecionado
# =========================
ultimo_real = 0
if not realizado.empty:
    ultimo_real = int(realizado[realizado["LAT"] > 0]["yyyymm"].max())
meses_disp = meses_simulaveis(ultimo_real, sim_vigente, ano)
mes_sel = st.segmented_control(
    "Mês",
    options=[202500 + m for m in range(1, 13)],
    default=meses_disp[0] if meses_disp else 202501,
    format_func=lambda x: MESES_PT[x % 100],
)
st.session_state["mes_sel"] = mes_sel

idx_sel = (mes_sel % 100) - 1
lat_sel = st.session_state["tabela"].at[idx_sel, "LAT"]

with st.expander(f"{MESES_PT[mes_sel % 100]} {ano}", expanded=True):
    margem = st.segmented_control(
        "Cenários um-clique",
        options=MARGENS,
        default=0.20,
        format_func=lambda x: f"{int(x*100)}%",
    )
    res_m = calc_por_margem(lat_sel, margem)
    fat_ref = calc_por_margem(lat_sel, 0.20)["FAT"]
    pis, cofins = base_pis_cofins(
        base_tipo, lat_sel, fat_ref, 0.20, aliq_pis / 100, aliq_cof / 100
    )

    c1, c2, c3 = st.columns(3)
    c1.metric("Faturamento", fmt_brl(res_m["FAT"]))
    c2.metric("Compras", fmt_brl(res_m["COMPRAS"]))
    c3.metric("ICMS", fmt_brl(res_m["ICMS"]))
    c4, c5 = st.columns(2)
    c4.metric("PIS", fmt_brl(pis))
    c5.metric("COFINS", fmt_brl(cofins))

    lat_dict = {
        202500 + i + 1: float(st.session_state["tabela"].at[i, "LAT"])
        for i in range(12)
    }
    irpj_map = irpj_csll_trimestrais(lat_dict)
    irpj, csll = irpj_map.get(mes_sel, (0.0, 0.0))
    if irpj or csll:
        cc1, cc2 = st.columns(2)
        cc1.metric("IRPJ", fmt_brl(irpj))
        cc2.metric("CSLL", fmt_brl(csll))

    df_mes = pd.DataFrame(
        {
            "LAT": [lat_sel],
            "FAT": [res_m["FAT"]],
            "Compras": [res_m["COMPRAS"]],
            "ICMS": [res_m["ICMS"]],
            "PIS": [pis],
            "COFINS": [cofins],
            "IRPJ": [irpj],
            "CSLL": [csll],
        }
    )
    st.download_button(
        "Baixar CSV do mês",
        df_mes.to_csv(index=False).encode("utf-8"),
        file_name=f"mes_{mes_sel}.csv",
        mime="text/csv",
    )

# =========================
# Exportação anual
# =========================
st.markdown("---")
lat_dict = {202500 + i + 1: float(st.session_state["tabela"].at[i, "LAT"]) for i in range(12)}
irpj_map = irpj_csll_trimestrais(lat_dict)
rows = []
for i in range(12):
    y = 202500 + i + 1
    lat = lat_dict.get(y, 0.0)
    fat20 = calc_por_margem(lat, 0.20)["FAT"]
    compras20 = fat20 - lat
    icms20 = 0.05 * fat20
    pis, cof = base_pis_cofins(base_tipo, lat, fat20, 0.20, aliq_pis / 100, aliq_cof / 100)
    irpj, csll = irpj_map.get(y, (0.0, 0.0))
    rows.append(
        {
            "yyyymm": y,
            "LAT": lat,
            "FAT": fat20,
            "Compras": compras20,
            "ICMS": icms20,
            "PIS": pis,
            "COFINS": cof,
            "IRPJ": irpj,
            "CSLL": csll,
        }
    )

df_anual = pd.DataFrame(rows)
st.download_button(
    "Baixar Consolidado Anual (XLSX)",
    to_excel(df_anual),
    file_name="consolidado_2025.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
)
