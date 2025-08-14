"""
Testes unitários para as funções de cálculo fiscal.
Valida os cenários de simulação de LAT, cálculos de tributos e progressos trimestrais.
"""

import unittest
import sys
import os

# Adicionar o diretório pai ao path para importar calc
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from calc import (
    calc_mes,
    irpj_csll_trimestre,
    progresso_trimestre,
    trimestre_de,
    ultimo_yyyymm,
    meses_simulaveis
)
import pandas as pd


class TestCalcFunctions(unittest.TestCase):
    """Testes para funções de cálculo fiscal."""
    
    def test_calc_mes_cenario_basico(self):
        """Caso 1: LAT de R$ 100.000 - validar PIS, COFINS e cenários por margem."""
        lat = 100000.0
        resultado = calc_mes(lat)
        
        # Validar tributos mensais
        self.assertAlmostEqual(resultado["PIS"], 650.0, places=2)
        self.assertAlmostEqual(resultado["COFINS"], 3000.0, places=2)
        
        # Validar cenário margem 20%
        cenario_20 = resultado["cenarios"][0.20]
        self.assertAlmostEqual(cenario_20["FAT"], 500000.0, places=2)
        self.assertAlmostEqual(cenario_20["COMPRAS"], 400000.0, places=2)
        self.assertAlmostEqual(cenario_20["ICMS"], 25000.0, places=2)
        
        # Validar cenário margem 5%
        cenario_5 = resultado["cenarios"][0.05]
        self.assertAlmostEqual(cenario_5["FAT"], 2000000.0, places=2)
        self.assertAlmostEqual(cenario_5["COMPRAS"], 1900000.0, places=2)
        self.assertAlmostEqual(cenario_5["ICMS"], 100000.0, places=2)
        
        # Validar cenário margem 30%
        cenario_30 = resultado["cenarios"][0.30]
        self.assertAlmostEqual(cenario_30["FAT"], 333333.33, places=2)
        self.assertAlmostEqual(cenario_30["COMPRAS"], 233333.33, places=2)
        self.assertAlmostEqual(cenario_30["ICMS"], 16666.67, places=2)
    
    def test_calc_mes_lat_zero(self):
        """Teste com LAT zero - todos os valores devem ser zero."""
        resultado = calc_mes(0.0)
        
        self.assertEqual(resultado["PIS"], 0.0)
        self.assertEqual(resultado["COFINS"], 0.0)
        
        for margem in [0.05, 0.10, 0.15, 0.20, 0.25, 0.30]:
            cenario = resultado["cenarios"][margem]
            self.assertEqual(cenario["FAT"], 0.0)
            self.assertEqual(cenario["COMPRAS"], 0.0)
            self.assertEqual(cenario["ICMS"], 0.0)
    
    def test_irpj_csll_trimestre_base_normal(self):
        """Caso 2: Trimestre com base que não excede 60k - apenas alíquotas básicas."""
        lat_mes = {202501: 50000.0, 202502: 50000.0, 202503: 50000.0}
        irpj, csll, fechamento = irpj_csll_trimestre(lat_mes, "2025Q1")
        
        # Base total: 150k * 0.32 = 48k (não excede 60k)
        # IRPJ: 15% * 48k = 7.200
        # CSLL: 9% * 48k = 4.320
        self.assertAlmostEqual(irpj, 7200.0, places=2)
        self.assertAlmostEqual(csll, 4320.0, places=2)
        self.assertEqual(fechamento, 202503)
    
    def test_irpj_csll_trimestre_adicional_aplicado(self):
        """Caso 2b: Trimestre com base que excede 60k - aplicar adicional de IRPJ."""
        lat_mes = {202501: 83333.33, 202502: 83333.33, 202503: 83333.34}
        irpj, csll, fechamento = irpj_csll_trimestre(lat_mes, "2025Q1")
        
        # Base total: 250k * 0.32 = 80k
        # IRPJ: 15% * 80k + 10% * (80k - 60k) = 12k + 2k = 14k
        # CSLL: 9% * 80k = 7.2k
        self.assertAlmostEqual(irpj, 14000.0, places=2)
        self.assertAlmostEqual(csll, 7200.0, places=2)
        self.assertEqual(fechamento, 202503)
    
    def test_irpj_csll_trimestre_diferentes_q(self):
        """Validar cálculos para diferentes trimestres."""
        # Q2 (abr-jun)
        lat_q2 = {202504: 70000.0, 202505: 70000.0, 202506: 70000.0}
        irpj_q2, csll_q2, fechamento_q2 = irpj_csll_trimestre(lat_q2, "2025Q2")
        
        self.assertEqual(fechamento_q2, 202506)
        # Base: 210k * 0.32 = 67.2k
        # IRPJ: 15% * 67.2k + 10% * 7.2k = 10.08k + 0.72k = 10.8k
        self.assertAlmostEqual(irpj_q2, 10800.0, places=2)
        
        # Q4 (out-dez)
        lat_q4 = {202510: 30000.0, 202511: 30000.0, 202512: 30000.0}
        irpj_q4, csll_q4, fechamento_q4 = irpj_csll_trimestre(lat_q4, "2025Q4")
        
        self.assertEqual(fechamento_q4, 202512)
        # Base: 90k * 0.32 = 28.8k (não excede 60k)
        self.assertAlmostEqual(irpj_q4, 4320.0, places=2)
        self.assertAlmostEqual(csll_q4, 2592.0, places=2)
    
    def test_progresso_trimestre_casos(self):
        """Caso 3: Progresso do trimestre - 0/3, 1/3, 2/3, 3/3."""
        
        # Cenário 0/3: trimestre vazio
        prog0, total0, faltantes0 = progresso_trimestre({}, "2025Q1")
        self.assertEqual(prog0, 0)
        self.assertEqual(total0, 3)
        self.assertEqual(len(faltantes0), 3)
        self.assertIn(202501, faltantes0)
        self.assertIn(202502, faltantes0)
        self.assertIn(202503, faltantes0)
        
        # Cenário 1/3: apenas janeiro preenchido
        prog1, total1, faltantes1 = progresso_trimestre({202501: 1000.0}, "2025Q1")
        self.assertEqual(prog1, 1)
        self.assertEqual(total1, 3)
        self.assertEqual(len(faltantes1), 2)
        self.assertIn(202502, faltantes1)
        self.assertIn(202503, faltantes1)
        
        # Cenário 2/3: janeiro e fevereiro preenchidos
        prog2, total2, faltantes2 = progresso_trimestre({202501: 1000.0, 202502: 1000.0}, "2025Q1")
        self.assertEqual(prog2, 2)
        self.assertEqual(total2, 3)
        self.assertEqual(len(faltantes2), 1)
        self.assertIn(202503, faltantes2)
        
        # Cenário 3/3: trimestre completo
        lat_completo = {202501: 1000.0, 202502: 2000.0, 202503: 1500.0}
        prog3, total3, faltantes3 = progresso_trimestre(lat_completo, "2025Q1")
        self.assertEqual(prog3, 3)
        self.assertEqual(total3, 3)
        self.assertEqual(len(faltantes3), 0)
    
    def test_progresso_trimestre_diferentes_q(self):
        """Validar progresso em diferentes trimestres."""
        # Q3 (jul-set)
        lat_q3 = {202507: 5000.0, 202509: 3000.0}  # Agosto faltando
        prog_q3, total_q3, faltantes_q3 = progresso_trimestre(lat_q3, "2025Q3")
        
        self.assertEqual(prog_q3, 2)
        self.assertEqual(total_q3, 3)
        self.assertEqual(faltantes_q3, [202508])
    
    def test_trimestre_de_mapeamento(self):
        """Validar mapeamento correto de meses para trimestres."""
        self.assertEqual(trimestre_de(202501), "2025Q1")  # Janeiro -> Q1
        self.assertEqual(trimestre_de(202503), "2025Q1")  # Março -> Q1
        self.assertEqual(trimestre_de(202504), "2025Q2")  # Abril -> Q2
        self.assertEqual(trimestre_de(202506), "2025Q2")  # Junho -> Q2
        self.assertEqual(trimestre_de(202507), "2025Q3")  # Julho -> Q3
        self.assertEqual(trimestre_de(202509), "2025Q3")  # Setembro -> Q3
        self.assertEqual(trimestre_de(202510), "2025Q4")  # Outubro -> Q4
        self.assertEqual(trimestre_de(202512), "2025Q4")  # Dezembro -> Q4
    
    def test_ultimo_yyyymm_funcional(self):
        """Testar função ultimo_yyyymm com DataFrame simulado."""
        # DataFrame com dados de exemplo
        data = {
            'yyyymm': [202501, 202502, 202503, 202507],
            'valor': [100, 200, 300, 400]
        }
        df = pd.DataFrame(data)
        
        ultimo = ultimo_yyyymm(df)
        self.assertEqual(ultimo, 202507)
        
        # DataFrame vazio
        df_vazio = pd.DataFrame({'yyyymm': []})
        ultimo_vazio = ultimo_yyyymm(df_vazio)
        self.assertEqual(ultimo_vazio, 0)
        
        # DataFrame sem coluna yyyymm
        df_sem_col = pd.DataFrame({'outra_col': [1, 2, 3]})
        ultimo_sem_col = ultimo_yyyymm(df_sem_col)
        self.assertEqual(ultimo_sem_col, 0)
    
    def test_meses_simulaveis_funcional(self):
        """Testar função meses_simulaveis."""
        # Último mês foi julho (202507)
        simulaveis = meses_simulaveis(202507)
        esperados = [202508, 202509, 202510, 202511, 202512]
        self.assertEqual(simulaveis, esperados)
        
        # Último mês foi dezembro (202512)
        simulaveis_dez = meses_simulaveis(202512)
        self.assertEqual(simulaveis_dez, [])
        
        # Nenhum mês realizado (ultimo = 0)
        simulaveis_zero = meses_simulaveis(0)
        esperados_zero = [202501, 202502, 202503, 202504, 202505, 202506, 
                          202507, 202508, 202509, 202510, 202511, 202512]
        self.assertEqual(simulaveis_zero, esperados_zero)
    
    def test_edge_cases_calc_mes(self):
        """Testes de casos extremos para calc_mes."""
        # LAT muito alto
        resultado_alto = calc_mes(1000000.0)
        self.assertAlmostEqual(resultado_alto["PIS"], 6500.0, places=2)
        self.assertAlmostEqual(resultado_alto["COFINS"], 30000.0, places=2)
        
        # LAT muito baixo
        resultado_baixo = calc_mes(0.01)
        self.assertAlmostEqual(resultado_baixo["PIS"], 0.0065, places=4)
        self.assertAlmostEqual(resultado_baixo["COFINS"], 0.0003, places=4)


if __name__ == '__main__':
    # Executar todos os testes
    unittest.main(verbosity=2)
