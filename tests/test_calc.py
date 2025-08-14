import sys
import os
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from calc import calc_por_margem, base_pis_cofins, irpj_csll_trimestrais


class TestCalc(unittest.TestCase):
    def test_margem_20(self):
        res = calc_por_margem(100000.0, 0.20)
        self.assertAlmostEqual(res["FAT"], 500000.0, places=2)
        self.assertAlmostEqual(res["COMPRAS"], 400000.0, places=2)
        self.assertAlmostEqual(res["ICMS"], 25000.0, places=2)

    def test_pis_cofins_bases(self):
        lat = 100000.0
        fat_ref = calc_por_margem(lat, 0.20)["FAT"]
        pis, cof = base_pis_cofins("Lucro do mês (LAT)", lat, fat_ref)
        self.assertAlmostEqual(pis, 650.0, places=2)
        self.assertAlmostEqual(cof, 3000.0, places=2)

        pis_fat, cof_fat = base_pis_cofins("Receita (FAT)", lat, fat_ref)
        self.assertAlmostEqual(pis_fat, 0.0065 * fat_ref, places=2)
        self.assertAlmostEqual(cof_fat, 0.03 * fat_ref, places=2)

        pis_marg, cof_marg = base_pis_cofins("Margem (FAT*m)", lat, fat_ref, m_ref=0.20)
        self.assertAlmostEqual(pis_marg, 0.0065 * fat_ref * 0.20, places=2)
        self.assertAlmostEqual(cof_marg, 0.03 * fat_ref * 0.20, places=2)

    def test_irpj_csll_trimestre(self):
        lat_mes = {202501: 100000.0, 202502: 100000.0, 202503: 100000.0}
        trib = irpj_csll_trimestrais(lat_mes)
        irpj, csll = trib.get(202503, (0.0, 0.0))
        self.assertAlmostEqual(irpj, 18000.0, places=2)
        self.assertAlmostEqual(csll, 8640.0, places=2)
        self.assertNotIn(202501, trib)
        self.assertNotIn(202502, trib)


if __name__ == "__main__":
    unittest.main()
