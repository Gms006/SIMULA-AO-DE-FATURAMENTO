import streamlit as st
import pandas as pd
from io import BytesIO
from datetime import datetime
from calc import (
    realizado_por_mes,
    cenarios_por_margem,
    irpj_csll_trimestre,
    meses_simulaveis,
    mes_vigente,
    prepare_dataframe,
    MARGENS,
)
from ui_helpers import brl, cenarios_fat_compra, pis_cofins, yyyymm_to_label

st.set_page_config(page_title="Simulação de Faturamento 2025", layout="wide")

# ====== CSS PROFISSIONAL ======
def inject_css():
    st.markdown(
        """
        <style>
        /* ====== Layout base ====== */
        .app-container {max-width: 1280px; margin: 0 auto;}
        section.main > div {padding-top: 0.5rem;}

        /* ====== Cards ====== */
        .kpi-grid {display: grid; grid-template-columns: repeat(5, 1fr); gap: 14px;}
        @media (max-width: 1200px){ .kpi-grid {grid-template-columns: repeat(3, 1fr);} }
        @media (max-width: 780px){ .kpi-grid {grid-template-columns: repeat(2, 1fr);} }
        @media (max-width: 520px){ .kpi-grid {grid-template-columns: 1fr;} }

        .card {
            border: 1px solid #E5E7EB;
            background: #FFFFFF;
            border-radius: 12px;
            padding: 16px 16px 14px;
            box-shadow: 0 2px 6px rgba(15, 23, 42, .05);
        }
        .card h4 {
            font-size: 12.5px; font-weight: 600; letter-spacing: .3px;
            color: #475569; margin: 0 0 6px 0;
            text-transform: uppercase;
        }
        .card .value {
            font-variant-numeric: tabular-nums;
            font-weight: 700; font-size: 26px; color: #0F172A;
            margin: 0;
        }
        .muted { color:#64748B; font-size: 12px; margin-top: 4px; }
        .ok    { border-color:#D1FAE5; background: #ECFDF5; }
        .warn  { border-color:#FEF3C7; background: #FFFBEB; }
        .bad   { border-color:#FEE2E2; background: #FEF2F2; }

        /* ====== Section headers ====== */
        .section {margin-top: 18px; margin-bottom: 6px;}
        .section h3 {margin:0; font-size: 18px;}
        .section .sub {color:#64748B; font-size: 12.5px; margin-top:2px;}

        /* ====== Metric trio ====== */
        .metric-grid {display:grid; grid-template-columns: repeat(3,1fr); gap:14px;}
        @media (max-width: 900px){ .metric-grid {grid-template-columns: 1fr; } }

        /* Dark mode (Streamlit toggle) */
        @media (prefers-color-scheme: dark){
            .card { background:#0B1220; border-color:#1F2937; }
            .card h4 { color:#94A3B8; }
            .card .value { color:#E2E8F0; }
            .ok   { background:#052E2B; }
            .warn { background:#2B2412; }
            .bad  { background:#2B1111; }
        }
        </style>
        """,
        unsafe_allow_html=True
    )

inject_css()

# ====== MESES BRASILEIROS ======
MESES_PT = {
    1: "Jan", 2: "Fev", 3: "Mar", 4: "Abr", 5: "Mai", 6: "Jun",
    7: "Jul", 8: "Ago", 9: "Set", 10: "Out", 11: "Nov", 12: "Dez",
}

# ====== FUNÇÕES AUXILIARES ======
@st.cache_data(ttl=300)
def load_data() -> pd.DataFrame:
    """Carrega dados do GitHub ou local automaticamente."""
    # Tenta GitHub primeiro
    url = "https://raw.githubusercontent.com/eduardoveiculos/SIMULA-AO-DE-FATURAMENTO/main/resultado_eduardo_veiculos.xlsx"
    try:
        return pd.read_excel(url, engine="openpyxl")
    except Exception:
        try:
            # Tenta arquivo local
            return pd.read_excel("resultado_eduardo_veiculos.xlsx", engine="openpyxl")
        except Exception:
            return pd.DataFrame()

