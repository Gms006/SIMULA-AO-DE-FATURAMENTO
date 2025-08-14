
import streamlit as st
import pandas as pd
from io import BytesIO
from calc import realizado_por_mes, cenarios_por_margem, irpj_csll_trimestre
from ui_helpers import brl, cenarios_fat_compra, pis_cofins, yyyymm_to_label, MARGENS


def inject_css():
    st.markdown(
        """
        <style>
        .app-container {max-width: 1280px; margin: 0 auto;}
        section.main > div {padding-top: 0.5rem;}
        .kpi-grid {display: grid; grid-template-columns: repeat(5, 1fr); gap: 14px;}
        @media (max-width: 1200px){ .kpi-grid {grid-template-columns: repeat(3, 1fr);} }
        @media (max-width: 780px){ .kpi-grid {grid-template-columns: repeat(2, 1fr);} }
        @media (max-width: 520px){ .kpi-grid {grid-template-columns: 1fr;} }
        .card {border:1px solid #E5E7EB;background:#FFF;border-radius:12px;padding:16px 16px 14px;box-shadow:0 2px 6px rgba(15,23,42,.05);}
        .card h4 {font-size:12.5px;font-weight:600;letter-spacing:.3px;color:#475569;margin:0 0 6px 0;text-transform:uppercase;}
        .card .value {font-variant-numeric:tabular-nums;font-weight:700;font-size:26px;color:#0F172A;margin:0;}
        .muted { color:#64748B; font-size:12px; margin-top:4px; }
        .section {margin-top:18px;margin-bottom:6px;}
        .section h3 {margin:0;font-size:18px;}
        .section .sub {color:#64748B;font-size:12.5px;margin-top:2px;}
        .metric-grid {display:grid;grid-template-columns:repeat(3,1fr);gap:14px;}
        @media (max-width:900px){ .metric-grid {grid-template-columns:1fr;} }
        </style>
        """,
        unsafe_allow_html=True,
    )


inject_css()
st.set_page_config(page_title="Simulação de Faturamento 2025", layout="wide")

MESES_PT = {1:"Jan",2:"Fev",3:"Mar",4:"Abr",5:"Mai",6:"Jun",7:"Jul",8:"Ago",9:"Set",10:"Out",11:"Nov",12:"Dez"}


def load_data() -> pd.DataFrame:
    url = "https://raw.githubusercontent.com/eduardoveiculos/SIMULA-AO-DE-FATURAMENTO/main/resultado_eduardo_veiculos.xlsx"
    try:
        return pd.read_excel(url, engine="openpyxl")
    except Exception:
        try:
            return pd.read_excel("resultado_eduardo_veiculos.xlsx", engine="openpyxl")
        except Exception:
            up = st.file_uploader("Carregar planilha", type=["xlsx"])
            if up:
                return pd.read_excel(up, engine="openpyxl")
            return pd.DataFrame()


@st.cache_data(ttl=300)
def get_realizado():
    df_raw = load_data()
    if df_raw.empty:
        return pd.DataFrame(), 0
    realizado = realizado_por_mes(df_raw)
    non_zero = realizado[(realizado[["FAT","COMPRAS"]] != 0).any(axis=1)]
    mes_vigente = int(non_zero.index.max()) if not non_zero.empty else 202501
    return realizado, mes_vigente


realizado, mes_vigente = get_realizado()

with st.sidebar:
    st.header("Simulação")
    st.selectbox("Ano", [2025], index=0)
    sim_vigente = st.checkbox("Simular mês vigente", value=False)
    st.divider()
    if st.button("Propagar LAT do mês atual para os próximos"):
        if "mes_sel" in st.session_state:
            idx = st.session_state["mes_sel"]%100-1
            val = st.session_state["tabela"].at[idx,"LAT (R$)"]
            for j in range(idx+1,12):
                st.session_state["tabela"].at[j,"LAT (R$)"]=val
    if st.button("Zerar simulação", type="secondary"):
        for j in range(12):
            y = 202501+j
            if y>=mes_vigente:
                st.session_state["tabela"].at[j,"LAT (R$)"]=0.0

