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

st.set_page_config(page_title="Simulação de Faturamento 2025", layout="wide")
st.markdown(
    """
<style>
div.stMetric{border:1px solid #E0E0E0;padding:10px;border-radius:4px;background-color:#F6F8FC}
</style>
""",
    unsafe_allow_html=True,
)

st.sidebar.header("Parâmetros GitHub")
owner = st.sidebar.text_input("Owner", value="")
repo = st.sidebar.text_input("Repo", value="SIMULACAO-DE-FATURAMENTO")
branch = st.sidebar.text_input("Branch", value="main")
path = st.sidebar.text_input("Path", value="resultado_eduardo_veiculos.xlsx")

@st.cache_data(ttl=300)
def load_data(owner: str, repo: str, branch: str, path: str):
    if owner:
        url = f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{path}"
        try:
            return pd.read_excel(url, engine="openpyxl")
        except Exception:
            st.warning("Falha ao carregar do GitHub.")
    try:
        return pd.read_excel(path, engine="openpyxl")
    except Exception:
        return None

df = load_data(owner, repo, branch, path)
if df is None:
    uploaded = st.file_uploader("Envie a planilha resultado_eduardo_veiculos.xlsx", type="xlsx")
    if uploaded:
        df = pd.read_excel(uploaded, engine="openpyxl")

if df is None:
    st.stop()

df = prepare_dataframe(df)
realizado = compute_realizado(df)
ultimo = ultimo_yyyymm(df)
last_month = ultimo % 100

def fmt_brl(v: float) -> str:
    return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

MESES_PT = {
    1: "Jan",
    2: "Fev",
    3: "Mar",
    4: "Abr",
    5: "Mai",
    6: "Jun",
    7: "Jul",
    8: "Ago",
    9: "Set",
    10: "Out",
    11: "Nov",
    12: "Dez",
}

pagina = st.sidebar.selectbox("Página", ["Dashboard", "Simulação", "Notas/Detalhes"])

if pagina == "Dashboard":
    ano = st.sidebar.selectbox("Ano", [2025], index=0)
    mes = st.sidebar.selectbox("Mês", list(range(1, 13)), index=max(last_month - 1, 0))
    linha = realizado.loc[mes]
    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("Entradas", fmt_brl(linha["CMV"]))
    col2.metric("Saídas", fmt_brl(linha["FAT"]))
    col3.metric("LAT", fmt_brl(linha["LAT"]))
    col4.metric("Lucro Líquido", fmt_brl(linha["LL"]))
    col5.metric("Consumo", fmt_brl(linha["CONSUMO"]))
    mensal = realizado.copy()
    mensal["Tributos"] = mensal[["PIS", "COFINS", "ICMS", "IRPJ", "CSLL"]].sum(axis=1)
    fig = px.bar(mensal, x=mensal.index, y=["FAT", "CMV", "CONSUMO", "LAT", "Tributos", "LL"], barmode="stack")
    fig.update_layout(xaxis_title="Mês", yaxis_title="R$")
    st.plotly_chart(fig, use_container_width=True)

