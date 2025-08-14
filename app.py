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
# CSS (estilo próximo ao design do outro app)
# =========================
def inject_css():
    st.markdown(
        """
        <style>
        .app-container {max-width: 1280px; margin: 0 auto;}
        section.main > div {padding-top: 0.25rem;}

        .kpi-grid {display: grid; grid-template-columns: repeat(5, 1fr); gap: 14px;}
        @media (max-width: 1200px){ .kpi-grid {grid-template-columns: repeat(3, 1fr);} }
        @media (max-width: 780px){ .kpi-grid {grid-template-columns: repeat(2, 1fr);} }
        @media (max-width: 520px){ .kpi-grid {grid-template-columns: 1fr;} }

        .metric-grid {display:grid; grid-template-columns: repeat(3,1fr); gap:14px;}
        @media (max-width: 900px){ .metric-grid {grid-template-columns: 1fr; } }

        .panel {border:1px solid #E5E7EB; background:#FFFFFF; border-radius:12px; padding:14px 16px; box-shadow: 0 2px 6px rgba(15,23,42,.05);}
        .panel h4 {margin:0 0 6px 0; font-size:13px; color:#475569; text-transform:uppercase; letter-spacing:.2px;}
        .panel .label {font-size:12px; color:#64748B; margin-bottom:4px;}
        .panel .row {display:grid; grid-template-columns: 1fr 1fr; gap:12px;}
        .panel .muted { color:#64748B; font-size: 12px; margin-top: 4px; }

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

        /* Dark look (similar ao segundo screenshot) */
        @media (prefers-color-scheme: dark){
            .panel, .card { background:#0B1220; border-color:#1F2937; }
            .panel h4, .card h4 { color:#94A3B8; }
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
MESES_PT = {1:"Jan",2:"Fev",3:"Mar",4:"Abr",5:"Mai",6:"Jun",7:"Jul",8:"Ago",9:"Set",10:"Out",11:"Nov",12:"Dez"}

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
# Sidebar minimalista
# =========================
with st.sidebar:
    st.header("📊 Simulação")
    ano = st.selectbox("Ano", [2025], index=0, disabled=True)
    sim_vigente = st.checkbox("✏️ Simular mês vigente", value=False,
                              help="Permite editar o mês vigente (soma realizado + simulado)")
    st.divider()
    c1, c2 = st.columns(2)
    if c1.button("📈 Propagar LAT", help="Copia o LAT do mês selecionado (abaixo) para os próximos meses editáveis"):
        st.session_state["__propagar__"] = True
        st.rerun()
    if c2.button("🗑️ Zerar simulação", type="secondary", help="Zera apenas meses editáveis (mantém realizado nos travados)"):
        st.session_state["__zerar__"] = True
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

# Realizado por mês (dict por yyyymm)
realizado_dict = realizado_por_mes(df_raw)  # {yyyymm: {"FAT", "COMPRAS", "LAT"}}

# =========================
# Estado do planejamento (LAT simulado por mês)
# =========================
if "lat_plan" not in st.session_state:
    st.session_state["lat_plan"] = {}
    # Pré-preenche: meses < vigente ficam com LAT Real (somente leitura), demais 0.0
    for m in range(1, 13):
        ymm = 2025 * 100 + m
        if m < mes_vig_num:
            st.session_state["lat_plan"][ymm] = float(realizado_dict.get(ymm, {}).get("LAT", 0.0))
        elif m == mes_vig_num and not sim_vigente:
            st.session_state["lat_plan"][ymm] = float(realizado_dict.get(ymm, {}).get("LAT", 0.0))
        else:
            st.session_state["lat_plan"][ymm] = 0.0

# Ações globais vindas do sidebar
if st.session_state.pop("__zerar__", False):
    for m in range(1,13):
        ymm = 2025*100+m
        editavel = (m > mes_vig_num) or (m == mes_vig_num and sim_vigente)
        if editavel:
            st.session_state["lat_plan"][ymm] = 0.0

# =========================
# KPIs YTD (somente realizado)
# =========================
def kpis_ytd(realizado_dict: dict, mes_limite: int) -> dict:
    fat = compras = lat = 0.0
    pis = cofins = icms = irpj = csll = 0.0
    lat_por_mes = {}
    for m in range(1, mes_limite + 1):
        ymm = 2025 * 100 + m
        vals = realizado_dict.get(ymm, {"FAT": 0.0, "COMPRAS": 0.0, "LAT": 0.0})
        f, c, l = float(vals["FAT"]), float(vals["COMPRAS"]), float(vals["LAT"])
        fat += f; compras += c; lat += l
        p, co = pis_cofins(l); pis += p; cofins += co
        icms += 0.05 * f
        lat_por_mes[ymm] = l
    trib_map = irpj_csll_trimestre(lat_por_mes)
    for ymm, (ir, cs) in trib_map.items():
        mes = ymm % 100
        if mes <= mes_limite:
            irpj += ir; csll += cs
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
# Planejamento LAT – estilo "steppers" por mês
# =========================
st.markdown(
    '<div class="section"><h3>📝 Planejamento LAT 2025</h3>'
    '<div class="sub">Digite o LAT de cada mês. Meses anteriores ao vigente ficam bloqueados; '
    'o vigente só é editável se a opção estiver marcada no menu.</div></div>',
    unsafe_allow_html=True
)

# Mês selecionado para simulação (usado também pela ação Propagar)
if "mes_selecionado" not in st.session_state:
    st.session_state["mes_selecionado"] = mes_vig_num if mes_vig_num > 0 else 1

# Renderiza expanders por mês (design similar ao do outro app)
for m in range(1, 13):
    ymm = 2025 * 100 + m
    is_locked = (m < mes_vig_num) or (m == mes_vig_num and not sim_vigente)
    default_val = float(st.session_state["lat_plan"].get(ymm, 0.0))

    with st.expander(f"{MESES_PT[m]}/2025", expanded=(m == st.session_state["mes_selecionado"])):
        st.markdown('<div class="panel">', unsafe_allow_html=True)
        st.markdown(f'<h4>LAT (R$)</h4><div class="label">{"Travado (somente realizado)" if is_locked else "Informe o LAT do mês"}</div>', unsafe_allow_html=True)
        val = st.number_input(
            label="",
            min_value=0.0,
            step=100.0,
            format="%.2f",
            value=default_val,
            key=f"lat_input_{ymm}",
            disabled=is_locked
        )
        # Atualiza estado se editável
        if not is_locked:
            st.session_state["lat_plan"][ymm] = float(val)

        # Se foi pedida a propagação a partir deste mês
        if st.session_state.pop("__propagar__", False) and (m == st.session_state["mes_selecionado"]):
            base = float(st.session_state["lat_plan"][ymm])
            for k in range(m + 1, 13):
                ymm2 = 2025 * 100 + k
                is_locked2 = (k < mes_vig_num) or (k == mes_vig_num and not sim_vigente)
                if not is_locked2:
                    st.session_state["lat_plan"][ymm2] = base
                    st.session_state[f"lat_input_{ymm2}"] = base  # reflete no widget
            st.success("Valores propagados para os meses futuros editáveis.")

        # Botões locais
        colA, colB = st.columns(2)
        if colA.button("Usar LAT Real (se houver)", key=f"fill_real_{ymm}"):
            lat_real = float(realizado_dict.get(ymm, {}).get("LAT", 0.0))
            st.session_state["lat_plan"][ymm] = lat_real
            st.session_state[f"lat_input_{ymm}"] = lat_real
        if colB.button("Copiar para os próximos", key=f"copy_next_{ymm}"):
            base = float(st.session_state["lat_plan"][ymm])
            for k in range(m + 1, 13):
                ymm2 = 2025 * 100 + k
                is_locked2 = (k < mes_vig_num) or (k == mes_vig_num and not sim_vigente)
                if not is_locked2:
                    st.session_state["lat_plan"][ymm2] = base
                    st.session_state[f"lat_input_{ymm2}"] = base
            st.success("Valores copiados para os próximos meses editáveis.")
        st.markdown('</div>', unsafe_allow_html=True)

# =========================
# Simulação por Mês (chips) + cards
# =========================
st.markdown(
    '<div class="section"><h3>🎯 Simulação por Mês</h3>'
    '<div class="sub">Selecione um mês para visualizar os cenários e tributos</div></div>',
    unsafe_allow_html=True
)

mes_selecionado = st.segmented_control(
    "Mês para simular:",
    options=list(range(1, 13)),
    default=st.session_state["mes_selecionado"],
    format_func=lambda x: MESES_PT[x],
    key="selector_mes",
)
if mes_selecionado is None:
    mes_selecionado = st.session_state["mes_selecionado"]
st.session_state["mes_selecionado"] = mes_selecionado

# Cálculos do mês selecionado
idx_mes = mes_selecionado - 1
ymm_sel = 2025 * 100 + mes_selecionado
lat_simulado = float(st.session_state["lat_plan"].get(ymm_sel, 0.0))
vals_real = realizado_dict.get(ymm_sel, {"FAT": 0.0, "COMPRAS": 0.0, "LAT": 0.0})
lat_real = float(vals_real["LAT"])
fat_real = float(vals_real["FAT"])
compras_real = float(vals_real["COMPRAS"])

if mes_selecionado < mes_vig_num:
    lat_total = lat_real  # meses passados: somente realizado
elif mes_selecionado == mes_vig_num:
    lat_total = (lat_real + lat_simulado) if sim_vigente else lat_real
else:
    lat_total = lat_simulado  # meses futuros: somente simulado

if (mes_selecionado == mes_vig_num) and sim_vigente:
    st.info(
        f"**Mês Vigente**: Realizado LAT {brl(lat_real)} + Simulado LAT {brl(lat_simulado)} "
        f"= **Total LAT {brl(lat_total)}**"
    )

# Cenários e tributos
with st.expander(f"🎲 {MESES_PT[mes_selecionado]} 2025 - Cenários", expanded=True):
    margem_ref = st.segmented_control(
        "Cenário de referência:",
        options=MARGENS,
        default=0.20,
        format_func=lambda x: f"{int(x*100)}%",
        key="margem_referencia",
    )
    if margem_ref is None:
        margem_ref = 0.20

    cenarios = cenarios_fat_compra(lat_total)
    pis_mes, cofins_mes = pis_cofins(lat_total)

    ref_idx = int(margem_ref * 100)
    ref_cenario = cenarios[ref_idx]

    st.markdown(f'<div class="section"><h3>Cenário {int(margem_ref*100)}% (Referência)</h3></div>', unsafe_allow_html=True)
    st.markdown('<div class="metric-grid">', unsafe_allow_html=True)
    st.markdown(
        f'''
        <div class="card"><h4>Faturamento (projetado)</h4><p class="value">{brl(ref_cenario["FAT"])}</p>
        {'<div class="muted">Real: ' + brl(fat_real) + '</div>' if fat_real > 0 else ''}</div>
        <div class="card"><h4>Compras (projetadas)</h4><p class="value">{brl(ref_cenario["COMPRAS"])}</p>
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
        for i in range(1, 13):
            ymm = 2025 * 100 + i
            lat_r = float(realizado_dict.get(ymm, {}).get("LAT", 0.0))
            if i < mes_vig_num:
                lat_anual[ymm] = lat_r
            elif i == mes_vig_num:
                lat_anual[ymm] = lat_r + (float(st.session_state["lat_plan"].get(ymm, 0.0)) if sim_vigente else 0.0)
            else:
                lat_anual[ymm] = float(st.session_state["lat_plan"].get(ymm, 0.0))

        trib_tri = irpj_csll_trimestre(lat_anual)
        irpj_mes, csll_mes = trib_tri.get(ymm_sel, (0.0, 0.0))

        st.markdown(
            f'''
            <div class="card warn"><h4>IRPJ (Trimestre)</h4><p class="value">{brl(irpj_mes)}</p>
            <div class="muted">Fechamento trimestral</div></div>
            ''',
            unsafe_allow_html=True
        )

    # Todos os cenários (cards HTML)
    st.markdown('<div class="section"><h3>Todos os Cenários</h3><div class="sub">FAT e Compras projetados por margem</div></div>',
                unsafe_allow_html=True)

    cards = []
    for margem_pct in sorted(cenarios.keys()):
        cen = cenarios[margem_pct]
        classe_css = "ok" if margem_pct >= 20 else "warn" if margem_pct >= 10 else "bad"
        cards.append(
            f'''
            <div class="card {classe_css}">
                <h4>Margem {margem_pct}%</h4>
                <p class="value">{brl(cen["FAT"])}</p>
                <div class="muted">Compras: {brl(cen["COMPRAS"])}</div>
            </div>
            '''
        )
    cenarios_html = f'<div class="kpi-grid">{"".join(cards)}</div>'
    st.markdown(cenarios_html, unsafe_allow_html=True)

# =========================
# Exportação consolidado anual (margem 20% como referência)
# =========================
st.markdown("---")

lat_dict_anual = {}
for i in range(1, 13):
    ymm = 2025 * 100 + i
    lat_r = float(realizado_dict.get(ymm, {}).get("LAT", 0.0))
    if i < mes_vig_num:
        lat_dict_anual[ymm] = lat_r
    elif i == mes_vig_num:
        lat_dict_anual[ymm] = lat_r + (float(st.session_state["lat_plan"].get(ymm, 0.0)) if sim_vigente else 0.0)
    else:
        lat_dict_anual[ymm] = float(st.session_state["lat_plan"].get(ymm, 0.0))

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
        "FAT (20%)": ref20["FAT"],
        "Compras (20%)": ref20["COMPRAS"],
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
    def _to_excel_bytes(df):
        buf = BytesIO()
        with pd.ExcelWriter(buf, engine="openpyxl") as w:
            df.to_excel(w, index=False)
        return buf.getvalue()

    st.download_button(
        "📊 Baixar Consolidado Anual XLSX",
        _to_excel_bytes(df_consolidado),
        file_name="simulacao_anual_2025.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

with st.expander("👁️ Preview Consolidado Anual", expanded=False):
    df_preview = df_consolidado.copy()
    for col in ["LAT", "Faturamento", "Compras", "ICMS", "PIS", "COFINS", "IRPJ", "CSLL", "Lucro Líquido"]:
        df_preview[col] = df_preview[col].apply(lambda x: brl(x) if pd.notnull(x) else "—")
    st.dataframe(df_preview, use_container_width=True, hide_index=True)
