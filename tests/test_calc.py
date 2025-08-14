import os
import sys
import pytest

sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from calc import calc_mes, irpj_csll_trimestre, progresso_trimestre


def test_calc_mes_basico():
    res = calc_mes(100000.0)
    assert res["PIS"] == pytest.approx(650.0)
    assert res["COFINS"] == pytest.approx(3000.0)
    cen = res["cenarios"][0.20]
    assert cen["FAT"] == pytest.approx(500000.0)
    assert cen["COMPRAS"] == pytest.approx(400000.0)
    assert cen["ICMS"] == pytest.approx(25000.0)


def test_irpj_csll_trimestre():
    lat = {202501: 83333.33, 202502: 83333.33, 202503: 83333.34}
    irpj, csll, fechamento = irpj_csll_trimestre(lat, "2025Q1")
    assert irpj == pytest.approx(14000.0)
    assert csll == pytest.approx(7200.0)
    assert fechamento == 202503


def test_progresso_trimestre():
    lat = {202501: 1000.0, 202502: 0.0, 202503: 1000.0}
    prog, total, falt = progresso_trimestre(lat, "2025Q1")
    assert total == 3
    assert prog == 2
    assert falt == [202502]
