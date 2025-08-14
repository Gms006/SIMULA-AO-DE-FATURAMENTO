import streamlit as st
import pandas as pd
from io import BytesIO
from datetime import datetime

from calc import (
    realizado_por_mes,
    irpj_csll_trimestre,
    mes_vigente,
    prepare_dataframe,
    MARGENS,
)
from ui_helpers import brl, cenarios_fat_compra, pis_cofins, yyyymm_to_label

st.set_page_config(page_title="Simulação de Faturamento 2025", layout="wide")

# =========================
# CSS (layout corporativo)
# =========================
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

        .metric-grid {display:grid; grid-template-columns: repeat(3,1fr); gap:14px;}
        @media (max-width: 900px){ .metric-grid {grid-template-columns: 1fr; } }

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

        .section {margin-top: 18px; margin-bottom: 6px;}
        .section h3 {margin:0; font-size: 18px;}
        .section .sub {color:#64748B; font-size: 12.5px; margin-top:2px;}

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

# =========================
# Constantes
# =========================
MESES_PT = {
    1: "Jan", 2: "Fev", 3: "Mar", 4: "Abr", 5: "Mai", 6: "Jun",
    7: "Jul", 8: "Ago", 9: "Set", 10: "Out", 11: "Nov", 12: "Dez",
}

# =========================
# Carregamento de dados
# =========================
@st.cache_data(ttl=300)
def load_data() -> pd.DataFrame:
    """
    Leitura automática:
      1) GitHub raw
      2) Arquivo local
      3) Uploader
    """
    url = "https://raw.githubusercontent.com/eduardoveiculos/SIMULA-AO-DE-FATURAMENTO/main/resultado_eduardo_veiculos.xlsx"
    try:
        return pd.read_excel(url, engine="openpyxl")
    except Exception:
        try:
            return pd.read_excel("resultado_eduardo_veiculos.xlsx", engine="openpyxl")
        except Exception:
            return pd.DataFrame()

def to_excel(df: pd.DataFrame) -> bytes:
    buf = BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.to_excel(writer, index=False)
    return buf.getvalue()

# =========================
# Ações de simulação
# =========================
def propagar_lat():
    """Propaga o LAT do mês selecionado para todos os meses posteriores destravados."""
    if "tabela" not in st.session_state:
        return
    df = st.session_state["tabela"].copy()
    mes_sel = st.session_state.get("mes_selecionado", 1)
    idx = mes_sel - 1
    val = df.at[idx, "LAT (R$)"]
    locked = st.session_state.get("meses_travados", [])
    for j in range(idx + 1, 12):
        if (j + 1) not in locked:
            df.at[j, "LAT (R$)"] = val
    st.session_state["tabela"] = df

def zerar_simulacao():
    """Zera valores simulados (mantém realizado nos meses travados)."""
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
            df.at[i, "LAT (R$)"] = realizado.get(mes_num, 0.0)
    st.session_state["tabela"] = df

def preencher_reais_ytd():
    """Preenche (ou restaura) LAT dos meses até o vigente com os valores realizados."""
    if "tabela" not in st.session_state:
        return
    df = st.session_state["tabela"].copy()
    realizado = st.session_state.get("valores_realizados", {})
    mes_vig_num = st.session_state.get("mes_vig_num", 0)
    for i in range(mes_vig_num):
        df.at[i, "LAT (R$)"] = realizado.get(i + 1, 0.0)
    st.session_state["tabela"] = df

# =========================
# Sidebar minimalista
# =========================
with st.sidebar:
    st.header("📊 Simulação")
    ano = st.selectbox("Ano", [2025], index=0, disabled=True)
    sim_vigente = st.checkbox("✏️ Simular mês vigente", value=False,
                              help="Permite editar o mês vigente (soma realizado + simulado)")
    st.divider()
    c1, c2 = st.columns(2)
    if c1.button("📈 Propagar LAT", help="Copia LAT do mês atual para os próximos"):
        propagar_lat()
        st.rerun()
    if c2.button("🗑️ Zerar", type="secondary", help="Remove valores simulados"):
        zerar_simulacao()
        st.rerun()

# =========================
# Dados base e mês vigente
# =========================
df_raw = load_data()
if df_raw.empty:
    st.warning("🔍 Não foi possível carregar os dados automaticamente.")
    uploaded = st.file_uploader("📁 Envie o arquivo resultado_eduardo_veiculos.xlsx", type="xlsx")
    if uploaded:
        df_raw = pd.read_excel(uploaded, engine="openpyxl")
    else:
        st.stop()

df_norm = prepare_dataframe(df_raw)
vigente_yyyymm = mes_vigente(df_norm)  # último yyyymm presente na planilha
mes_vig_num = (vigente_yyyymm % 100) if vigente_yyyymm else 0
st.session_state["mes_vig_num"] = mes_vig_num

# Realizado por mês (dict por yyyymm)
realizado_dict = realizado_por_mes(df_raw)  # {yyyymm: {"FAT", "COMPRAS", "LAT"}}

# =========================
# Inicialização do planejamento (session_state)
# =========================
if "tabela" not in st.session_state:
    st.session_state["tabela"] = pd.DataFrame({
        "Mês": [MESES_PT[i] for i in range(1, 13)],
        "LAT (R$)": pd.Series([None] * 12, dtype="float"),
        "Obs": [""] * 12,
    })

    # Travar meses anteriores ao vigente (se não marcar sim_vigente, inclui o próprio vigente)
    st.session_state["meses_travados"] = (
        list(range(1, mes_vig_num + 1)) if not sim_vigente else list(range(1, mes_vig_num))
    )

    # Guardar realizado (LAT) por mês 1..12
    st.session_state["valores_realizados"] = {}
    for i in range(1, 13):
        yyyymm = 2025 * 100 + i
        lat_real = float(realizado_dict.get(yyyymm, {}).get("LAT", 0.0))
        if i <= mes_vig_num:
            st.session_state["tabela"].at[i - 1, "LAT (R$)"] = lat_real
            st.session_state["valores_realizados"][i] = lat_real

# =========================
# KPIs YTD (somente realizado)
# =========================
def kpis_ytd(realizado_dict: dict, mes_limite: int) -> dict:
    """Calcula KPIs YTD somente com realizado até mes_limite (1..12)."""
    fat = compras = lat = 0.0
    pis = cofins = icms = irpj = csll = 0.0

    # Somatórios mensais (PIS/COFINS sobre LAT; ICMS 5% sobre FAT)
    lat_por_mes = {}
    for m in range(1, mes_limite + 1):
        yyyymm = 2025 * 100 + m
        vals = realizado_dict.get(yyyymm, {"FAT": 0.0, "COMPRAS": 0.0, "LAT": 0.0})
        f, c, l = float(vals["FAT"]), float(vals["COMPRAS"]), float(vals["LAT"])
        fat += f
        compras += c
        lat += l
        p, co = pis_cofins(l)
        pis += p
        cofins += co
        icms += 0.05 * f
        lat_por_mes[yyyymm] = l

    # IRPJ/CSLL somente nos fechamentos já ocorridos
    trib_map = irpj_csll_trimestre(lat_por_mes)
    for ymm, (ir, cs) in trib_map.items():
        mes = ymm % 100
        if mes <= mes_limite:
            irpj += ir
            csll += cs

    ll = lat - (pis + cofins + icms + irpj + csll)
    return {"FAT": fat, "COMPRAS": compras, "LAT": lat, "LL": ll}

if mes_vig_num > 0:
    kpi = kpis_ytd(realizado_dict, mes_vig_num)
    st.markdown('<div class="kpi-grid">', unsafe_allow_html=True)
    st.markdown(
        f'''
        <div class="card"><h4>Entradas YTD</h4><p class="value">{brl(kpi["COMPRAS"])}</p></div>
        <div class="card"><h4>Saídas YTD</h4><p class="value">{brl(kpi["FAT"])}</p></div>
        <div class="card"><h4>LAT YTD</h4><p class="value">{brl(kpi["LAT"])}</p></div>
        <div class="card {'ok' if kpi["LL"] > 0 else 'warn' if kpi["LL"] > -50000 else 'bad'}">
            <h4>Lucro Líquido YTD</h4><p class="value">{brl(kpi["LL"])}</p>
        </div>
        <div class="card"><h4>Mês Vigente</h4><p class="value">{yyyymm_to_label(vigente_yyyymm) if vigente_yyyymm else "—"}</p></div>
        ''',
        unsafe_allow_html=True
    )
    st.markdown('</div>', unsafe_allow_html=True)

# =========================
# Planejamento LAT (tabela editável)
# =========================
st.markdown(
    '<div class="section"><h3>📝 Planejamento LAT 2025</h3>'
    '<div class="sub">Digite o LAT desejado para cada mês. Meses passados estão travados.</div></div>',
    unsafe_allow_html=True
)

# Ações do planejamento
cpa, cpb = st.columns(2)
if cpa.button("↩️ Preencher pelos valores reais YTD"):
    preencher_reais_ytd()
if cpb.button("➡️ Propagar LAT (mês atual → próximos)"):
    propagar_lat()

# Máscara de bloqueio por mês
mask_df = pd.DataFrame(False, index=st.session_state["tabela"].index, columns=st.session_state["tabela"].columns)
for mes_travado in st.session_state["meses_travados"]:
    mask_df.at[mes_travado - 1, "LAT (R$)"] = True

df_editado = st.data_editor(
    st.session_state["tabela"],
    hide_index=True,
    column_config={
        "Mês": st.column_config.TextColumn("Mês", disabled=True, width="small"),
        "LAT (R$)": st.column_config.NumberColumn(
            "LAT (R$)",
            min_value=0.0,
            step=100.0,
            format="R$ %.2f",  # evita sprintf placeholder
            width="medium",
        ),
        "Obs": st.column_config.TextColumn("Obs", width="large"),
    },
    disabled=mask_df,
    num_rows="fixed",
    use_container_width=True,
    key="data_editor",
)
st.session_state["tabela"] = df_editado

# =========================
# Simulação por mês (chips)
# =========================
st.markdown(
    '<div class="section"><h3>🎯 Simulação por Mês</h3>'
    '<div class="sub">Selecione um mês para ver os cenários detalhados</div></div>',
    unsafe_allow_html=True
)

# Meses disponíveis para simulação
if mes_vig_num == 0:
    # fallback (sem dados na planilha): usa o mês atual
    mes_vig_num = datetime.today().month

meses_disponiveis = list(range(mes_vig_num if sim_vigente else mes_vig_num + 1, 13)) or [12]

mes_selecionado = st.segmented_control(
    "Mês para simular:",
    options=list(range(1, 13)),
    default=meses_disponiveis[0],
    format_func=lambda x: MESES_PT[x],
    key="selector_mes",
)
# Fallback robusto caso o widget retorne None (versões específicas do Streamlit)
if mes_selecionado is None:
    mes_selecionado = meses_disponiveis[0]
st.session_state["mes_selecionado"] = mes_selecionado

# =========================
# Cálculos do mês selecionado
# =========================
idx_mes = mes_selecionado - 1
lat_val = st.session_state["tabela"].at[idx_mes, "LAT (R$)"]
lat_simulado = float(lat_val) if pd.notna(lat_val) else 0.0

# Realizado do mês (se for vigente e editável)
fat_real = compras_real = lat_real = 0.0
if (mes_selecionado == mes_vig_num) and sim_vigente:
    ymm = 2025 * 100 + mes_selecionado
    vals = realizado_dict.get(ymm, {"FAT": 0.0, "COMPRAS": 0.0, "LAT": 0.0})
    fat_real = float(vals["FAT"])
    compras_real = float(vals["COMPRAS"])
    lat_real = float(vals["LAT"])
    lat_total = lat_real + lat_simulado
    st.info(
        f"**Mês Vigente**: Realizado LAT {brl(lat_real)} + Simulado LAT {brl(lat_simulado)} "
        f"= **Total LAT {brl(lat_total)}**"
    )
else:
    lat_total = lat_simulado

# =========================
# Cenários e tributos (mês)
# =========================
with st.expander(f"🎲 {MESES_PT[mes_selecionado]} 2025 - Cenários", expanded=True):
    margem_ref = st.segmented_control(
        "Cenário de referência:",
        options=MARGENS,
        default=0.20,
        format_func=lambda x: f"{int(x*100)}%",
        key="margem_referencia",
    )
    # Fallback robusto — em algumas versões o widget pode retornar None no primeiro run
    if margem_ref is None:
        margem_ref = 0.20

    cenarios = cenarios_fat_compra(lat_total)  # usa LAT total (real + sim no vigente)
    pis_mes, cofins_mes = pis_cofins(lat_total)

    ref_idx = int(margem_ref * 100)
    ref_cenario = cenarios[ref_idx]

    st.markdown(f'<div class="section"><h3>Cenário {int(margem_ref*100)}% (Referência)</h3></div>', unsafe_allow_html=True)
    st.markdown('<div class="metric-grid">', unsafe_allow_html=True)
    st.markdown(
        f'''
        <div class="card"><h4>Faturamento</h4><p class="value">{brl(ref_cenario["FAT"])}</p>
        {'<div class="muted">Real: ' + brl(fat_real) + '</div>' if fat_real > 0 else ''}</div>
        <div class="card"><h4>Compras</h4><p class="value">{brl(ref_cenario["COMPRAS"])}</p>
        {'<div class="muted">Real: ' + brl(compras_real) + '</div>' if compras_real > 0 else ''}</div>
        <div class="card"><h4>ICMS (5%)</h4><p class="value">{brl(ref_cenario["ICMS"])}</p></div>
        ''',
        unsafe_allow_html=True
    )
    st.markdown('</div>', unsafe_allow_html=True)

    st.markdown('<div class="section"><h3>Tributos Mensais (Base LAT)</h3></div>', unsafe_allow_html=True)
    st.markdown('<div class="metric-grid">', unsafe_allow_html=True)
    st.markdown(
        f'''
        <div class="card"><h4>PIS (0,65%)</h4><p class="value">{brl(pis_mes)}</p></div>
        <div class="card"><h4>COFINS (3%)</h4><p class="value">{brl(cofins_mes)}</p></div>
        ''',
        unsafe_allow_html=True
    )

    # IRPJ/CSLL apenas nos meses de fechamento (Mar/Jun/Set/Dez)
    if mes_selecionado in [3, 6, 9, 12]:
        lat_anual = {}
        for i in range(12):
            m = i + 1
            ymm = 2025 * 100 + m
            if m < mes_vig_num:
                # meses anteriores: somente realizado
                lat_anual[ymm] = float(st.session_state["valores_realizados"].get(m, 0.0))
            elif (m == mes_vig_num) and sim_vigente:
                # vigente: realizado + simulado
                lat_r = float(st.session_state["valores_realizados"].get(m, 0.0))
                lat_s_val = st.session_state["tabela"].at[i, "LAT (R$)"]
                lat_s = float(lat_s_val) if pd.notna(lat_s_val) else 0.0
                lat_anual[ymm] = lat_r + lat_s
            else:
                # futuros: apenas simulado
                lat_f_val = st.session_state["tabela"].at[i, "LAT (R$)"]
                lat_anual[ymm] = float(lat_f_val) if pd.notna(lat_f_val) else 0.0

        trib_tri = irpj_csll_trimestre(lat_anual)
        irpj_mes, csll_mes = trib_tri.get(2025 * 100 + mes_selecionado, (0.0, 0.0))

        st.markdown(
            f'''
            <div class="card warn"><h4>IRPJ (Trimestre)</h4><p class="value">{brl(irpj_mes)}</p>
            <div class="muted">Fechamento trimestral</div></div>
            ''',
            unsafe_allow_html=True
        )

    # Todos os cenários (cards HTML)
    st.markdown('<div class="section"><h3>Todos os Cenários</h3><div class="sub">Variação de FAT e Compras por margem</div></div>',
                unsafe_allow_html=True)

    cenarios_html = '<div class="kpi-grid">'
    for margem_pct in sorted(cenarios.keys()):
        cen = cenarios[margem_pct]
        classe_css = "ok" if margem_pct >= 20 else "warn" if margem_pct >= 10 else "bad"
        cenarios_html += f'''
            <div class="card {classe_css}">
                <h4>Margem {margem_pct}%</h4>
                <p class="value">{brl(cen["FAT"])}</p>
                <div class="muted">Compras: {brl(cen["COMPRAS"])}</div>
            </div>
        '''
    cenarios_html += '</div>'
    st.markdown(cenarios_html, unsafe_allow_html=True)

# =========================
# Exportação consolidado anual (margem 20% como referência)
# =========================
st.markdown("---")

lat_dict_anual = {}
for i in range(12):
    m = i + 1
    ymm = 2025 * 100 + m
    if (m < mes_vig_num) or ((m == mes_vig_num) and not sim_vigente):
        # realizado puro
        lat_dict_anual[ymm] = float(st.session_state["valores_realizados"].get(m, 0.0))
    elif (m == mes_vig_num) and sim_vigente:
        # vigente: real + simulado
        lat_r = float(st.session_state["valores_realizados"].get(m, 0.0))
        lat_s_val = st.session_state["tabela"].at[i, "LAT (R$)"]
        lat_s = float(lat_s_val) if pd.notna(lat_s_val) else 0.0
        lat_dict_anual[ymm] = lat_r + lat_s
    else:
        # meses futuros: só simulado
        val_future = st.session_state["tabela"].at[i, "LAT (R$)"]
        lat_dict_anual[ymm] = float(val_future) if pd.notna(val_future) else 0.0

tributos_anuais = irpj_csll_trimestre(lat_dict_anual)

rows_consolidado = []
for m in range(1, 13):
    ymm = 2025 * 100 + m
    lat_m = float(lat_dict_anual.get(ymm, 0.0))
    if lat_m > 0:
        fat_m = lat_m / 0.20
        compras_m = fat_m - lat_m
        icms_m = 0.05 * fat_m
    else:
        fat_m = compras_m = icms_m = 0.0
    pis_m, cof_m = pis_cofins(lat_m)
    irpj_m, csll_m = tributos_anuais.get(ymm, (0.0, 0.0))
    ll_m = lat_m - (pis_m + cof_m + icms_m + irpj_m + csll_m)
    rows_consolidado.append({
        "Mês": MESES_PT[m],
        "LAT": lat_m,
        "Faturamento": fat_m,
        "Compras": compras_m,
        "ICMS": icms_m,
        "PIS": pis_m,
        "COFINS": cof_m,
        "IRPJ": irpj_m,
        "CSLL": csll_m,
        "Lucro Líquido": ll_m,
    })

df_consolidado = pd.DataFrame(rows_consolidado)
totals = df_consolidado.sum(numeric_only=True)
totals["Mês"] = "TOTAL"
df_consolidado = pd.concat([df_consolidado, totals.to_frame().T], ignore_index=True)

c1, c2 = st.columns(2)
with c1:
    # Download do mês selecionado (CSV)
    ref20 = cenarios_fat_compra(lat_total).get(20, {"FAT": 0.0, "COMPRAS": 0.0})
    df_mes_sel = pd.DataFrame([{
        "Mês": MESES_PT[mes_selecionado],
        "LAT": lat_total,
        "Cenários": f"Margem 20%: FAT {brl(ref20['FAT'])}, Compras {brl(ref20['COMPRAS'])}",
        "PIS": pis_cofins(lat_total)[0],
        "COFINS": pis_cofins(lat_total)[1],
    }])
    csv_mes = df_mes_sel.to_csv(index=False).encode("utf-8")
    st.download_button(
        f"📄 Baixar {MESES_PT[mes_selecionado]} CSV",
        csv_mes,
        file_name=f"simulacao_{MESES_PT[mes_selecionado].lower()}_2025.csv",
        mime="text/csv",
    )

with c2:
    # Download consolidado anual (XLSX)
    st.download_button(
        "📊 Baixar Consolidado Anual XLSX",
        to_excel(df_consolidado),
        file_name="simulacao_anual_2025.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

with st.expander("👁️ Preview Consolidado Anual", expanded=False):
    df_preview = df_consolidado.copy()
    for col in ["LAT", "Faturamento", "Compras", "ICMS", "PIS", "COFINS", "IRPJ", "CSLL", "Lucro Líquido"]:
        df_preview[col] = df_preview[col].apply(lambda x: brl(x) if pd.notnull(x) else "—")
    st.dataframe(df_preview, use_container_width=True, hide_index=True)