if "tabela" not in st.session_state:
    tbl = pd.DataFrame({"Mês":[MESES_PT[i] for i in range(1,13)],"LAT (R$)":[0.0]*12,"Obs":[""]*12})
    for i,y in enumerate(range(202501,202513)):
        if y<mes_vigente:
            tbl.at[i,"LAT (R$)"]=realizado.at[y,"LAT"]
    st.session_state["tabela"] = tbl
    st.session_state["real_lat"]={i:realizado.at[202501+i,"LAT"] for i in range(12) if 202501+i<=mes_vigente}
    st.session_state["real_fat"]={i:realizado.at[202501+i,"FAT"] for i in range(12) if 202501+i<=mes_vigente}
    st.session_state["real_comp"]={i:realizado.at[202501+i,"COMPRAS"] for i in range(12) if 202501+i<=mes_vigente}

lock = [i for i in range((mes_vigente%100)-1)]
if not sim_vigente:
    lock.append((mes_vigente%100)-1)
mask = pd.DataFrame(False,index=range(12),columns=["Mês","LAT (R$)","Obs"])
mask.loc[lock,"LAT (R$)"]=True
edit = st.data_editor(
    st.session_state["tabela"],
    hide_index=True,
    column_config={
        "Mês": st.column_config.TextColumn("Mês", disabled=True, width="small"),
        "LAT (R$)": st.column_config.NumberColumn("LAT (R$)", min_value=0.0, step=100.0, format="R$ %.2f"),
        "Obs": st.column_config.TextColumn("Obs", width="medium"),
    },
    disabled=mask,
    num_rows="fixed",
    use_container_width=True,
)
for i,v in st.session_state["real_lat"].items():
    edit.at[i,"LAT (R$)"]=v
st.session_state["tabela"]=edit

