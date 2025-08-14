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
        "LAT (R$)": pd.Series([None] * 12, dtype="float"),
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
            step=100.0,
            format="R$ %.2f",
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
lat_val = st.session_state["tabela"].at[idx_mes, "LAT (R$)"]
lat_simulado = float(lat_val) if pd.notna(lat_val) else 0.0

# Para o mês vigente, soma realizado + simulado
if mes_selecionado == (mes_vig % 100) and sim_vigente and not realizado.empty:
    lat_real = realizado.at[mes_selecionado, "LAT"] if mes_selecionado in realizado.index else 0.0
    fat_real = realizado.at[mes_selecionado, "FAT"] if mes_selecionado in realizado.index else 0.0
    compras_real = realizado.at[mes_selecionado, "COMPRAS"] if mes_selecionado in realizado.index else 0.0
    
    # Total do mês = realizado + simulado
    lat_total = lat_real + lat_simulado
    
    st.info(f"**Mês Vigente**: Realizado LAT {brl(lat_real)} + Simulado LAT {brl(lat_simulado)} = **Total LAT {brl(lat_total)}**")
else:
    lat_total = lat_simulado
    fat_real = 0.0
    compras_real = 0.0

# =========================
# CENÁRIOS POR MARGEM
# =========================
with st.expander(f"🎲 {MESES_PT[mes_selecionado]} {ano} - Cenários", expanded=True):
    
    # Seletor de margem de referência
    margem_ref = st.segmented_control(
        "Cenário de referência:",
        options=MARGENS,
        default=0.20,
        format_func=lambda x: f"{int(x*100)}%",
        key="margem_referencia"
    )
    
    # Calcula cenários para o LAT total
    cenarios = cenarios_fat_compra(lat_total)
    pis_mes, cofins_mes = pis_cofins(lat_total)
    
    # Cards da margem de referência selecionada
    ref_idx = int(margem_ref * 100)
    ref_cenario = cenarios[ref_idx]
    
    st.markdown(f'<div class="section"><h3>Cenário {int(margem_ref*100)}% (Referência)</h3></div>', unsafe_allow_html=True)
    
    st.markdown('<div class="metric-grid">', unsafe_allow_html=True)
    st.markdown(f'''
        <div class="card"><h4>Faturamento</h4><p class="value">{brl(ref_cenario["FAT"])}</p>
        {'<div class="muted">Real: ' + brl(fat_real) + '</div>' if fat_real > 0 else ''}</div>
        <div class="card"><h4>Compras</h4><p class="value">{brl(ref_cenario["COMPRA"])}</p>
        {'<div class="muted">Real: ' + brl(compras_real) + '</div>' if compras_real > 0 else ''}</div>
        <div class="card"><h4>ICMS (5%)</h4><p class="value">{brl(ref_cenario["ICMS"])}</p></div>
    ''', unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)
    
    # Tributos fixos sobre LAT
    st.markdown('<div class="section"><h3>Tributos Mensais (Base LAT)</h3></div>', unsafe_allow_html=True)
    
    st.markdown('<div class="metric-grid">', unsafe_allow_html=True)
    st.markdown(f'''
        <div class="card"><h4>PIS (0,65%)</h4><p class="value">{brl(pis_mes)}</p></div>
        <div class="card"><h4>COFINS (3%)</h4><p class="value">{brl(cofins_mes)}</p></div>
    ''', unsafe_allow_html=True)
    
    # IRPJ/CSLL apenas nos meses de fechamento trimestral
    if mes_selecionado in [3, 6, 9, 12]:  # Mar, Jun, Set, Dez
        # Constrói LAT de todo o ano para cálculo trimestral
        lat_anual = {}
        for i in range(12):
            mes_num = i + 1
            yyyymm = 2025 * 100 + mes_num
            
            if mes_num <= (mes_vig % 100) and not sim_vigente:
                # Mês já realizado
                lat_anual[yyyymm] = st.session_state["valores_realizados"].get(mes_num, 0.0)
            elif mes_num == (mes_vig % 100) and sim_vigente:
                # Mês vigente: realizado + simulado
                lat_r = st.session_state["valores_realizados"].get(mes_num, 0.0)
                lat_val2 = st.session_state["tabela"].at[i, "LAT (R$)"]
                lat_s = float(lat_val2) if pd.notna(lat_val2) else 0.0
                lat_anual[yyyymm] = lat_r + lat_s
            else:
                # Mês futuro: apenas simulado
                val_fut = st.session_state["tabela"].at[i, "LAT (R$)"]
                lat_anual[yyyymm] = float(val_fut) if pd.notna(val_fut) else 0.0
        
        # Calcula IRPJ/CSLL do trimestre
        tributos_tri = irpj_csll_trimestre(lat_anual)
        irpj_mes, csll_mes = tributos_tri.get(2025 * 100 + mes_selecionado, (0.0, 0.0))
        
        st.markdown(f'''
            <div class="card warn"><h4>IRPJ (Trimestre)</h4><p class="value">{brl(irpj_mes)}</p>
            <div class="muted">Fechamento trimestral</div></div>
        ''', unsafe_allow_html=True)
    
    st.markdown('</div>', unsafe_allow_html=True)
    
    # Resumo de todos os cenários
    st.markdown('<div class="section"><h3>Todos os Cenários</h3><div class="sub">Variação de FAT e Compras por margem</div></div>', unsafe_allow_html=True)
    
    cenarios_html = '<div class="kpi-grid">'
    for margem_pct in sorted(cenarios.keys()):
        cen = cenarios[margem_pct]
        classe_css = "ok" if margem_pct >= 20 else "warn" if margem_pct >= 10 else "bad"
        cenarios_html += f'''
            <div class="card {classe_css}">
                <h4>Margem {margem_pct}%</h4>
                <p class="value">{brl(cen["FAT"])}</p>
                <div class="muted">Compras: {brl(cen["COMPRA"])}</div>
            </div>
        '''
    cenarios_html += '</div>'
    
    st.markdown(cenarios_html, unsafe_allow_html=True)

