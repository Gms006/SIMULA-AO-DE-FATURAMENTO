import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
from io import BytesIO
from calc import prepare_dataframe, compute_realizado, simulate

st.set_page_config(page_title="Simulação de Faturamento 2025", layout="wide")

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
last_month = int(realizado[realizado["FAT"] > 0].index.max() or 0)

def fmt_brl(v: float) -> str:
    return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

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
    st.header("Simulação 2025")
    lat_meta = st.number_input("Meta LAT Anual (R$)", min_value=0.0, step=1000.0)
    margens_opts = [0.05, 0.10, 0.15, 0.20, 0.25, 0.30]
    margens = [m for m in margens_opts if st.checkbox(f"Margem {int(m*100)}%", True, key=f"m_{m}")]
    sim_mes_atual = st.checkbox("Simular mês vigente", False)
    meses_sim = list(range(last_month + 1, 13))
    locked = list(range(1, last_month + 1))
    if sim_mes_atual:
        meses_sim = list(range(last_month, 13))
        locked = list(range(1, last_month))
    manual = st.checkbox("Distribuição manual por mês", False)
    distrib = {}
    if manual:
        st.write("Distribuição (% do LAT restante)")
        total = 0
        for mes in meses_sim:
            val = st.slider(f"Mês {mes:02d}", 0, 100, value=int(100 / len(meses_sim)), key=f"d_{mes}")
            distrib[mes] = val
            total += val
        if total > 0:
            distrib = {k: v / total for k, v in distrib.items()}
        else:
            distrib = None
    else:
        distrib = None
    resultados = simulate(realizado, lat_meta, margens, meses_sim, distrib)
    for margem, dfm in resultados.items():
        st.subheader(f"Margem {int(margem*100)}%")
        df_show = dfm.copy()
        df_show["Tributos"] = df_show[["PIS", "COFINS", "ICMS", "IRPJ", "CSLL"]].sum(axis=1)
        total = df_show.sum()
        df_show = pd.concat([df_show, total.to_frame().T], ignore_index=False)
        df_show.index = list(range(1, 13)) + ["Total"]
        st.dataframe(df_show)
        if (df_show.loc[1:12, "LL"] < 0).any():
            st.warning("Lucro Líquido negativo em algum mês.")
        csv = df_show.to_csv().encode("utf-8")
        st.download_button("Exportar CSV", csv, f"simulacao_{int(margem*100)}.csv", "text/csv")
        towrite = BytesIO()
        with pd.ExcelWriter(towrite, engine="openpyxl") as writer:
            df_show.to_excel(writer, index=True)
        st.download_button(
            "Exportar XLSX",
            towrite.getvalue(),
            f"simulacao_{int(margem*100)}.xlsx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        try:
            from reportlab.lib.pagesizes import A4
            from reportlab.pdfgen import canvas
            pdf_buffer = BytesIO()
            c = canvas.Canvas(pdf_buffer, pagesize=A4)
            c.drawString(30, 800, f"Simulação margem {int(margem*100)}%")
            text = c.beginText(30, 780)
            for line in df_show.to_string().split("\n"):
                text.textLine(line)
            c.drawText(text)
            c.showPage()
            c.save()
            pdf_buffer.seek(0)
            st.download_button(
                "Exportar PDF",
                pdf_buffer,
                f"simulacao_{int(margem*100)}.pdf",
                "application/pdf",
            )
        except Exception:
            st.info("reportlab não disponível para PDF.")
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
