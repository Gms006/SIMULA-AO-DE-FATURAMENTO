import streamlit as st
import pandas as pd
from io import BytesIO
from datetime import datetime

from calc import (
    realizado_por_mes,      # DataFrame OU dict por yyyymm -> {FAT, COMPRAS, LAT}
    irpj_csll_trimestre,    # cálculo trimestral (usa dict {yyyymm: LAT})
    MARGENS,
)
from ui_helpers import brl, pis_cofins, yyyymm_to_label

st.set_page_config(page_title="Simulação de Faturamento 2025", layout="wide")

# =========================
# CSS (layout corporativo, AA)
# =========================
def inject_css():
    st.markdown(
        """
<style>
.app-container{max-width:1280px;margin:0 auto;}
section.main>div{padding-top:.25rem;}
.kpi-grid{display:grid;grid-template-columns:repeat(5,1fr);gap:14px;}
@media (max-width:1200px){.kpi-grid{grid-template-columns:repeat(3,1fr)}}
@media (max-width:780px){.kpi-grid{grid-template-columns:repeat(2,1fr)}}
@media (max-width:520px){.kpi-grid{grid-template-columns:1fr}}
.metric-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:14px;}
@media (max-width:900px){.metric-grid{grid-template-columns:1fr}}
.panel{border:1px solid #E5E7EB;background:#FFF;border-radius:12px;padding:14px 16px;box-shadow:0 2px 6px rgba(15,23,42,.05)}
.panel h4{margin:0 0 6px 0;font-size:13px;color:#334155;text-transform:uppercase;letter-spacing:.2px}
.panel .label{font-size:12px;color:#475569;margin-bottom:4px}
.panel .muted{color:#64748B;font-size:12px;margin-top:4px}
.card{border:1px solid #E5E7EB;background:#FFF;border-radius:12px;padding:16px 16px 14px;box-shadow:0 2px 6px rgba(15,23,42,.05)}
.card h4{font-size:12.5px;font-weight:700;letter-spacing:.3px;color:#334155;margin:0 0 6px 0;text-transform:uppercase}
.card .value{font-variant-numeric:tabular-nums;font-weight:800;font-size:26px;color:#0F172A;margin:0}
.muted{color:#475569;font-size:12px;margin-top:4px}
.ok{border-color:#D1FAE5;background:#ECFDF5}
.warn{border-color:#FEF3C7;background:#FFFBEB}
.bad{border-color:#FEE2E2;background:#FEF2F2}
.section{margin-top:18px;margin-bottom:6px}
.section h3{margin:0;font-size:18px}
.section .sub{color:#475569;font-size:12.5px;margin-top:2px}
@media (prefers-color-scheme:dark){
 .panel,.card{background:#0B1220;border-color:#1F2937}
 .panel h4,.card h4{color:#CBD5E1}
 .card .value{color:#E2E8F0}
 .muted{color:#94A3B8}
 .ok{background:#052E2B}
 .warn{background:#2B2412}
 .bad{background:#2B1111}
}
</style>
        """,
        unsafe_allow_html=True,
    )

inject_css()

# =========================
# Util
# =========================
MESES_PT = {1:"Jan",2:"Fev",3:"Mar",4:"Abr",5:"Mai",6:"Jun",7:"Jul",8:"Ago",9:"Set",10:"Out",11:"Nov",12:"Dez"}

@st.cache_data(ttl=300)
def load_data() -> pd.DataFrame:
    url = "https://raw.githubusercontent.com/eduardoveiculos/SIMULA-AO-DE-FATURAMENTO/main/resultado_eduardo_veiculos.xlsx"
    try:
        return pd.read_excel(url, engine="openpyxl")
    except Exception:
        try:
            return pd.read_excel("resultado_eduardo_veiculos.xlsx", engine="openpyxl")
        except Exception:
            return pd.DataFrame()

def to_excel_bytes(df: pd.DataFrame) -> bytes:
    buf = BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        df.to_excel(w, index=False)
    return buf.getvalue()