# =========================
# EXPORTAÇÃO
# =========================
st.markdown("---")

# Prepara dados para exportação
lat_dict_anual = {}
for i in range(12):
    mes_num = i + 1
    yyyymm = 2025 * 100 + mes_num
    
    if mes_num <= (mes_vig % 100) and not sim_vigente:
        # Realizado
        lat_dict_anual[yyyymm] = st.session_state["valores_realizados"].get(mes_num, 0.0)
    elif mes_num == (mes_vig % 100) and sim_vigente:
        # Vigente: real + simulado
        lat_r = st.session_state["valores_realizados"].get(mes_num, 0.0)
        lat_val3 = st.session_state["tabela"].at[i, "LAT (R$)"]
        lat_s = float(lat_val3) if pd.notna(lat_val3) else 0.0
        lat_dict_anual[yyyymm] = lat_r + lat_s
    else:
        # Futuro: simulado
        val_future = st.session_state["tabela"].at[i, "LAT (R$)"]
        lat_dict_anual[yyyymm] = float(val_future) if pd.notna(val_future) else 0.0

# Calcula IRPJ/CSLL anuais
tributos_anuais = irpj_csll_trimestre(lat_dict_anual)

# Monta DataFrame consolidado (margem 20% como padrão)
rows_consolidado = []
for mes_num in range(1, 13):
    yyyymm = 2025 * 100 + mes_num
    lat = lat_dict_anual.get(yyyymm, 0.0)
    
    # Cenários com margem 20%
    if lat > 0:
        fat = lat / 0.20
        compras = fat - lat
        icms = 0.05 * fat
    else:
        fat = compras = icms = 0.0
    
    # Tributos
    pis = 0.0065 * lat
    cofins = 0.03 * lat
    irpj, csll = tributos_anuais.get(yyyymm, (0.0, 0.0))
    
    lucro_liquido = lat - (pis + cofins + icms + irpj + csll)
    
    rows_consolidado.append({
        "Mês": MESES_PT[mes_num],
        "LAT": lat,
        "Faturamento": fat,
        "Compras": compras,
        "ICMS": icms,
        "PIS": pis,
        "COFINS": cofins,
        "IRPJ": irpj,
        "CSLL": csll,
        "Lucro Líquido": lucro_liquido,
    })

df_consolidado = pd.DataFrame(rows_consolidado)

# Adiciona linha de totais
totals = df_consolidado.sum(numeric_only=True)
totals["Mês"] = "TOTAL"
df_consolidado = pd.concat([df_consolidado, totals.to_frame().T], ignore_index=True)

col1, col2 = st.columns(2)

with col1:
    # Download do mês selecionado
    df_mes_sel = pd.DataFrame([{
        "Mês": MESES_PT[mes_selecionado],
        "LAT": lat_total,
        "Cenários": f"Margem 20%: FAT {brl(ref_cenario['FAT'])}, Compras {brl(ref_cenario['COMPRA'])}",
        "PIS": pis_mes,
        "COFINS": cofins_mes,
    }])
    
    csv_mes = df_mes_sel.to_csv(index=False).encode("utf-8")
    st.download_button(
        f"📄 Baixar {MESES_PT[mes_selecionado]} CSV",
        csv_mes,
        file_name=f"simulacao_{MESES_PT[mes_selecionado].lower()}_2025.csv",
        mime="text/csv"
    )

with col2:
    # Download consolidado anual
    st.download_button(
        "📊 Baixar Consolidado Anual XLSX",
        to_excel(df_consolidado),
        file_name="simulacao_anual_2025.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

# Exibe preview do consolidado
with st.expander("👁️ Preview Consolidado Anual", expanded=False):
    # Formatar para exibição
    df_preview = df_consolidado.copy()
    cols_money = ["LAT", "Faturamento", "Compras", "ICMS", "PIS", "COFINS", "IRPJ", "CSLL", "Lucro Líquido"]
    for col in cols_money:
        df_preview[col] = df_preview[col].apply(lambda x: brl(x) if pd.notnull(x) else "—")
    
    st.dataframe(df_preview, use_container_width=True, hide_index=True)
