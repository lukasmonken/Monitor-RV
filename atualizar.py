#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Monitor de Carteiras — atualizador de dados (VAROS)
===================================================

O que este script faz:
  1. Lê as carteiras na pasta ./carteiras (um CSV por carteira: ticker, empresa, peso).
  2. Consulta o Yahoo Finance o preço de cada ação (cotação com ~15 min de atraso).
  3. Calcula a variação de cada ação e de cada carteira (ponderada pelos pesos)
     em três janelas: DIA (vs. pregão anterior), SEMANA (7 dias) e MÊS (30 dias).
  4. CIFRA o resultado com usuário+senha (AES-256-GCM) e grava "dados.enc.js".
     O index.html só mostra os dados depois que a pessoa digita o login e a senha.

Como usar (local):
  $ python3 atualizar.py

Na nuvem (GitHub Actions) ele roda sozinho a cada 15 min no horário de pregão.

Login/senha:
  Definidos em MONITOR_USUARIO e MONITOR_SENHA (variáveis de ambiente / secrets).
  Se não estiverem definidos, usa o padrão abaixo (troque, ou defina os secrets).
"""

from __future__ import annotations

import base64
import glob
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

try:
    import pandas as pd
    import requests
    import yfinance as yf
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
except ImportError as e:
    print("Faltam bibliotecas. Rode:  pip install -r requirements.txt")
    print("Detalhe:", e)
    sys.exit(1)


# --------------------------------------------------------------------------- #
# Configuração
# --------------------------------------------------------------------------- #

AQUI = os.path.dirname(os.path.abspath(__file__))
PASTA_CARTEIRAS = os.path.join(AQUI, "carteiras")
# Pasta PÚBLICA (o GitHub Pages serve só ela). O dados.enc.js cifrado é gravado
# aqui; as carteiras e este script ficam FORA dela, sem acesso pela web.
PASTA_SITE = os.path.join(AQUI, "docs")

def _arquivo_local(nome: str) -> str:
    """Lê um arquivo local que NÃO vai para o Git (está no .gitignore).
    Serve para rodar na sua máquina sem precisar exportar variáveis."""
    caminho = os.path.join(AQUI, nome)
    if os.path.exists(caminho):
        with open(caminho, encoding="utf-8-sig") as f:
            return f.read().strip()
    return ""


# ATENÇÃO: este repositório é PÚBLICO. Não existe senha escrita aqui.
# A senha vem do secret MONITOR_SENHA (GitHub Actions) ou, na sua máquina, do
# arquivo senha.local (que está no .gitignore e nunca sobe para o GitHub).
# Usamos "or" (e não o 2º argumento de get) DE PROPÓSITO: no GitHub Actions um
# secret não definido chega como string VAZIA, não ausente.
USUARIO = os.environ.get("MONITOR_USUARIO") or "VAROS"
SENHA = os.environ.get("MONITOR_SENHA") or _arquivo_local("senha.local")

# Iterações do PBKDF2 (derivação da chave a partir da senha). Não precisa mexer.
PBKDF2_ITERACOES = 600_000  # recomendação OWASP para PBKDF2-SHA256

# Janelas de variação. "dia" é tratado à parte (vs. o pregão anterior);
# as demais comparam o preço de agora com o pregão mais próximo de X dias atrás.
PERIODOS = {
    "dia":    "Dia",
    "semana": "Semana",
    "mes":    "30 dias",
}
DIAS_ATRAS = {
    "semana": lambda d: d - timedelta(days=7),
    "mes":    lambda d: d - timedelta(days=30),
}

# Quantos fechamentos guardar para o mini-gráfico (sparkline).
PONTOS_SPARKLINE = 44  # ~2 meses de pregões

# Benchmark de cada carteira: (rótulo exibido, símbolo no Yahoo).
# Os índices da B3 (SMLL/IDIV/IFIX) não têm histórico no Yahoo, então usamos os
# ETFs que os replicam como proxy (retorno praticamente igual ao do índice).
#   SMAL11 → Small Caps (SMLL) · DIVO11 → Dividendos (IDIV) · XFIX11 → IFIX
#   SPY    → S&P 500 (ETF mais líquido do mundo)
# A chave é o NOME da carteira (arquivo .csv). Sem entrada aqui = sem benchmark.
BENCHMARKS = {
    "Crescimento":       ("SMLL",    "SMAL11.SA"),
    "Crescimento PRO":   ("SMLL",    "SMAL11.SA"),
    "Renda":             ("IDIV",    "DIVO11.SA"),
    "Renda PRO":         ("IDIV",    "DIVO11.SA"),
    "FIIs":              ("IFIX",    "XFIX11.SA"),
    "FIIs PRO":          ("IFIX",    "XFIX11.SA"),
    "Internacional":     ("S&P 500", "SPY"),
    "Internacional PRO": ("S&P 500", "SPY"),
}

# Setor de cada ativo (por ticker; um ticker tem o mesmo setor em toda carteira).
# Usado para a "exposição por setor". Ativos sem setor aqui não entram na quebra.
SETORES = {
    # Ações
    "BBAS3": "Banco",          "BBDC4": "Banco",         "BMGB4": "Banco",
    "ABCB4": "Banco",          "SLCE3": "Agronegócio",   "KLBN11": "Celulose",
    "AZZA3": "Varejo de Moda", "PRIO3": "Petróleo e Gás","WIZC3": "Seguros",
    "KEPL3": "Indústria",      "VAMO3": "Logística",     "SEER3": "Educação",
    "BRST3": "Telecom",        "ALPK3": "Estacionamentos",
    # FIIs (todos os "Recebíveis" juntos — middle risk + imobiliários)
    "AFHI11": "Recebíveis", "OUJP11": "Recebíveis",
    "KNCR11": "Recebíveis", "RBHG11": "Recebíveis",
    "RBFM11": "Fundo de Fundos",          "RBRP11": "Lajes Corporativas",
    "RCRB11": "Lajes Corporativas",       "RBVA11": "Varejo",
    "RZAT11": "Galpões Logísticos",       "VILG11": "Galpões Logísticos",
    "RZTR11": "Agronegócio",              "VISC11": "Shoppings Centers",
}

# Tradução dos setores GICS (usados nas ponderações setoriais dos ETFs internacionais).
SETOR_EN_PT = {
    "technology": "Tecnologia", "communication_services": "Comunicação",
    "consumer_cyclical": "Consumo Cíclico", "consumer_defensive": "Consumo Defensivo",
    "healthcare": "Saúde", "financial_services": "Financeiro", "energy": "Energia",
    "industrials": "Indústria", "utilities": "Utilidades",
    "basic_materials": "Materiais Básicos", "real_estate": "Imobiliário",
    "realestate": "Imobiliário",
}


# --------------------------------------------------------------------------- #
# 1) Ler as carteiras
# --------------------------------------------------------------------------- #

def _detecta_sep(cabecalho: str) -> str:
    """Detecta o separador (',' ou ';') UMA vez, pela linha de cabeçalho do arquivo.
    Detectar por linha quebra quando o peso usa vírgula decimal (ex.: 'PETR4;9,52'
    do Excel em PT-BR): a heurística por linha empataria e cortaria no lugar errado."""
    return ";" if cabecalho.count(";") > cabecalho.count(",") else ","


def _split_linha(linha: str, sep: str) -> list[str]:
    """Separa a linha pelo separador do arquivo (detectado no cabeçalho)."""
    return [c.strip() for c in linha.split(sep)]


def ler_carteira(caminho: str) -> list[dict]:
    """Lê uma carteira a partir de um arquivo CSV (uso local)."""
    with open(caminho, encoding="utf-8-sig") as f:
        return _parse_carteira(f.read().splitlines())


def _parse_carteira(linhas_brutas: list[str]) -> list[dict]:
    """
    Interpreta as linhas de uma carteira e devolve [{ticker, empresa, peso, mercado}].
    Formato esperado (cabeçalho na 1ª linha):  ticker,empresa,peso[,mercado]
    - 'empresa' é opcional; se faltar, usa o próprio ticker.
    - 'peso' é opcional; se faltar (na linha ou na carteira toda), todos ficam
      com peso igual. O peso é o percentual de alocação (a soma não precisa dar
      exatamente 100 — o cálculo normaliza sozinho).
    """
    linhas = [l for l in linhas_brutas if l.strip()]
    if not linhas:
        return []

    # Separador do arquivo (detectado uma vez no cabeçalho) e detecção de cabeçalho.
    sep = _detecta_sep(linhas[0])
    cabecalho = _split_linha(linhas[0].lower(), sep)
    tem_cab = "ticker" in cabecalho
    idx_tk = cabecalho.index("ticker") if tem_cab else 0
    idx_emp = cabecalho.index("empresa") if (tem_cab and "empresa" in cabecalho) else 1
    idx_peso = cabecalho.index("peso") if (tem_cab and "peso" in cabecalho) else 2
    idx_merc = cabecalho.index("mercado") if (tem_cab and "mercado" in cabecalho) else -1
    corpo = linhas[1:] if tem_cab else linhas

    ativos: list[dict] = []
    for linha in corpo:
        campos = _split_linha(linha, sep)
        if not campos or not campos[0]:
            continue
        ticker = campos[idx_tk].upper() if len(campos) > idx_tk else ""
        if not ticker:
            continue
        empresa = campos[idx_emp] if len(campos) > idx_emp and campos[idx_emp] else ticker
        peso = None
        if len(campos) > idx_peso and campos[idx_peso]:
            try:
                peso = float(campos[idx_peso].replace("%", "").replace(",", "."))
            except ValueError:
                peso = None
        # mercado: "US" = ativo em bolsa dos EUA (sem .SA, cotado em US$);
        # qualquer outra coisa (ou vazio) = B3, em R$.
        mercado = "BR"
        if idx_merc >= 0 and len(campos) > idx_merc and campos[idx_merc]:
            mercado = campos[idx_merc].upper()
        ativos.append({"ticker": ticker, "empresa": empresa,
                       "peso": peso, "mercado": mercado})

    # Se nenhum peso foi informado, distribui igualmente.
    if all(a["peso"] is None for a in ativos) and ativos:
        for a in ativos:
            a["peso"] = round(100 / len(ativos), 4)
    else:
        for a in ativos:  # linhas sem peso ficam com 0
            if a["peso"] is None:
                a["peso"] = 0.0
    return ativos


def carteiras_do_texto(texto: str) -> dict[str, list[dict]]:
    """
    Lê as carteiras do secret MONITOR_CARTEIRAS. Formato: blocos começando com
    '### Nome da carteira', seguidos do CSV (ticker,empresa,peso[,mercado]):

        ### Crescimento
        ticker,empresa,peso
        BBAS3,Banco do Brasil,16.67
        ...

        ### Internacional
        ticker,empresa,peso,mercado
        QQQM,Invesco NASDAQ 100,36,US
    """
    blocos: dict[str, list[str]] = {}
    nome = None
    for linha in texto.splitlines():
        if linha.strip().startswith("###"):
            nome = linha.strip().lstrip("#").strip()
            if nome:
                blocos[nome] = []
        elif nome is not None and linha.strip():
            blocos[nome].append(linha)
    resultado: dict[str, list[dict]] = {}
    for n, linhas in blocos.items():
        ativos = _parse_carteira(linhas)
        if ativos:
            resultado[n] = ativos
    return resultado


def carregar_carteiras() -> dict[str, list[dict]]:
    """Monta {nome_carteira: [ativos...]}.
    1) do secret MONITOR_CARTEIRAS (é assim que roda no GitHub Actions, para as
       carteiras NÃO ficarem no repositório público);
    2) senão, dos CSVs em ./carteiras (uso local — a pasta está no .gitignore)."""
    texto = os.environ.get("MONITOR_CARTEIRAS", "") or _arquivo_local("carteiras.local.txt")
    if texto.strip():
        resultado = carteiras_do_texto(texto)
        if resultado:
            for nome, ativos in resultado.items():
                print(f"  • {nome:22s} {len(ativos):2d} ativos  (secret)")
            return resultado

    resultado = {}
    arquivos = sorted(glob.glob(os.path.join(PASTA_CARTEIRAS, "*.csv")))
    for caminho in arquivos:
        nome = os.path.splitext(os.path.basename(caminho))[0]
        ativos = ler_carteira(caminho)
        if ativos:
            resultado[nome] = ativos
            print(f"  • {nome:22s} {len(ativos):2d} ativos")
    return resultado


# --------------------------------------------------------------------------- #
# 2) Baixar preços do Yahoo Finance
# --------------------------------------------------------------------------- #

def simbolo_yahoo(ticker: str, mercado: str) -> str:
    """Converte o ticker no símbolo do Yahoo conforme o mercado.
    US -> como está (ex.: QQQM, cotado em US$); BR -> acrescenta .SA (ex.: PETR4.SA)."""
    if "." in ticker:            # já é um símbolo completo
        return ticker
    if (mercado or "BR").upper() == "US":
        return ticker
    return f"{ticker}.SA"


def baixar_precos(simbolos: list[str]) -> pd.DataFrame:
    """Baixa ~90 dias de fechamento ajustado dos símbolos do Yahoo informados.
    Devolve um DataFrame com uma coluna por SÍMBOLO."""
    simbolos = sorted(set(simbolos))
    inicio = (datetime.now() - timedelta(days=95)).strftime("%Y-%m-%d")
    fim = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")

    dados = yf.download(
        simbolos, start=inicio, end=fim, interval="1d",
        auto_adjust=True, progress=False, threads=True, group_by="column",
    )
    if dados is None or dados.empty:
        raise RuntimeError("O Yahoo não retornou dados. Verifique a conexão.")

    close = dados["Close"]
    if isinstance(close, pd.Series):  # 1 símbolo só vira Series
        close = close.to_frame(name=simbolos[0])
    if getattr(close.index, "tz", None) is not None:
        close.index = close.index.tz_localize(None)
    return close


# --------------------------------------------------------------------------- #
# 3) Cálculo das variações
# --------------------------------------------------------------------------- #

def variacoes_acao(serie: pd.Series) -> tuple[dict, float | None, list]:
    """Para UMA ação: {dia, semana, mes} (decimal ou None), preço e sparkline."""
    serie = serie.dropna()
    ret = {p: None for p in PERIODOS}
    if serie.empty:
        return ret, None, []

    data_atual = serie.index[-1]
    preco = float(serie.iloc[-1])

    # DIA: preço de agora vs. o pregão imediatamente anterior.
    if len(serie) >= 2:
        anterior = float(serie.iloc[-2])
        if anterior:
            ret["dia"] = round(preco / anterior - 1, 6)

    # SEMANA / MÊS: vs. o pregão mais próximo de X dias atrás.
    for chave, calc in DIAS_ATRAS.items():
        alvo = pd.Timestamp(calc(data_atual))
        if alvo < serie.index[0]:
            continue
        passado = serie.asof(alvo)
        if pd.notna(passado) and passado:
            ret[chave] = round(preco / float(passado) - 1, 6)

    spark = [round(float(v), 2) for v in serie.iloc[-PONTOS_SPARKLINE:]]
    return ret, round(preco, 2), spark


def variacoes_carteira(ativos: list[dict], por_ticker: dict,
                       close: pd.DataFrame) -> tuple[dict, list]:
    """
    Variação da carteira = média das variações das ações PONDERADA pelos pesos.
    Para cada período, normaliza os pesos apenas sobre as ações que têm dado
    naquela janela (uma ação recém-listada não distorce o mês, por ex.).
    Também devolve um mini-índice normalizado (base 100) para o sparkline.
    """
    ret: dict[str, float | None] = {}
    for p in PERIODOS:
        num = den = 0.0
        for a in ativos:
            r = por_ticker.get(a["ticker"], {}).get("retornos", {}).get(p)
            w = a["peso"] or 0.0
            if r is not None and w > 0:
                num += w * r
                den += w
        ret[p] = round(num / den, 6) if den > 0 else None

    # Sparkline: índice ponderado normalizado (cada ação parte de 1.0 na janela).
    cols = [a["ticker"] for a in ativos if a["ticker"] in close.columns]
    spark: list[float] = []
    if cols:
        janela = close[cols].dropna(how="all").iloc[-PONTOS_SPARKLINE:]
        base = janela.apply(lambda c: c.dropna().iloc[0] if c.notna().any() else pd.NA)
        rel = janela.divide(base)  # cada coluna vira 1.0 no início
        pesos = pd.Series({a["ticker"]: (a["peso"] or 0.0)
                           for a in ativos if a["ticker"] in cols})
        for _, linha in rel.iterrows():
            validos = linha.dropna()
            w = pesos.reindex(validos.index).fillna(0.0)
            if w.sum() > 0:
                spark.append(round(float((validos * w).sum() / w.sum() * 100), 3))
    return ret, spark


# --------------------------------------------------------------------------- #
# 4) Cifragem (AES-256-GCM com chave derivada de usuário+senha)
# --------------------------------------------------------------------------- #

def cifrar(texto: str, usuario: str, senha: str) -> dict:
    """Cifra 'texto' com uma chave derivada de usuário+senha. Devolve o blob."""
    segredo = f"{usuario}\n{senha}".encode("utf-8")
    salt = os.urandom(16)
    iv = os.urandom(12)
    chave = hashlib.pbkdf2_hmac("sha256", segredo, salt, PBKDF2_ITERACOES, dklen=32)
    ct = AESGCM(chave).encrypt(iv, texto.encode("utf-8"), None)  # ct = cifra||tag
    b64 = lambda b: base64.b64encode(b).decode()
    return {"v": 1, "kdf": "PBKDF2-SHA256", "iter": PBKDF2_ITERACOES,
            "salt": b64(salt), "iv": b64(iv), "ct": b64(ct)}


# --------------------------------------------------------------------------- #
# Macro: DI (CDI) e IPCA 12m do Banco Central (API pública SGS, grátis)
# --------------------------------------------------------------------------- #

def _sgs(codigo: int) -> dict:
    """Último ponto de uma série do SGS/Bacen. Devolve {valor, data}."""
    url = (f"https://api.bcb.gov.br/dados/serie/bcdata.sgs.{codigo}"
           f"/dados/ultimos/1?formato=json")
    r = requests.get(url, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
    r.raise_for_status()
    d = r.json()
    return {"valor": float(d[-1]["valor"]), "data": d[-1]["data"]}


def puxar_macro() -> dict:
    """DI/CDI anualizado (série 4389) e IPCA acumulado em 12 meses (série 13522).
    Só muda nas divulgações (IPCA mensal, Selic no Copom); em falha, devolve None
    nos campos e a interface mostra '—'."""
    macro = {"cdi": None, "cdi_data": None, "ipca12m": None, "ipca_data": None,
             "dolar": None, "dolar_data": None}
    try:
        c = _sgs(4389); macro["cdi"] = c["valor"]; macro["cdi_data"] = c["data"]
    except Exception as e:
        print("  ! Não consegui o CDI no Bacen:", repr(e)[:80])
    try:
        i = _sgs(13522); macro["ipca12m"] = i["valor"]; macro["ipca_data"] = i["data"]
    except Exception as e:
        print("  ! Não consegui o IPCA no Bacen:", repr(e)[:80])
    try:  # série 1 = dólar comercial (venda), cotação oficial diária
        d = _sgs(1); macro["dolar"] = d["valor"]; macro["dolar_data"] = d["data"]
    except Exception as e:
        print("  ! Não consegui o dólar no Bacen:", repr(e)[:80])
    return macro


def buscar_setores_etfs(etf_map: dict) -> dict:
    """{ticker: {setor_pt: fração}} a partir das ponderações setoriais de cada ETF
    (yfinance funds_data). É o que dá a exposição setorial das carteiras
    internacionais (Tecnologia, Financeiro, Energia...). ETFs sem dado são ignorados."""
    out: dict[str, dict] = {}
    for tk, sim in etf_map.items():
        try:
            sw = yf.Ticker(sim).funds_data.sector_weightings
        except Exception as e:
            print(f"  ! Sem setor do ETF {tk}: {repr(e)[:60]}")
            continue
        if not sw:
            continue
        dist: dict[str, float] = {}
        for en, v in sw.items():
            if v and v > 0:
                pt = SETOR_EN_PT.get(en)
                if pt is None:
                    # Setor fora do dicionário: o rótulo viria cru do Yahoo. As
                    # chaves GICS são ASCII, então manter só letras e espaço
                    # impede qualquer caractere de marcação de chegar à página
                    # (a página já escapa, mas a fonte também não deve confiar).
                    pt = re.sub(r"[^A-Za-z ]", "", en.replace("_", " ")).strip().title()
                    if not pt:
                        continue
                dist[pt] = dist.get(pt, 0.0) + float(v)
        if dist:
            out[tk] = dist
    return out


# --------------------------------------------------------------------------- #
# 5) Orquestração
# --------------------------------------------------------------------------- #

def main() -> None:
    print("=" * 62)
    print("  MONITOR DE CARTEIRAS — atualização de dados")
    print("=" * 62)

    if not SENHA:
        print("\nERRO: nenhuma senha definida (o repositório é público, então a")
        print("senha NÃO fica no código).")
        print("  • No GitHub: crie o secret MONITOR_SENHA")
        print("    (Settings > Secrets and variables > Actions).")
        print("  • Na sua máquina: crie o arquivo 'senha.local' com a senha dentro.")
        sys.exit(1)

    print("\n[1/4] Lendo carteiras...")
    carteiras = carregar_carteiras()
    if not carteiras:
        print("\nNenhuma carteira encontrada. Coloque CSVs em carteiras/ "
              "(colunas: ticker,empresa,peso) e rode de novo.")
        sys.exit(1)

    mapa_yahoo: dict[str, str] = {}
    moeda_por_ticker: dict[str, str] = {}
    for ativos in carteiras.values():
        for a in ativos:
            mapa_yahoo[a["ticker"]] = simbolo_yahoo(a["ticker"], a.get("mercado", "BR"))
            moeda_por_ticker[a["ticker"]] = "USD" if (a.get("mercado", "BR").upper() == "US") else "BRL"
    tickers = sorted(mapa_yahoo)

    # Símbolos dos benchmarks das carteiras presentes.
    bench_simbolos = {BENCHMARKS[n][1] for n in carteiras if n in BENCHMARKS}

    CRIPTO_SIM = {"BTC-USD", "USDBRL=X"}  # para o card do Bitcoin (R$ e US$)
    todos = sorted(set(mapa_yahoo.values()) | bench_simbolos | CRIPTO_SIM)
    print(f"\n[2/4] Baixando cotações de {len(tickers)} ativos "
          f"(+{len(bench_simbolos)} benchmarks) no Yahoo Finance...")
    close_sym = baixar_precos(todos)

    # DataFrame com uma coluna por TICKER (para os cálculos das ações/carteiras).
    close = pd.DataFrame(index=close_sym.index)
    for tk, sim in mapa_yahoo.items():
        if sim in close_sym.columns:
            close[tk] = close_sym[sim]

    # Variações de cada benchmark (uma vez por símbolo).
    bench_ret: dict[str, dict] = {}
    for sim in bench_simbolos:
        if sim in close_sym.columns:
            bench_ret[sim] = variacoes_acao(close_sym[sim])[0]

    # Ponderações setoriais dos ETFs internacionais (exposição por setor real).
    etf_map: dict[str, str] = {}
    for ats in carteiras.values():
        for a in ats:
            if a.get("mercado", "BR").upper() == "US":
                etf_map[a["ticker"]] = a["ticker"]
            elif a["ticker"] == "SPXR11":
                etf_map["SPXR11"] = "SPY"   # ETF de S&P na B3 -> setores via SPY
    print("  Buscando setores dos ETFs internacionais...")
    setores_etf = buscar_setores_etfs(etf_map)

    print("\n[3/4] Calculando variações...")
    por_ticker: dict[str, dict] = {}
    sem_dados: list[str] = []
    for t in tickers:
        if t in close.columns:
            ret, preco, spark = variacoes_acao(close[t])
        else:
            ret, preco, spark = {p: None for p in PERIODOS}, None, []
        if preco is None:
            sem_dados.append(t)
        por_ticker[t] = {"retornos": ret, "preco": preco, "spark": spark}

    print("  Buscando DI (CDI) e IPCA no Banco Central...")
    macro = puxar_macro()

    # Data do último PREGÃO da B3 (ações/FIIs em R$). Ignora cripto/câmbio/ETF dos
    # EUA, que negociam em dias sem pregão na B3 e adiantariam a data.
    cols_b3 = [t for t in close.columns if moeda_por_ticker.get(t) == "BRL"]
    base_datas = close[cols_b3].dropna(how="all") if cols_b3 else close_sym
    data_ref = base_datas.index[-1].strftime("%d/%m/%Y") if not base_datas.empty else None
    saida = {
        "atualizado_em": datetime.now(ZoneInfo("America/Sao_Paulo")).strftime("%d/%m/%Y %H:%M"),
        "data_pregao": data_ref,
        "periodos": PERIODOS,
        "macro": macro,
        "carteiras": [],
    }
    for nome, ativos in carteiras.items():
        ret_cart, spark_cart = variacoes_carteira(ativos, por_ticker, close)
        soma_peso = sum(a["peso"] or 0.0 for a in ativos)
        lista_ativos = []
        for a in ativos:
            d = por_ticker.get(a["ticker"], {})
            lista_ativos.append({
                "ticker": a["ticker"],
                "empresa": a["empresa"],
                "setor": (max(setores_etf[a["ticker"]], key=setores_etf[a["ticker"]].get)
                          if a["ticker"] in setores_etf
                          else SETORES.get(a["ticker"], "")),
                "peso": round(a["peso"] or 0.0, 4),
                "moeda": moeda_por_ticker.get(a["ticker"], "BRL"),
                "preco": d.get("preco"),
                "retornos": d.get("retornos", {p: None for p in PERIODOS}),
                "spark": d.get("spark", []),
            })

        # Exposição por setor: cada ativo distribui seu peso entre seus setores.
        # Ação/FII => um setor (SETORES). ETF => vários setores (setores_etf).
        setor_peso: dict[str, float] = {}
        for a in ativos:
            if a["ticker"] in setores_etf:
                dist = setores_etf[a["ticker"]]
            else:
                s = SETORES.get(a["ticker"], "")
                dist = {s: 1.0} if s else {}
            w = a["peso"] or 0.0
            for s, frac in dist.items():
                setor_peso[s] = setor_peso.get(s, 0.0) + w * frac
        tot_s = sum(setor_peso.values())
        setores_list = sorted(
            [{"setor": s, "pct": round(v / tot_s * 100, 2)} for s, v in setor_peso.items()],
            key=lambda x: -x["pct"]) if tot_s > 0 else []
        bench = None
        b = BENCHMARKS.get(nome)
        if b and b[1] in bench_ret:
            bench = {"label": b[0], "retornos": bench_ret[b[1]]}
        saida["carteiras"].append({
            "nome": f"Academy {nome}",
            "n_ativos": len(ativos),
            "soma_peso": round(soma_peso, 2),
            "retornos": ret_cart,
            "benchmark": bench,
            "setores": setores_list,
            "spark": spark_cart,
            "ativos": lista_ativos,
        })

    # ---- Card especial do Bitcoin (ativo único, mostrado em R$ e US$) ----
    if "BTC-USD" in close_sym.columns and "USDBRL=X" in close_sym.columns:
        btc_usd_serie = close_sym["BTC-USD"].dropna()
        ret_usd, preco_usd, spark_usd = variacoes_acao(btc_usd_serie)
        # BTC em R$ no MESMO calendário do BTC-USD: o dólar do fim de semana usa a
        # última cotação útil (ffill). Sem isso, "Dia"/preço em US$ e R$ divergiriam
        # (BTC negocia sáb/dom, o dólar não).
        usdbrl_ff = close_sym["USDBRL=X"].reindex(btc_usd_serie.index).ffill()
        btc_brl_serie = (btc_usd_serie * usdbrl_ff).dropna()
        ret_brl, preco_brl, _ = variacoes_acao(btc_brl_serie)
        saida["carteiras"].append({
            "nome": "Bitcoin",
            "tipo": "cripto",
            "n_ativos": 1,
            "soma_peso": 100.0,
            "retornos": ret_usd,           # valorização em US$ (principal)
            "benchmark": None,
            "setores": [],
            "spark": spark_usd,
            "extra": {                     # valorização em R$ + preço em US$
                "ret_brl": ret_brl,
                "preco_usd": preco_usd,
                "preco_brl": preco_brl,
            },
            "ativos": [{
                "ticker": "BTC", "empresa": "Bitcoin", "setor": "", "peso": 100.0,
                "moeda": "USD", "preco": preco_usd, "retornos": ret_usd, "spark": spark_usd,
            }],
        })
        print(f"  Bitcoin: US$ {preco_usd} (R$ {preco_brl})")

    print("\n[4/4] Cifrando e gravando dados.enc.js...")
    os.makedirs(PASTA_SITE, exist_ok=True)

    # Só recifra/regrava quando os DADOS mudaram (ignorando o carimbo de hora).
    # Como salt/iv são aleatórios a cada execução, o arquivo cifrado sempre difere
    # byte a byte; sem esta checagem o robô faria commit a cada rodada mesmo sem
    # mudança real (mercado fechado, dispatch manual). Guardamos um hash do
    # conteúdo em .datahash (na raiz, fora do site) para comparar entre execuções.
    dados_sem_hora = {k: v for k, v in saida.items() if k not in ("atualizado_em", "macro")}
    # tira o card cripto do hash: BTC/USDBRL variam 24/7 e disparariam commit sempre.
    dados_sem_hora["carteiras"] = [c for c in saida["carteiras"] if c.get("tipo") != "cripto"]
    hash_atual = hashlib.sha256(
        json.dumps(dados_sem_hora, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()
    caminho_hash = os.path.join(AQUI, ".datahash")
    hash_anterior = None
    if os.path.exists(caminho_hash):
        with open(caminho_hash, encoding="utf-8") as f:
            hash_anterior = f.read().strip()

    if hash_atual == hash_anterior:
        print("  Sem mudança nos dados desde a última execução — nada a regravar.")
        print("=" * 62)
        return

    texto = json.dumps(saida, ensure_ascii=False, separators=(",", ":"))
    blob = cifrar(texto, USUARIO, SENHA)
    caminho = os.path.join(PASTA_SITE, "dados.enc.js")
    with open(caminho, "w", encoding="utf-8") as f:
        f.write("window.DADOS_CIFRADO = ")
        json.dump(blob, f)
        f.write(";\n")
    with open(caminho_hash, "w", encoding="utf-8") as f:
        f.write(hash_atual)

    usou_padrao = not os.environ.get("MONITOR_SENHA")
    print("\n" + "=" * 62)
    print(f"  Pronto! Pregão de referência: {data_ref}")
    print(f"  Carteiras: {len(carteiras)} · Ações: {len(tickers)}")
    print(f"  Gerado: dados.enc.js (cifrado)")
    print(f"  Login: usuário='{USUARIO}'"
          + ("  (senha PADRÃO do código)" if usou_padrao else "  (senha via secret)"))
    if sem_dados:
        print(f"  Aviso: sem cotação para {len(sem_dados)}: {', '.join(sem_dados)}")
    print("=" * 62)


if __name__ == "__main__":
    main()