def ensure_realizado_df(r, ano: int = 2025) -> pd.DataFrame:
    """
    Normaliza o retorno de realizado_por_mes para um DataFrame com:
    index = 1..12 (mês), colunas: FAT, COMPRAS, LAT, yyyymm.
    Aceita tanto DataFrame quanto dict {yyyymm -> {FAT,COMPRAS,LAT}}.
    """
    if isinstance(r, pd.DataFrame):
        df = r.copy()
        for col in ["FAT", "COMPRAS", "LAT"]:
            if col not in df.columns:
                df[col] = 0.0
        if "yyyymm" in df.columns:
            df["yyyymm"] = pd.to_numeric(df["yyyymm"], errors="coerce").fillna(0).astype(int)
            df["mes"] = df["yyyymm"] % 100
            df = df.set_index("mes").sort_index()
        elif "mes" in df.columns:
            df = df.set_index("mes").sort_index()
            if "yyyymm" not in df.columns:
                df["yyyymm"] = [ano * 100 + m for m in df.index]
        else:
            if "yyyymm" not in df.columns:
                df["yyyymm"] = [ano * 100 + m for m in df.index]
        return df[["FAT", "COMPRAS", "LAT", "yyyymm"]]
    else:
        df = pd.DataFrame.from_dict(r, orient="index")
        df = df.rename_axis("key").reset_index()
        df["key_num"] = pd.to_numeric(df["key"], errors="coerce")
        if (df["key_num"] >= 1000).any():
            df["yyyymm"] = df["key_num"].astype("Int64")
            df["mes"] = (df["yyyymm"] % 100).astype(int)
        else:
            df["mes"] = df["key_num"].fillna(0).astype(int)
            df["yyyymm"] = ano * 100 + df["mes"]
        for col in ["FAT", "COMPRAS", "LAT"]:
            if col not in df.columns:
                df[col] = 0.0
        out = df.set_index("mes").sort_index()[["FAT", "COMPRAS", "LAT", "yyyymm"]]
        for col in ["FAT", "COMPRAS", "LAT"]:
            out[col] = pd.to_numeric(out[col], errors="coerce").fillna(0.0).astype(float)
        out["yyyymm"] = out["yyyymm"].astype(int)
        return out

# =========================
# Sidebar minimalista
# =========================
with st.sidebar:
    st.header("📊 Simulação")
    ano = st.selectbox("Ano", [2025], index=0, disabled=True)
    sim_vigente = st.checkbox(
        "✏️ Simular mês vigente",
        value=True,
        help="Permite editar o mês vigente somando o valor simulado ao realizado."
    )
    st.divider()
    c1, c2 = st.columns(2)
    if c1.button("📈 Propagar LAT", help="Copia o LAT do mês selecionado para os próximos editáveis"):
        st.session_state["__propagar__"] = True
        st.rerun()
    if c2.button("🗑️ Zerar simulação", type="secondary", help="Zera apenas os meses editáveis"):
        st.session_state["__zerar__"] = True
        st.rerun()

# =========================
# Dados base + realizado + vigente (robusto a DF/dict)
# =========================
df_raw = load_data()
if df_raw.empty:
    st.warning("🔍 Não foi possível carregar os dados automaticamente.")
    upl = st.file_uploader("📁 Envie o arquivo resultado_eduardo_veiculos.xlsx", type="xlsx")
    if upl:
        df_raw = pd.read_excel(upl, engine="openpyxl")
    else:
        st.stop()

rpm_raw = realizado_por_mes(df_raw)            # DataFrame OU dict
realizado_df = ensure_realizado_df(rpm_raw)    # DataFrame normalizado

# mês vigente = MAIOR yyyymm com FAT > 0
vigente_yyyymm = int(realizado_df.loc[realizado_df["FAT"] > 0, "yyyymm"].max()) if not realizado_df.empty else 0
mes_vig_num = (vigente_yyyymm % 100) if vigente_yyyymm else 0
if mes_vig_num == 0:
    mes_vig_num = datetime.today().month
    vigente_yyyymm = 2025 * 100 + mes_vig_num