elif pagina == "Simulação":
    st.header("Cenários por Margem – mensal e trimestral")
    lat_sim = st.session_state.setdefault("lat_sim", {})

    fat_ytd = realizado.loc[1:last_month, "FAT"].sum()
    lat_ytd = realizado.loc[1:last_month, "LAT"].sum()
    col1, col2 = st.columns(2)
    col1.metric("Faturado YTD", fmt_brl(fat_ytd))
    col2.metric("LAT YTD", fmt_brl(lat_ytd))

    col_mes, col_toggle = st.columns([4, 1])
    with col_toggle:
        sim_vigente = st.checkbox("Simular mês vigente", False)
    meses_disp = meses_simulaveis(ultimo)
    if sim_vigente and ultimo not in meses_disp:
        meses_disp.insert(0, ultimo)
    if not meses_disp:
        st.info("Todos os meses de 2025 já estão realizados.")
        st.stop()
    with col_mes:
        mes_atual = st.segmented_control(
            "Meses simuláveis",
            meses_disp,
            key="mes_atual",
            selection=st.session_state.get("mes_atual", meses_disp[0]),
            format_func=lambda m: MESES_PT[m % 100],
        )

    lat_val = lat_sim.get(mes_atual, 0.0)
    lat_input = st.number_input(
        "LAT do mês (R$)",
        min_value=0.0,
        step=1000.0,
        value=lat_val,
        key=f"lat_{mes_atual}",
    )
    lat_sim[mes_atual] = lat_input
    propagar = st.checkbox("Aplicar este LAT aos próximos meses")
    if propagar:
        for m in meses_disp:
            if m >= mes_atual:
                lat_sim[m] = lat_input

    res_mes = calc_mes(lat_input)
    cenarios = res_mes["cenarios"]
    margens = [0.05, 0.10, 0.15, 0.20, 0.25, 0.30]
    for i in range(0, 6, 2):
        c1, c2 = st.columns(2)
        for j, m in enumerate(margens[i:i+2]):
            col = c1 if j == 0 else c2
            with col:
                st.markdown(f"**Margem {int(m*100)}%**")
                st.metric("Faturamento", fmt_brl(cenarios[m]["FAT"]))
                st.metric("Compras", fmt_brl(cenarios[m]["COMPRAS"]))

    pis = res_mes["PIS"]
    cofins = res_mes["COFINS"]
    icms_ref = cenarios[0.20]["ICMS"]
    c1, c2, c3 = st.columns(3)
    c1.metric("PIS (mês)", fmt_brl(pis))
    c2.metric("COFINS (mês)", fmt_brl(cofins))
    c3.metric("ICMS (mês)", fmt_brl(icms_ref))
    st.caption("*ICMS depende do faturamento (varia por margem)")

    lat_total = {202500 + m: realizado.loc[m, "LAT"] for m in range(1, 13)}
    lat_total.update(lat_sim)
    tri_key = trimestre_de(mes_atual)
    prog, total, faltantes = progresso_trimestre(lat_total, tri_key)
    st.subheader("Obrigações do Trimestre")
    st.markdown(f"**Completo {prog}/{total}**")
    if prog < total:
        st.warning("Complete os 3 meses para apurar o trimestre")
        cols = st.columns(len(faltantes))
        for idx, m in enumerate(faltantes):
            if cols[idx].button(MESES_PT[m % 100], key=f"goto_{m}"):
                st.session_state["mes_atual"] = m
                st.experimental_rerun()
    irpj, csll, fechamento = irpj_csll_trimestre(lat_total, tri_key)
    c1, c2 = st.columns(2)
    if mes_atual == fechamento and prog == total:
        c1.metric(f"IRPJ – {MESES_PT[fechamento % 100]}", fmt_brl(irpj))
        c2.metric(f"CSLL – {MESES_PT[fechamento % 100]}", fmt_brl(csll))
    else:
        c1.metric("IRPJ – trimestre", fmt_brl(0.0))
        c2.metric("CSLL – trimestre", fmt_brl(0.0))

    rows = []
    for m in margens:
        rows.append({"Item": f"Margem {int(m*100)}% FAT", "Valor": cenarios[m]["FAT"]})
        rows.append({"Item": f"Margem {int(m*100)}% Compras", "Valor": cenarios[m]["COMPRAS"]})
    rows.append({"Item": "PIS", "Valor": pis})
    rows.append({"Item": "COFINS", "Valor": cofins})
    rows.append({"Item": "ICMS (20%)", "Valor": icms_ref})
    df_export = pd.DataFrame(rows)
    csv = df_export.to_csv(index=False).encode("utf-8")
    st.download_button("Exportar Resumo CSV", csv, f"resumo_{mes_atual}.csv", "text/csv")
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas
        pdf_buffer = BytesIO()
        c = canvas.Canvas(pdf_buffer, pagesize=A4)
        c.drawString(30, 800, f"Resumo {MESES_PT[mes_atual % 100]} 2025")
        text = c.beginText(30, 780)
        for _, row in df_export.iterrows():
            text.textLine(f"{row['Item']}: {fmt_brl(row['Valor'])}")
        c.drawText(text)
        c.showPage()
        c.save()
        pdf_buffer.seek(0)
        st.download_button(
            "Exportar Resumo PDF",
            pdf_buffer,
            f"resumo_{mes_atual}.pdf",
            "application/pdf",
        )
    except Exception:
        st.info("reportlab não disponível para PDF.")

    if st.checkbox("Mostrar detalhes (opcional)"):
        detalhes = []
        for m in meses_disp:
            latm = lat_sim.get(m, 0.0)
            resm = calc_mes(latm)
            cen20 = resm["cenarios"][0.20]
            detalhes.append(
                {
                    "Mês": MESES_PT[m % 100],
                    "LAT": latm,
                    "FAT_20%": cen20["FAT"],
                    "Compras_20%": cen20["COMPRAS"],
                    "PIS": resm["PIS"],
                    "COFINS": resm["COFINS"],
                    "ICMS_20%": cen20["ICMS"],
                }
            )
        st.dataframe(pd.DataFrame(detalhes))
elif pagina == "Notas/Detalhes":
    st.header("Notas/Detalhes")
    meses = st.multiselect("Mês", sorted(df["mes"].unique()), default=sorted(df["mes"].unique()))
    tipos = st.multiselect("Tipo Nota", sorted(df["tipo_nota"].unique()), default=sorted(df["tipo_nota"].unique()))
    classifs = st.multiselect("Classificação", sorted(df["classificacao"].unique()), default=sorted(df["classificacao"].unique()))
    filtrado = df[df["mes"].isin(meses) & df["tipo_nota"].isin(tipos) & df["classificacao"].isin(classifs)]
    st.dataframe(filtrado)
    csv = filtrado.to_csv(index=False).encode("utf-8")
    st.download_button("Download CSV", csv, "notas_filtradas.csv", "text/csv")
    towrite = BytesIO()
    with pd.ExcelWriter(towrite, engine="openpyxl") as writer:
        filtrado.to_excel(writer, index=False)
    st.download_button(
        "Download XLSX",
        towrite.getvalue(),
        "notas_filtradas.xlsx",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
