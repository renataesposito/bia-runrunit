import sys
sys.path.insert(0, r"c:\Users\caio\Documents\GitHub\bia-runrunit\runrun_report")
import data_processor
import database
import pandas as pd
database.init_database()
escopo = data_processor.load_escopo()
print("Qtd_ano unicos nao-zero:", sorted(escopo[escopo['qtd_ano']>0]['qtd_ano'].unique().tolist()))
print("Cooldown unicos:", sorted(escopo["cooldown_dias"].unique().tolist()))
print("Total contrato (sum qtd_ano):", int(escopo["qtd_ano"].sum()))
print("Total previsto acumulado:", int(escopo["previsto_acumulado"].sum()))
database.save_escopo(escopo)
print("OK")