def val_real(mes: int, col: str) -> float:
    try:
        return float(realizado_df.at[mes, col]) if mes in realizado_df.index else 0.0
    except Exception:
        return 0.0

# =========================
# Estado do planejamento (LAT simulado por mês)
# =========================
if "lat_plan" not in st.session_state:
    st.session_state["lat_plan"] = {2025*100+m: 0.0 for m in range(1, 13)}

if st.session_state.pop("__zerar__", False):
    for m in range(1, 13):
        editavel = (m > mes_vig_num) or (m == mes_vig_num and sim_vigente)
        if editavel:
            st.session_state["lat_plan"][2025*100+m] = 0.0

# =========================
# KPIs YTD (somente realizado)
# =========================
if not realizado_df.empty:
    ytd_fat = float(realizado_df.loc[1:mes_vig_num, "FAT"].sum())
    ytd_compras = float(realizado_df.loc[1:mes_vig_num, "COMPRAS"].sum())
    ytd_lat = float(realizado_df.loc[1:mes_vig_num, "LAT"].sum())
    pis_ytd = cof_ytd = icms_ytd = 0.0
    lat_dict_ytd = {}
    for m in range(1, mes_vig_num+1):
        l = val_real(m, "LAT")
        f = val_real(m, "FAT")
        p, c = pis_cofins(l)
        pis_ytd += p
        cof_ytd += c
        icms_ytd += 0.05 * f
        lat_dict_ytd[2025*100+m] = l
    irpj_ytd = csll_ytd = 0.0
    for ymm, (ir, cs) in irpj_csll_trimestre(lat_dict_ytd).items():
        if ymm % 100 <= mes_vig_num:
            irpj_ytd += ir
            csll_ytd += cs
    ll_ytd = ytd_lat - (pis_ytd + cof_ytd + icms_ytd + irpj_ytd + csll_ytd)

    html_kpis = (
        '<div class="kpi-grid">'
        f'<div class="card"><h4>Entradas YTD</h4><p class="value">{brl(ytd_compras)}</p></div>'
        f'<div class="card"><h4>Saídas YTD</h4><p class="value">{brl(ytd_fat)}</p></div>'
        f'<div class="card"><h4>LAT YTD</h4><p class="value">{brl(ytd_lat)}</p></div>'
        f'<div class="card {"ok" if ll_ytd>0 else "warn" if ll_ytd>-50000 else "bad"}"><h4>Lucro Líquido YTD</h4><p class="value">{brl(ll_ytd)}</p></div>'
        f'<div class="card"><h4>Mês Vigente</h4><p class="value">{yyyymm_to_label(vigente_yyyymm)}</p></div>'
        '</div>'
    )
    st.markdown(html_kpis, unsafe_allow_html=True)

# =========================
# Planejamento LAT – editor por mês (aceita negativos)
# =========================
st.markdown(
    '<div class="section"><h3>📝 Planejamento LAT 2025</h3>'
    '<div class="sub">Meses anteriores ao vigente ficam travados; o vigente soma o simulado ao realizado quando “Simular mês vigente” estiver ativo.</div></div>',
    unsafe_allow_html=True
)

if "mes_selecionado" not in st.session_state:
    st.session_state["mes_selecionado"] = mes_vig_num or 1

