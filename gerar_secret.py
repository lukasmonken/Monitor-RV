#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Gera o conteúdo do secret MONITOR_CARTEIRAS a partir dos CSVs em ./carteiras.

Como o repositório é PÚBLICO, as carteiras não ficam nele: elas vivem num
"secret" do GitHub. Este script junta os CSVs num único texto para você copiar
e colar no secret.

Uso:
    python3 gerar_secret.py

Depois: GitHub > Settings > Secrets and variables > Actions >
        MONITOR_CARTEIRAS > Update > cole o conteúdo de carteiras.local.txt
"""

import glob
import os

AQUI = os.path.dirname(os.path.abspath(__file__))
SAIDA = os.path.join(AQUI, "carteiras.local.txt")


def main() -> None:
    arquivos = sorted(glob.glob(os.path.join(AQUI, "carteiras", "*.csv")))
    if not arquivos:
        print("Nenhum CSV encontrado em carteiras/. Nada a fazer.")
        return

    partes = []
    for caminho in arquivos:
        nome = os.path.splitext(os.path.basename(caminho))[0]
        with open(caminho, encoding="utf-8-sig") as f:
            corpo = f.read().strip()
        partes.append(f"### {nome}\n{corpo}")

    texto = "\n\n".join(partes) + "\n"
    with open(SAIDA, "w", encoding="utf-8") as f:
        f.write(texto)

    print(f"Pronto! {len(partes)} carteiras -> carteiras.local.txt")
    for caminho in arquivos:
        print("  •", os.path.splitext(os.path.basename(caminho))[0])
    print("\nAgora copie TODO o conteúdo de carteiras.local.txt e cole no secret")
    print("MONITOR_CARTEIRAS (GitHub > Settings > Secrets and variables > Actions).")

    # Setores (mapa ticker->setor) — secret separado MONITOR_SETORES. A lista de
    # tickers é sensível, por isso também não fica no repositório público.
    setores_csv = os.path.join(AQUI, "setores.local.csv")
    if os.path.exists(setores_csv):
        with open(setores_csv, encoding="utf-8-sig") as f:
            n_set = sum(
                1 for l in f
                if l.strip() and not l.strip().startswith("#")
                and l.split(",", 1)[0].strip().lower() != "ticker"
            )
        print(f"\nSetores: {n_set} tickers em setores.local.csv.")
        print("Se entrou um ticker NOVO nas carteiras, atualize setores.local.csv e")
        print("cole o conteúdo dele no secret MONITOR_SETORES (senão a quebra por")
        print("setor ignora esse ticker). Sem ticker novo, não precisa mexer nele.")
    else:
        print("\n(Sem setores.local.csv — a 'exposição por setor' ficará vazia.")
        print(" Crie o arquivo e o secret MONITOR_SETORES se quiser essa quebra.)")

    print("\nDepois rode o robô: aba Actions > Run workflow.")


if __name__ == "__main__":
    main()
