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

# =========================
# Configuração da página
# =========================
st.set_page_config(page_title="Simulação de Faturamento 2025", layout="wide")

# =========================
# Estilos
# =========================
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

# =========================
# Sidebar: parâmetros GitHub
# =========================
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
            st.warning("Falha ao carregar do GitHub. Tentando arquivo local...")

    # Fallback para arquivo local
    try:
        return pd.read_excel(path, engine="openpyxl")
    except Exception:
        return None

# =========================
# Utilidades
# =========================
def fmt_brl(v: float) -> str:
    """Formata valor em Real brasileiro."""
    try:
        return f"R$ {float(v):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except Exception:
        return "R$ 0,00"

MESES_PT = {
    1: "Jan", 2: "Fev", 3: "Mar", 4: "Abr", 5: "Mai", 6: "Jun",
    7: "Jul", 8: "Ago", 9: "Set", 10: "Out", 11: "Nov", 12: "Dez",
}

def yyyymm_to_parts(yyyymm: int) -> tuple[int, int]:
    return yyyymm // 100, yyyymm % 100

def montar_df_export(realizado: pd.DataFrame, lat_sim: dict[int, float]) -> pd.DataFrame:
    """
    Gera um DataFrame com LAT real/simulado por yyyymm para exportação.
    Espera realizado com index 1..12 (meses) e colunas ['LAT','FAT'].
    """
    linhas = []
    # Reais (travados)
    for m in range(1, 13):
        if m in realizado.index:
            yyyymm = 202500 + m
            linhas.append({"yyyymm": yyyymm, "tipo": "Real", "mes": m,
                           "LAT": float(realizado.loc[m, "LAT"]), "FAT": float(realizado.loc[m, "FAT"])})
    # Simulados (sobrepõe)
    for k, v in lat_sim.items():
        ano, mes = yyyymm_to_parts(k)
        if ano == 2025:
            fat_calc = None  # se desejar, pode inferir via calc_mes(v)
            linhas.append({"yyyymm": k, "tipo": "Simulado", "mes": mes,
                           "LAT": float(v), "FAT": fat_calc if fat_calc is not None else 0.0})
    df_out = pd.DataFrame(linhas).sort_values("yyyymm").reset_index(drop=True)
    df_out["mes_nome"] = df_out["mes"].map(MESES_PT)
    return df_out

