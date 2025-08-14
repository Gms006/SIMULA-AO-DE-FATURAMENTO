import streamlit as st
import pandas as pd
import plotly.express as px
from io import BytesIO
from calc import (
    prepare_dataframe,
    compute_realizado,
    calc_mes,
    ultimo_yyyymm,
    meses_simulaveis,
    trimestre_de,
    progresso_trimestre,
    irpj_csll_trimestre,
)

# Configuração da página
st.set_page_config(page_title="Simulação de Faturamento 2025", layout="wide")

# CSS personalizado para cards e styling
st.markdown(
    """
<style>
div.stMetric {
    border: 1px solid #E0E0E0;
    padding: 15px;
    border-radius: 8px;
    background-color: #F6F8FC;
    box-shadow: 0 1px 3px rgba(0,0,0,0.1);
}

.card-margem {
    border: 1px solid #E0E0E0;
    padding: 15px;
    border-radius: 8px;
    background-color: #FFFFFF;
    margin: 10px 0;
    box-shadow: 0 1px 3px rgba(0,0,0,0.1);
}

.card-titulo {
    font-weight: bold;
    font-size: 16px;
    color: #0F172A;
    margin-bottom: 8px;
}

.badge-trimestre {
    display: inline-block;
    padding: 4px 8px;
    border-radius: 4px;
    font-size: 12px;
    font-weight: bold;
    color: white;
}

.badge-completo { background-color: #10B981; }
.badge-incompleto { background-color: #F59E0B; }
</style>
""",
    unsafe_allow_html=True,
)

# Sidebar para parâmetros GitHub
st.sidebar.header("Parâmetros GitHub")
owner = st.sidebar.text_input("Owner", value="")
repo = st.sidebar.text_input("Repo", value="SIMULACAO-DE-FATURAMENTO")
branch = st.sidebar.text_input("Branch", value="main")
path = st.sidebar.text_input("Path", value="resultado_eduardo_veiculos.xlsx")

@st.cache_data(ttl=300)
def load_data(owner: str, repo: str, branch: str, path: str):
    """Carrega dados do GitHub com fallback local e uploader."""
    if owner:
        url = f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{path}"
        try:
            return pd.read_excel(url, engine="openpyxl")
        except Exception:
            st.warning("Falha ao carregar do GitHub.")
    
    # Fallback para arquivo local
    try:
        return pd.read_excel(path, engine="openpyxl")
    except Exception:
        return None

# Carregamento dos dados
df = load_data(owner, repo, branch, path)
if df is None:
    uploaded = st.file_uploader("Envie a planilha resultado_eduardo_veiculos.xlsx", type="xlsx")
    if uploaded:
        df = pd.read_excel(uploaded, engine="openpyxl")

if df is None:
    st.error("Não foi possível carregar os dados. Verifique o arquivo ou parâmetros GitHub.")
    st.stop()

# Processamento dos dados
df = prepare_dataframe(df)
realizado = compute_realizado(df)
ultimo = ultimo_yyyymm(df)
last_month = ultimo % 100 if ultimo else 0

def fmt_brl(v: float) -> str:
    """Formata valor em Real brasileiro."""
    return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

# Mapeamento de meses para português
MESES_PT = {
    1: "Jan", 2: "Fev", 3: "Mar", 4: "Abr", 5: "Mai", 6: "Jun",
    7: "Jul", 8: "Ago", 9: "Set", 10: "Out", 11: "Nov", 12: "Dez",
}

# Seletor de página no sidebar
pagina = st.sidebar.selectbox("Página", ["Simulação", "Dashboard", "Notas/Detalhes"])

