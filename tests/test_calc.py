import os
import sys
import pandas as pd
import streamlit as st
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ui_helpers import cenarios_fat_compra, pis_cofins
from calc import irpj_csll_trimestre


def test_number_column_format_and_dtype():
    df = pd.DataFrame({"LAT (R$)": pd.Series([None]*12, dtype="float")})
    st.column_config.NumberColumn("LAT (R$)", format="R$ %.2f", step=100.0, min_value=0.0)
    assert str(df["LAT (R$)"].dtype) == "float64"


def test_cenarios_fat_compra_margem_20():
    res = cenarios_fat_compra(389_800)
    assert res[20]["FAT"] == pytest.approx(1_949_000)
    assert res[20]["COMPRA"] == pytest.approx(1_559_200)
    assert res[20]["ICMS"] == pytest.approx(97_450)


def test_vigente_soma_real_simulado():
    lat_real = 10_000.0
    lat_sim = 5_000.0
    lat_total = lat_real + lat_sim
    pis, cofins = pis_cofins(lat_total)
    assert pis == pytest.approx(0.0065 * lat_total)
    assert cofins == pytest.approx(0.03 * lat_total)

    lat_dict = {202501: lat_real, 202502: lat_total, 202503: 0.0}
    trib = irpj_csll_trimestre(lat_dict)
    base = 0.32 * (lat_real + lat_total + 0.0)
    assert trib[202503][0] == pytest.approx(0.15 * base)
    assert trib[202503][1] == pytest.approx(0.09 * base)


def test_irpj_csll_trimestre_adicional():
    lat_mes = {202501: 100_000.0, 202502: 100_000.0, 202503: 100_000.0}
    trib = irpj_csll_trimestre(lat_mes)
    assert 202503 in trib and 202502 not in trib
    irpj, csll = trib[202503]
    base_total = 0.32 * (300_000.0)
    expected_irpj = 0.15 * base_total + 0.10 * (base_total - 60_000)
    expected_csll = 0.09 * base_total
    assert irpj == pytest.approx(expected_irpj)
    assert csll == pytest.approx(expected_csll)