def download_excel_button(df: pd.DataFrame, filename: str, label: str = "Baixar Excel"):
    with BytesIO() as buffer:
        with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name="Simulacao")
        st.download_button(label, data=buffer.getvalue(), file_name=filename, mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

# =========================
# Carregamento de dados
# =========================
df = load_data(owner, repo, branch, path)
if df is None:
    uploaded = st.file_uploader("Envie a planilha resultado_eduardo_veiculos.xlsx", type="xlsx")
    if uploaded:
        df = pd.read_excel(uploaded, engine="openpyxl")

if df is None:
    st.error("Não foi possível carregar os dados. Verifique o arquivo ou parâmetros GitHub.")
    st.stop()

# =========================
# Processamento base
# =========================
df = prepare_dataframe(df)
realizado = compute_realizado(df)  # esperado index 1..12 com colunas ['FAT','LAT']
ultimo = ultimo_yyyymm(df)         # ex: 202503
last_month = (ultimo % 100) if ultimo else 0

# =========================
# Página
# =========================
pagina = st.sidebar.selectbox("Página", ["Simulação", "Dashboard", "Notas/Detalhes"])

# =========================
# Página: Simulação
# =========================
if pagina == "Simulação":
    st.title("Simulação de Faturamento 2025")

    # Estado para LATs simulados
    if "lat_sim" not in st.session_state:
        st.session_state["lat_sim"] = {}
    lat_sim: dict[int, float] = st.session_state["lat_sim"]

    # Resumo YTD (dados reais até o último mês disponível)
    st.subheader("Resumo 2025")
    if last_month > 0:
        fat_ytd = float(realizado.loc[1:last_month, "FAT"].sum())
        lat_ytd = float(realizado.loc[1:last_month, "LAT"].sum())
    else:
        fat_ytd = lat_ytd = 0.0
    c1, c2 = st.columns(2)
    c1.metric("Faturado YTD", fmt_brl(fat_ytd))
    c2.metric("LAT YTD", fmt_brl(lat_ytd))

    st.markdown("---")
    col_mes, col_toggle = st.columns([4, 1])
    with col_toggle:
        sim_vigente = st.checkbox("Simular mês vigente", False)

    # Meses simuláveis
    meses_disp = meses_simulaveis(ultimo)  # lista de yyyymm
    if sim_vigente and ultimo and ultimo not in meses_disp:
        meses_disp.insert(0, ultimo)
    if not meses_disp:
        st.info("Todos os meses de 2025 já estão realizados ou não há dados disponíveis.")
        st.stop()

    with col_mes:
        # CORREÇÃO: usar default= (e não selection=)
        mes_atual = st.segmented_control(
            "Meses simuláveis",
            meses_disp,
            default=st.session_state.get("mes_atual", meses_disp[0]),
            format_func=lambda m: MESES_PT[m % 100],
        )
    st.session_state["mes_atual"] = mes_atual

    # Editor do mês selecionado
    st.markdown("---")
    ano_sel, mes_sel = yyyymm_to_parts(mes_atual)
    st.subheader(f"Editor: {MESES_PT[mes_sel].upper()} {ano_sel}")

    lat_val_default = float(lat_sim.get(mes_atual, 0.0))
    col_lat, col_prop = st.columns([3, 1])
    with col_lat:
        lat_input = st.number_input(
            "LAT do mês (R$)",
            min_value=0.0,
            step=1000.0,
            value=lat_val_default,
            key=f"lat_{mes_atual}",
        )
    with col_prop:
        propagar = st.checkbox("Aplicar este LAT aos próximos meses")

    # Atualiza e propaga
    lat_sim[mes_atual] = float(lat_input)
    if propagar:
        for m in meses_disp:
            if m >= mes_atual:
                lat_sim[m] = float(lat_input)

    # Cenários por margem
    st.markdown("#### Cenários por Margem")
    res_mes = calc_mes(float(lat_input))
    cenarios = res_mes["cenarios"]  # dict {margem: {"FAT":..., "COMPRAS":..., "ICMS":...}}
    margens = [0.05, 0.10, 0.15, 0.20, 0.25, 0.30]

    for i in range(0, 6, 2):
        c1, c2 = st.columns(2)
        with c1:
            m = margens[i]
            st.markdown(f'<div class="card-margem"><div class="card-titulo">Margem {int(m*100)}%</div></div>', unsafe_allow_html=True)
            st.metric("Faturamento", fmt_brl(cenarios[m]["FAT"]))
            st.metric("Compras", fmt_brl(cenarios[m]["COMPRAS"]))
        if i + 1 < len(margens):
            with c2:
                m = margens[i + 1]
                st.markdown(f'<div class="card-margem"><div class="card-titulo">Margem {int(m*100)}%</div></div>', unsafe_allow_html=True)
                st.metric("Faturamento", fmt_brl(cenarios[m]["FAT"]))
                st.metric("Compras", fmt_brl(cenarios[m]["COMPRAS"]))

    # Tributos do mês (PIS/COFINS fixos para o LAT; ICMS depende da margem -> usar 20% como referência)
    st.markdown("#### Tributos do Mês")
    pis = float(res_mes["PIS"])
    cofins = float(res_mes["COFINS"])
    icms_ref = float(cenarios[0.20]["ICMS"])

    c1, c2, c3 = st.columns(3)
    c1.metric("PIS (mês)", fmt_brl(pis))
    c2.metric("COFINS (mês)", fmt_brl(cofins))
    c3.metric("ICMS (mês)*", fmt_brl(icms_ref))
    st.caption("*ICMS depende do faturamento (varia por margem).")

    # Obrigações do Trimestre
    st.markdown("---")
    st.subheader("Obrigações do Trimestre")

    # LAT total: reais + simulados
    lat_total: dict[int, float] = {}
    # reais (travados até 'ultimo')
    for m in range(1, 13):
        if ultimo and (202500 + m) <= ultimo and m in realizado.index:
            lat_total[202500 + m] = float(realizado.loc[m, "LAT"])
    # simulados
    lat_total.update({int(k): float(v) for k, v in lat_sim.items()})

    tri_key = trimestre_de(mes_atual)  # ex: (2025, 1) para tri 1/2025
    prog, total, faltantes = progresso_trimestre(lat_total, tri_key)

    badge_class = "badge-completo" if prog == total else "badge-incompleto"
    st.markdown(
        f'<span class="badge-trimestre {badge_class}">Completo {prog}/{total}</span>',
        unsafe_allow_html=True,
    )

    if prog < total:
        st.warning("Complete os 3 meses para apurar o trimestre.")
        if faltantes:
            cols = st.columns(len(faltantes))
            for idx, m in enumerate(faltantes):
                if m in meses_disp:
                    if cols[idx].button(MESES_PT[m % 100], key=f"goto_{m}"):
                        st.session_state["mes_atual"] = m
                        st.rerun()

    irpj, csll, fechamento = irpj_csll_trimestre(lat_total, tri_key)  # fechamento: yyyymm do mês de apuração
    cc1, cc2 = st.columns(2)
    if mes_atual == fechamento and prog == total:
        cc1.metric(f"IRPJ – {MESES_PT[fechamento % 100]} (trimestre)", fmt_brl(float(irpj)))
        cc2.metric(f"CSLL – {MESES_PT[fechamento % 100]} (trimestre)", fmt_brl(float(csll)))
    else:
        cc1.metric("IRPJ – trimestre", fmt_brl(0.0))
        cc2.metric("CSLL – trimestre", fmt_brl(0.0))

    # Exportação
    st.markdown("---")
    st.subheader("Exportar Simulação")
    df_export = montar_df_export(realizado, lat_sim)
    st.dataframe(df_export, use_container_width=True)
    download_excel_button(df_export, "simulacao_2025.xlsx", "Baixar Excel da Simulação")

# =========================
# Página: Dashboard
# =========================
elif pagina == "Dashboard":
    st.title("Dashboard")

    # Base para gráfico FAT vs LAT (reais apenas)
    df_plot = (
        realizado.reset_index()
        .rename(columns={"index": "mes"})
        .assign(mes_nome=lambda d: d["mes"].map(MESES_PT))
    )

    c1, c2 = st.columns(2)
    c1.metric("Faturado Ano", fmt_brl(float(df_plot["FAT"].sum())))
    c2.metric("LAT Ano", fmt_brl(float(df_plot["LAT"].sum())))

    st.markdown("#### Faturamento (FAT) x LAT por mês (real)")
    fig = px.bar(
        df_plot,
        x="mes_nome",
        y=["FAT", "LAT"],
        barmode="group",
        labels={"value": "Valor", "mes_nome": "Mês", "variable": "Tipo"},
    )
    st.plotly_chart(fig, use_container_width=True)

    st.markdown("#### Tabela (real)")
    st.dataframe(
        df_plot[["mes", "mes_nome", "FAT", "LAT"]].rename(
            columns={"mes": "Mês", "mes_nome": "Nome do Mês", "FAT": "Faturamento", "LAT": "LAT"}
        ),
        use_container_width=True,
    )

# =========================
# Página: Notas/Detalhes
# =========================
else:
    st.title("Notas e Detalhes")
    st.markdown(
        """
- **Dados 'realizado'**: consolidados a partir da planilha base.
- **LAT simulado**: armazenado em `st.session_state["lat_sim"]` por `yyyymm`.
- **Cenários por margem**: usam `calc_mes(LAT)` para estimar FAT, COMPRAS e ICMS.
- **Trimestre**: `progresso_trimestre` verifica 3 meses completos; `irpj_csll_trimestre` só exibe valores no mês de fechamento e se o trio estiver completo.
- **Exportação**: inclui linhas “Real” e “Simulado”; o FAT simulado pode ser preenchido via cenários caso você deseje (aqui deixei 0 para FAT simulado por simplicidade).
- **Segmented Control**: use `default=` (não `selection=`). Se sua versão do Streamlit não tiver `st.segmented_control`, substitua por `st.selectbox`.
        """
    )
    st.code(
        "mes_atual = st.segmented_control('Meses simuláveis', meses_disp, default=meses_disp[0], format_func=lambda m: MESES_PT[m % 100])",
        language="python",
    )