def to_excel(df: pd.DataFrame) -> bytes:
    """Converte DataFrame para bytes Excel."""
    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df.to_excel(writer, index=False)
    return buffer.getvalue()

def propagar_lat():
    """Propaga LAT do mês selecionado para os próximos."""
    if "tabela" not in st.session_state:
        return
    
    df = st.session_state["tabela"].copy()
    mes_sel = st.session_state.get("mes_selecionado", 1)
    idx = mes_sel - 1
    val = df.at[idx, "LAT (R$)"]
    
    # Propaga para meses posteriores não travados
    locked = st.session_state.get("meses_travados", [])
    for j in range(idx + 1, 12):
        if (j + 1) not in locked:  # j+1 porque locked usa 1-12, idx usa 0-11
            df.at[j, "LAT (R$)"] = val
    
    st.session_state["tabela"] = df

def zerar_simulacao():
    """Zera apenas os valores simulados, mantendo o realizado."""
    if "tabela" not in st.session_state:
        return
        
    df = st.session_state["tabela"].copy()
    locked = st.session_state.get("meses_travados", [])
    realizado = st.session_state.get("valores_realizados", {})
    
    for i in range(12):
        mes_num = i + 1
        if mes_num not in locked:
            df.at[i, "LAT (R$)"] = 0.0
        else:
            # Restaura valor realizado
            df.at[i, "LAT (R$)"] = realizado.get(mes_num, 0.0)
    
    st.session_state["tabela"] = df

# =========================
# SIDEBAR LIMPO
# =========================
with st.sidebar:
    st.header("📊 Simulação")
    
    # Ano fixo por enquanto
    ano = st.selectbox("Ano", [2025], index=0, disabled=True)
    
    # Checkbox para simular mês vigente
    sim_vigente = st.checkbox("✏️ Simular mês vigente", value=False, 
                              help="Permite editar o mês vigente (soma realizado + simulado)")
    
    st.divider()
    
    # Ações rápidas
    col1, col2 = st.columns(2)
    if col1.button("📈 Propagar LAT", help="Copia LAT do mês atual para os próximos"):
        propagar_lat()
        st.rerun()
    
    if col2.button("🗑️ Zerar", type="secondary", help="Remove valores simulados"):
        zerar_simulacao()
        st.rerun()

# =========================
# CARREGAMENTO DE DADOS
# =========================
df_raw = load_data()

# Fallback para upload se não conseguir carregar
if df_raw.empty:
    st.warning("🔍 Não foi possível carregar os dados automaticamente.")
    uploaded = st.file_uploader("📁 Envie o arquivo resultado_eduardo_veiculos.xlsx", type="xlsx")
    if uploaded:
        df_raw = pd.read_excel(uploaded, engine="openpyxl")
    else:
        st.stop()

# Processa dados realizados
realizado = realizado_por_mes(df_raw) if not df_raw.empty else pd.DataFrame()
mes_vig = mes_vigente(realizado) if not realizado.empty else 0

# =========================
# INICIALIZAÇÃO DO SESSION STATE
# =========================
if "tabela" not in st.session_state:
    # Cria tabela inicial
    st.session_state["tabela"] = pd.DataFrame({
        "Mês": [MESES_PT[i] for i in range(1, 13)],
        "LAT (R$)": [0.0] * 12,
        "Obs": [""] * 12,
    })
    
    # Define meses travados (anteriores ao vigente)
    mes_vig_num = mes_vig % 100 if mes_vig > 0 else 0
    st.session_state["meses_travados"] = list(range(1, mes_vig_num + 1)) if not sim_vigente else list(range(1, mes_vig_num))
    
    # Armazena valores realizados
    st.session_state["valores_realizados"] = {}
    if not realizado.empty:
        for i in range(1, 13):
            if i <= mes_vig_num:
                lat_real = realizado.at[i, "LAT"] if i in realizado.index else 0.0
                st.session_state["tabela"].at[i-1, "LAT (R$)"] = lat_real
                st.session_state["valores_realizados"][i] = lat_real

