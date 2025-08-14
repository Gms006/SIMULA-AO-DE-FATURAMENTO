import os
import sys
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from calc import parse_brl, cenarios_por_margem, irpj_csll_trimestre


def test_parse_brl():
    assert parse_brl("1.234.567,89") == pytest.approx(1234567.89)


def test_vigente_total_real_sim():
    real = 1000.0
    sim = 500.0
    total = real + sim
    cen = cenarios_por_margem(total)
    assert cen[20]["FAT"] == pytest.approx(total / 0.20)

class TestCalc(unittest.TestCase):
    def test_margem_20(self):
        res = calc_por_margem(100000.0, 0.20)
        self.assertAlmostEqual(res["FAT"], 500000.0, places=2)
        self.assertAlmostEqual(res["COMPRAS"], 400000.0, places=2)
        self.assertAlmostEqual(res["ICMS"], 25000.0, places=2)

def test_margem_20():
    res = cenarios_por_margem(100000.0)
    assert res[20]["FAT"] == pytest.approx(500000.0)
    assert res[20]["COMPRAS"] == pytest.approx(400000.0)
    assert res[20]["ICMS"] == pytest.approx(25000.0)


def test_irpj_csll_trimestre_adicional():
    lat_mes = {202501: 100000.0, 202502: 100000.0, 202503: 100000.0}
    trib = irpj_csll_trimestre(lat_mes)
    assert 202503 in trib
    irpj, csll = trib[202503]
    assert irpj == pytest.approx(18000.0)
    assert csll == pytest.approx(8640.0)
    assert 202502 not in trib