for m in range(1, 13):
    ymm = 2025*100 + m
    is_locked = (m < mes_vig_num) or (m == mes_vig_num and not sim_vigente)
    lat_real_m = val_real(m, "LAT")
    default_val = float(st.session_state["lat_plan"].get(ymm, 0.0))

    with st.expander(f"{MESES_PT[m]}/2025", expanded=(m == st.session_state["mes_selecionado"])):
        st.markdown('<div class="panel">', unsafe_allow_html=True)
        if is_locked:
            st.markdown('<h4>LAT (Realizado)</h4>', unsafe_allow_html=True)
            st.markdown(f'<div class="value" style="font-size:22px;font-weight:800;">{brl(lat_real_m)}</div>', unsafe_allow_html=True)
            st.markdown('<div class="muted">Mês travado — sem simulação.</div>', unsafe_allow_html=True)
        else:
            st.markdown('<h4>LAT Simulado (pode ser negativo)</h4><div class="label">Informe o LAT adicional/ajustado do mês</div>', unsafe_allow_html=True)
            # Aceita negativos → sem min_value
            val = st.number_input(
                label="",
                step=100.0,
                format="%.2f",
                value=float(default_val),
                key=f"lat_input_{ymm}",
            )
            st.session_state["lat_plan"][ymm] = float(val)
            colA, colB = st.columns(2)
            if colA.button("Copiar para os próximos", key=f"copy_next_{ymm}"):
                base = float(st.session_state["lat_plan"][ymm])
                for k in range(m+1, 13):
                    ymm2 = 2025*100 + k
                    is_locked2 = (k < mes_vig_num) or (k == mes_vig_num and not sim_vigente)
                    if not is_locked2:
                        st.session_state["lat_plan"][ymm2] = base
                        st.session_state[f"lat_input_{ymm2}"] = base
                st.success("Valores copiados para os próximos meses editáveis.")
            if colB.button("Usar LAT Real (se houver)", key=f"use_real_{ymm}"):
                if m == mes_vig_num and sim_vigente:
                    st.info(f"LAT realizado {brl(lat_real_m)} será somado ao simulado na simulação.")
                else:
                    st.session_state["lat_plan"][ymm] = lat_real_m
                    st.session_state[f"lat_input_{ymm}"] = lat_real_m
        st.markdown('</div>', unsafe_allow_html=True)

# Propagação global (a partir do mês selecionado)
if st.session_state.pop("__propagar__", False):
    m = st.session_state["mes_selecionado"]
    base = float(st.session_state["lat_plan"][2025*100 + m])
    for k in range(m+1, 13):
        ymm2 = 2025*100 + k
        is_locked2 = (k < mes_vig_num) or (k == mes_vig_num and not sim_vigente)
        if not is_locked2:
            st.session_state["lat_plan"][ymm2] = base
            st.session_state[f"lat_input_{ymm2}"] = base
    st.success("Valores propagados para os meses futuros editáveis.")