# =========================
# KPIs YTD (APENAS REALIZADO)
# =========================
if not realizado.empty:
    ytd = realizado[realizado["LAT"] > 0].sum()
    
    st.markdown('<div class="kpi-grid">', unsafe_allow_html=True)
    st.markdown(f'''
        <div class="card"><h4>Entradas YTD</h4><p class="value">{brl(ytd["COMPRAS"])}</p></div>
        <div class="card"><h4>Saídas YTD</h4><p class="value">{brl(ytd["FAT"])}</p></div>
        <div class="card"><h4>LAT YTD</h4><p class="value">{brl(ytd["LAT"])}</p></div>
        <div class="card {'ok' if ytd["LL"] > 0 else 'warn' if ytd["LL"] > -50000 else 'bad'}"><h4>Lucro Líquido YTD</h4><p class="value">{brl(ytd["LL"])}</p></div>
        <div class="card"><h4>Mês Vigente</h4><p class="value">{yyyymm_to_label(mes_vig) if mes_vig > 0 else "—"}</p></div>
    ''', unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

# =========================
# EDITOR DE DADOS PROFISSIONAL
# =========================
st.markdown('<div class="section"><h3>📝 Planejamento LAT 2025</h3><div class="sub">Digite o LAT desejado para cada mês. Meses passados estão travados.</div></div>', unsafe_allow_html=True)

# Prepara máscara de campos bloqueados
mask_df = pd.DataFrame(False, index=st.session_state["tabela"].index, columns=st.session_state["tabela"].columns)
for mes_travado in st.session_state["meses_travados"]:
    mask_df.at[mes_travado - 1, "LAT (R$)"] = True

# Editor sem erro de formatação
df_editado = st.data_editor(
    st.session_state["tabela"],
    hide_index=True,
    column_config={
        "Mês": st.column_config.TextColumn("Mês", disabled=True, width="small"),
        "LAT (R$)": st.column_config.NumberColumn(
            "LAT (R$)", 
            min_value=0.0, 
            step=1000.0, 
            format="R$ %.2f",  # Formato seguro sem sprintf
            width="medium"
        ),
        "Obs": st.column_config.TextColumn("Obs", width="large"),
    },
    disabled=mask_df,
    num_rows="fixed",
    use_container_width=True,
    key="data_editor"
)

st.session_state["tabela"] = df_editado

# =========================
# SELETOR DE MÊS E SIMULAÇÃO
# =========================
st.markdown('<div class="section"><h3>🎯 Simulação por Mês</h3><div class="sub">Selecione um mês para ver os cenários detalhados</div></div>', unsafe_allow_html=True)

# Determina meses disponíveis para simulação
mes_vig_num = mes_vig % 100 if mes_vig > 0 else 8  # Default agosto se não há dados
meses_disponiveis = list(range(mes_vig_num if sim_vigente else mes_vig_num + 1, 13))
if not meses_disponiveis:
    meses_disponiveis = [12]  # Fallback

# Seletor de mês com chips
mes_selecionado = st.segmented_control(
    "Mês para simular:",
    options=list(range(1, 13)),
    default=meses_disponiveis[0],
    format_func=lambda x: MESES_PT[x],
    key="selector_mes"
)

st.session_state["mes_selecionado"] = mes_selecionado

# =========================
# CÁLCULOS DO MÊS SELECIONADO
# =========================
idx_mes = mes_selecionado - 1
lat_simulado = st.session_state["tabela"].at[idx_mes, "LAT (R$)"]

# Para o mês vigente, soma realizado + simulado
if mes_selecionado == (mes_vig % 100) and sim_vigente and not realizado.empty:
    lat_real = realizado.at[mes_selecionado, "LAT"] if mes_selecionado in realizado.index else 0.0
    fat_real