if not realizado.empty:
    ytd = realizado.loc[realizado.index<=mes_vigente].sum()
    lat_dict = realizado.loc[realizado.index<=mes_vigente,"LAT"].to_dict()
    trib_ytd = irpj_csll_trimestre(lat_dict)
    irpj_ytd = sum(v[0] for m,v in trib_ytd.items() if m<=mes_vigente)
    csll_ytd = sum(v[1] for m,v in trib_ytd.items() if m<=mes_vigente)
    pis_ytd = 0.0065*ytd["LAT"]
    cof_ytd = 0.03*ytd["LAT"]
    icms_ytd = 0.05*ytd["FAT"]
    lucro_liq = ytd["LAT"]-(pis_ytd+cof_ytd+icms_ytd+irpj_ytd+csll_ytd)
    st.markdown('<div class="kpi-grid">', unsafe_allow_html=True)
    st.markdown(f'<div class="card"><h4>Entradas</h4><p class="value">{brl(ytd["COMPRAS"])}</p></div>', unsafe_allow_html=True)
    st.markdown(f'<div class="card"><h4>Saídas</h4><p class="value">{brl(ytd["FAT"])}</p></div>', unsafe_allow_html=True)
    st.markdown(f'<div class="card"><h4>LAT</h4><p class="value">{brl(ytd["LAT"])}</p></div>', unsafe_allow_html=True)
    st.markdown(f'<div class="card warn"><h4>Lucro Líquido</h4><p class="value">{brl(lucro_liq)}</p></div>', unsafe_allow_html=True)
    st.markdown(f'<div class="card"><h4>Mês Vigente</h4><p class="value">{yyyymm_to_label(mes_vigente)}</p></div>', unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

meses = [202500+i for i in range(1,13)]
mes_sel = st.segmented_control("Mês", options=meses, default=meses[0], format_func=lambda x: MESES_PT[x%100])
st.session_state["mes_sel"]=mes_sel

lat_total = {}
for i,y in enumerate(meses):
    real = st.session_state["real_lat"].get(i,0.0)
    sim = st.session_state["tabela"].at[i,"LAT (R$)"] if y>=mes_vigente else 0.0
    if y<mes_vigente:
        lat_total[y]=real
    elif y==mes_vigente:
        lat_total[y]=real + (sim if sim_vigente else 0.0)
    else:
        lat_total[y]=sim
trib_map = irpj_csll_trimestre(lat_total)

idx = mes_sel%100-1
if mes_sel<mes_vigente:
    lat_mes = st.session_state["real_lat"].get(idx,0.0)
elif mes_sel==mes_vigente:
    lat_real = st.session_state["real_lat"].get(idx,0.0)
    lat_sim = st.session_state["tabela"].at[idx,"LAT (R$)"] if sim_vigente else 0.0
    lat_mes = lat_real + lat_sim
else:
    lat_mes = st.session_state["tabela"].at[idx,"LAT (R$)"]

cen = cenarios_fat_compra(lat_mes)
pis_mes, cof_mes = pis_cofins(lat_mes)
ref = st.segmented_control("Cenário", options=[int(m*100) for m in MARGENS], default=20, format_func=lambda x: f"{x}%")
vals = cen.get(ref,{"FAT":0.0,"COMPRA":0.0,"ICMS":0.0})

st.markdown('<div class="section"><h3>Simulação do mês</h3><div class="sub">FAT/Compra variam por margem; PIS/COFINS fixos sobre o LAT</div></div>', unsafe_allow_html=True)

st.markdown('<div class="metric-grid">', unsafe_allow_html=True)
st.markdown(f'<div class="card"><h4>Faturamento (ref. {ref}%)</h4><p class="value">{brl(vals["FAT"])}</p></div>', unsafe_allow_html=True)
st.markdown(f'<div class="card"><h4>Compras (ref. {ref}%)</h4><p class="value">{brl(vals["COMPRA"])}</p></div>', unsafe_allow_html=True)
st.markdown(f'<div class="card"><h4>ICMS (ref. {ref}%)</h4><p class="value">{brl(vals["ICMS"])}</p></div>', unsafe_allow_html=True)
st.markdown('</div>', unsafe_allow_html=True)

st.markdown('<div class="metric-grid">', unsafe_allow_html=True)
st.markdown(f'<div class="card"><h4>PIS (mês)</h4><p class="value">{brl(pis_mes)}</p></div>', unsafe_allow_html=True)
st.markdown(f'<div class="card"><h4>COFINS (mês)</h4><p class="value">{brl(cof_mes)}</p></div>', unsafe_allow_html=True)
if mes_sel in trib_map:
    irpj, csll = trib_map[mes_sel]
    st.markdown(f'<div class="card"><h4>IRPJ</h4><p class="value">{brl(irpj)}</p></div>', unsafe_allow_html=True)
    st.markdown(f'<div class="card"><h4>CSLL</h4><p class="value">{brl(csll)}</p></div>', unsafe_allow_html=True)
st.markdown('</div>', unsafe_allow_html=True)

# mês vigente breakdown
if mes_sel==mes_vigente and sim_vigente:
    lat_real = st.session_state["real_lat"].get(idx,0.0)
    lat_sim = st.session_state["tabela"].at[idx,"LAT (R$)"]
    st.markdown(f"Realizado até agora: {brl(lat_real)} | Simulado: {brl(lat_sim)} | Total do mês: {brl(lat_real+lat_sim)}")

# exportações
mes_df = pd.DataFrame({
    "Mês":[MESES_PT[mes_sel%100]],
    "LAT":[lat_mes],
    "PIS":[pis_mes],
    "COFINS":[cof_mes],
})
st.download_button("Baixar resumo do mês", data=mes_df.to_csv(index=False).encode("utf-8"), file_name=f"resumo_{mes_sel}.csv", mime="text/csv")

rows=[]
for y in meses:
    lat = lat_total[y]
    cen20 = cenarios_por_margem(lat)[20]
    pis, cof = pis_cofins(lat)
    irpj, csll = trib_map.get(y,(0.0,0.0))
    rows.append({"Mês": yyyymm_to_label(y), "LAT": lat, "FAT": cen20["FAT"], "COMPRAS": cen20["COMPRAS"], "PIS": pis, "COFINS": cof, "IRPJ": irpj, "CSLL": csll})
annual = pd.DataFrame(rows)

buf = BytesIO()
with pd.ExcelWriter(buf, engine="openpyxl") as w:
    annual.to_excel(w, index=False)
st.download_button("Baixar Consolidado Anual (XLSX)", data=buf.getvalue(), file_name="consolidado.xlsx")