# =========================
# Simulação por Mês (somente vigente + futuros)
# =========================
st.markdown(
    '<div class="section"><h3>🎯 Simulação por Mês</h3>'
    '<div class="sub">A simulação por margem vale para o mês vigente (somando o realizado) e para os meses futuros.</div></div>',
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

# Determina LAT_total
lat_sim = float(st.session_state["lat_plan"][2025*100 + mes_selecionado])
lat_real_sel = val_real(mes_selecionado, "LAT")
fat_real_sel = val_real(mes_selecionado, "FAT")
compras_real_sel = val_real(mes_selecionado, "COMPRAS")

is_past = mes_selecionado < mes_vig_num
is_vig = mes_selecionado == mes_vig_num
is_future = mes_selecionado > mes_vig_num

if is_past:
    st.info("Mês anterior ao vigente: apenas realizado (sem cenários).")
    lat_total = lat_real_sel
elif is_vig:
    lat_total = lat_real_sel + (lat_sim if sim_vigente else 0.0)
else:
    lat_total = lat_sim  # futuro

with st.expander(f"🎲 {MESES_PT[mes_selecionado]} 2025 - Cenários por margem", expanded=not is_past):
    if is_past:
        html_real = (
            '<div class="metric-grid">'
            f'<div class="card"><h4>Faturamento (real)</h4><p class="value">{brl(fat_real_sel)}</p></div>'
            f'<div class="card"><h4>Compras (real)</h4><p class="value">{brl(compras_real_sel)}</p></div>'
            f'<div class="card"><h4>LAT (real)</h4><p class="value">{brl(lat_real_sel)}</p></div>'
            '</div>'
        )
        st.markdown(html_real, unsafe_allow_html=True)
    else:
        margem_ref = st.segmented_control(
            "Cenário de referência:",
            options=MARGENS,
            default=0.20,
            format_func=lambda x: f"{int(x*100)}%",
            key="margem_referencia",
        ) or 0.20

        # Totais e "a emitir" por margem r
        cenarios = {}
        for r in MARGENS:
            fat_total = (lat_total / r) if r > 0 else 0.0
            compras_total = fat_total - lat_total
            if is_vig:
                fat_emitir = max(0.0, fat_total - fat_real_sel)
                compras_emitir = max(0.0, compras_total - compras_real_sel)
            else:
                fat_emitir = max(0.0, fat_total)
                compras_emitir = max(0.0, compras_total)
            cenarios[int(r*100)] = {
                "FAT_TOTAL": fat_total,
                "COMPRA_TOTAL": compras_total,
                "FAT_EMITIR": fat_emitir,
                "COMPRA_EMITIR": compras_emitir,
            }

        ref = cenarios[int(margem_ref*100)]
        real_fat_html = (
            f'<div class="muted">Realizado: {brl(fat_real_sel)}</div>' if is_vig else ''
        )
        real_comp_html = (
            f'<div class="muted">Realizado: {brl(compras_real_sel)}</div>' if is_vig else ''
        )
        lat_info_html = (
            '<div class="muted">Inclui realizado + simulado</div>'
            if is_vig and sim_vigente
            else ''
        )
        html_ref = (
            '<div class="section"><h3>Cenário ' + str(int(margem_ref*100)) + '% (Referência)</h3></div>'
            '<div class="metric-grid">'
            f'<div class="card"><h4>Faturamento (total do mês)</h4><p class="value">{brl(ref["FAT_TOTAL"])}</p>'
            f'{real_fat_html}'
            f'<div class="muted">A emitir: {brl(ref["FAT_EMITIR"])}</div></div>'
            f'<div class="card"><h4>Compras (total do mês)</h4><p class="value">{brl(ref["COMPRA_TOTAL"])}</p>'
            f'{real_comp_html}'
            f'<div class="muted">A emitir: {brl(ref["COMPRA_EMITIR"])}</div></div>'
            f'<div class="card"><h4>LAT do mês</h4><p class="value">{brl(lat_total)}</p>'
            f'{lat_info_html}'
            '</div>'
        )
        st.markdown(html_ref, unsafe_allow_html=True)

        # PIS/COFINS (base LAT do mês)
        pis_mes, cofins_mes = pis_cofins(lat_total)
        html_trib = (
            '<div class="section"><h3>Tributos Mensais (Base LAT)</h3></div>'
            '<div class="metric-grid">'
            f'<div class="card"><h4>PIS (0,65%)</h4><p class="value">{brl(pis_mes)}</p></div>'
            f'<div class="card"><h4>COFINS (3%)</h4><p class="value">{brl(cofins_mes)}</p></div>'
            '</div>'
        )
        st.markdown(html_trib, unsafe_allow_html=True)

        # IRPJ/CSLL apenas em Mar/Jun/Set/Dez
        if mes_selecionado in [3, 6, 9, 12]:
            lat_anual = {}
            for m in range(1, 13):
                ymm = 2025*100 + m
                if m < mes_vig_num:
                    lat_anual[ymm] = val_real(m, "LAT")
                elif m == mes_vig_num:
                    lat_anual[ymm] = val_real(m, "LAT") + (st.session_state["lat_plan"][ymm] if sim_vigente else 0.0)
                else:
                    lat_anual[ymm] = st.session_state["lat_plan"][ymm]
            trib = irpj_csll_trimestre(lat_anual)
            irpj_mes, csll_mes = trib.get(2025*100 + mes_selecionado, (0.0, 0.0))
            html_ir = (
                '<div class="metric-grid">'
                f'<div class="card warn"><h4>IRPJ (Trimestre)</h4><p class="value">{brl(irpj_mes)}</p>'
                '<div class="muted">Lançado apenas em Mar/Jun/Set/Dez</div></div>'
                '</div>'
            )
            st.markdown(html_ir, unsafe_allow_html=True)

        # Todos os Cenários — montar cards sem indentação (evita <div> literal)
        st.markdown('<div class="section"><h3>Todos os Cenários</h3><div class="sub">Totais do mês e valores a emitir por margem</div></div>', unsafe_allow_html=True)
        cards = []
        for margem_pct in sorted(cenarios.keys()):
            c = cenarios[margem_pct]
            classe_css = "ok" if margem_pct >= 20 else "warn" if margem_pct >= 10 else "bad"
            cards.append(
                f'<div class="card {classe_css}"><h4>Margem {margem_pct}%</h4>'
                f'<p class="value">{brl(c["FAT_TOTAL"])}</p>'
                f'<div class="muted">Compras (total): {brl(c["COMPRA_TOTAL"])}</div>'
                f'<div class="muted">A emitir (Saída): {brl(c["FAT_EMITIR"])}</div>'
                f'<div class="muted">A emitir (Entrada): {brl(c["COMPRA_EMITIR"])}</div>'
                f'</div>'
            )
        st.markdown('<div class="kpi-grid">' + ''.join(cards) + '</div>', unsafe_allow_html=True)

# =========================
# Exportações (margem 20% como referência visual)
# =========================
st.markdown("---")

rows = []
lat_dict_anual = {}
for m in range(1, 13):
    ymm = 2025*100 + m
    lat_r = val_real(m, "LAT")
    if m < mes_vig_num:
        lat_tot = lat_r
    elif m == mes_vig_num:
        lat_tot = lat_r + (st.session_state["lat_plan"][ymm] if sim_vigente else 0.0)
    else:
        lat_tot = st.session_state["lat_plan"][ymm]
    lat_dict_anual[ymm] = lat_tot
    if lat_tot != 0:
        fat = lat_tot / 0.20
        compras = fat - lat_tot
        icms = 0.05 * fat
    else:
        fat = compras = icms = 0.0
    pis, cof = pis_cofins(lat_tot)
    rows.append({
        "Mês": MESES_PT[m],
        "LAT": lat_tot,
        "Faturamento (20%)": fat,
        "Compras (20%)": compras,
        "ICMS (5%)": icms,
        "PIS": pis,
        "COFINS": cof,
    })

df_consol = pd.DataFrame(rows)
tot = df_consol.sum(numeric_only=True)
tot["Mês"] = "TOTAL"
df_consol = pd.concat([df_consol, tot.to_frame().T], ignore_index=True)

c1, c2 = st.columns(2)
with c1:
    r = 0.20
    lat_t_mes = lat_dict_anual.get(2025*100 + st.session_state["mes_selecionado"], 0.0)
    fat_t_mes = lat_t_mes / r if r > 0 else 0.0
    comp_t_mes = fat_t_mes - lat_t_mes
    pis_m, cof_m = pis_cofins(lat_t_mes)
    df_mes = pd.DataFrame([{
        "Mês": MESES_PT[st.session_state["mes_selecionado"]],
        "LAT": lat_t_mes,
        "FAT (20%)": fat_t_mes,
        "Compras (20%)": comp_t_mes,
        "PIS": pis_m,
        "COFINS": cof_m,
    }])
    st.download_button(
        f"📄 Baixar {MESES_PT[st.session_state['mes_selecionado']]} CSV",
        df_mes.to_csv(index=False).encode("utf-8"),
        file_name=f"simulacao_{MESES_PT[st.session_state['mes_selecionado']].lower()}_2025.csv",
        mime="text/csv",
    )

with c2:
    st.download_button(
        "📊 Baixar Consolidado Anual XLSX",
        to_excel_bytes(df_consol),
        file_name="simulacao_anual_2025.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

with st.expander("👁️ Preview Consolidado Anual", expanded=False):
    prev = df_consol.copy()
    for col in ["LAT", "Faturamento (20%)", "Compras (20%)", "ICMS (5%)", "PIS", "COFINS"]:
        prev[col] = prev[col].apply(lambda x: brl(x))
    st.dataframe(prev, use_container_width=True, hide_index=True)