if pagina == "Simulação":
    st.title("Simulação de Faturamento 2025")
    
    # Inicializar session state para LAT simulado
    if "lat_sim" not in st.session_state:
        st.session_state["lat_sim"] = {}
    
    lat_sim = st.session_state["lat_sim"]
    
    # === RESUMO YTD (Topo) ===
    st.subheader("Resumo 2025")
    
    # Calcular YTD apenas com dados reais (travados)
    if last_month > 0:
        fat_ytd = realizado.loc[1:last_month, "FAT"].sum()
        lat_ytd = realizado.loc[1:last_month, "LAT"].sum()
    else:
        fat_ytd = lat_ytd = 0.0
    
    col1, col2 = st.columns(2)
    col1.metric("Faturado YTD", fmt_brl(fat_ytd))
    col2.metric("LAT YTD", fmt_brl(lat_ytd))
    
    # === LINHA DE MESES (Chips) ===
    st.markdown("---")
    
    col_mes, col_toggle = st.columns([4, 1])
    
    with col_toggle:
        sim_vigente = st.checkbox("Simular mês vigente", False)
    
    # Determinar meses simuláveis
    meses_disp = meses_simulaveis(ultimo)
    if sim_vigente and ultimo > 0 and ultimo not in meses_disp:
        meses_disp.insert(0, ultimo)
    
    if not meses_disp:
        st.info("Todos os meses de 2025 já estão realizados ou não há dados disponíveis.")
        st.stop()
    
    with col_mes:
        mes_atual = st.segmented_control(
            "Meses simuláveis",
            meses_disp,
            selection=st.session_state.get("mes_atual", meses_disp[0]),
            format_func=lambda m: MESES_PT[m % 100],
        )
    
    st.session_state["mes_atual"] = mes_atual
    
    # === EDITOR DO MÊS SELECIONADO ===
    st.markdown("---")
    st.subheader(f"Editor: {MESES_PT[mes_atual % 100].upper()} {mes_atual // 100}")
    
    # Input LAT do mês
    lat_val = lat_sim.get(mes_atual, 0.0)
    col_lat, col_prop = st.columns([3, 1])
    
    with col_lat:
        lat_input = st.number_input(
            "LAT do mês (R$)",
            min_value=0.0,
            step=1000.0,
            value=lat_val,
            key=f"lat_{mes_atual}",
        )
    
    with col_prop:
        propagar = st.checkbox("Aplicar este LAT aos próximos meses")
    
    # Atualizar session state
    lat_sim[mes_atual] = lat_input
    
    # Auto-propagação se solicitada
    if propagar:
        for m in meses_disp:
            if m >= mes_atual:
                lat_sim[m] = lat_input
    
    # === CARDS POR MARGEM (6 cards; 2 colunas × 3 linhas) ===
    st.markdown("#### Cenários por Margem")
    
    # Calcular cenários para o LAT atual
    res_mes = calc_mes(lat_input)
    cenarios = res_mes["cenarios"]
    margens = [0.05, 0.10, 0.15, 0.20, 0.25, 0.30]
    
    # Layout: 3 linhas com 2 colunas cada
    for i in range(0, 6, 2):
        col1, col2 = st.columns(2)
        
        # Primeira coluna
        with col1:
            m = margens[i]
            st.markdown(f'<div class="card-margem"><div class="card-titulo">Margem {int(m*100)}%</div></div>', unsafe_allow_html=True)
            st.metric("Faturamento", fmt_brl(cenarios[m]["FAT"]))
            st.metric("Compras", fmt_brl(cenarios[m]["COMPRAS"]))
        
        # Segunda coluna (se houver)
        if i + 1 < len(margens):
            with col2:
                m = margens[i + 1]
                st.markdown(f'<div class="card-margem"><div class="card-titulo">Margem {int(m*100)}%</div></div>', unsafe_allow_html=True)
                st.metric("Faturamento", fmt_brl(cenarios[m]["FAT"]))
                st.metric("Compras", fmt_brl(cenarios[m]["COMPRAS"]))
    
    # === CARDS DE TRIBUTOS DO MÊS ===
    st.markdown("#### Tributos do Mês")
    
    pis = res_mes["PIS"]
    cofins = res_mes["COFINS"]
    icms_ref = cenarios[0.20]["ICMS"]  # ICMS usando margem 20% como referência
    
    col1, col2, col3 = st.columns(3)
    col1.metric("PIS (mês)", fmt_brl(pis))
    col2.metric("COFINS (mês)", fmt_brl(cofins))
    col3.metric("ICMS (mês)*", fmt_brl(icms_ref))
    
    st.caption("*ICMS depende do faturamento (varia por margem)")
    
    # === OBRIGAÇÕES TRIMESTRAIS ===
    st.markdown("---")
    st.subheader("Obrigações do Trimestre")
    
    # Combinar dados reais + simulados
    lat_total = {}
    
    # Adicionar dados reais (travados)
    for m in range(1, 13):
        if 202500 + m <= ultimo:
            lat_total[202500 + m] = realizado.loc[m, "LAT"]
    
    # Adicionar simulados
    lat_total.update(lat_sim)
    
    # Avaliar progresso do trimestre atual
    tri_key = trimestre_de(mes_atual)
    prog, total, faltantes = progresso_trimestre(lat_total, tri_key)
    
    # Badge de progresso
    badge_class = "badge-completo" if prog == total else "badge-incompleto"
    st.markdown(f'<span class="badge-trimestre {badge_class}">Completo {prog}/{total}</span>', unsafe_allow_html=True)
    
    # Alerta e botões para meses faltantes
    if prog < total:
        st.warning("Complete os 3 meses para apurar o trimestre")
        if faltantes:
            cols = st.columns(len(faltantes))
            for idx, m in enumerate(faltantes):
                if m in meses_disp:  # Só mostrar botão se o mês for simulável
                    if cols[idx].button(MESES_PT[m % 100], key=f"goto_{m}"):
                        st.session_state["mes_atual"] = m
                        st.rerun()
    
    # Calcular IRPJ/CSLL do trimestre
    irpj, csll, fechamento = irpj_csll_trimestre(lat_total, tri_key)
    
    # Mostrar IRPJ/CSLL apenas se estivermos no mês de fechamento E o trimestre estiver completo
    col1, col2 = st.columns(2)
    
    if mes_atual == fechamento and prog == total:
        col1.metric(f"IRPJ – {MESES_PT[fechamento % 100]} (trimestre)", fmt_brl(irpj))
        col2.metric(f"CSLL – {MESES_PT[fechamento % 100]} (trimestre)", fmt_brl(csll))
    else:
        col1.metric("IRPJ – trimestre", fmt_brl(0.0))
        col2.metric("CSLL – trimestre", fmt_brl(0.0))
