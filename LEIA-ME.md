# Monitor de Carteira — VAROS Academy Renda Variável

Painel para acompanhar, **em tempo quase real (~15 min)**, a performance das
carteiras da VAROS Academy: a variação de **cada carteira** e de **cada ativo**,
nas janelas **Dia**, **Semana** e **Mês**, com **benchmark** e **alpha** por
carteira. A página é protegida por **login e senha** (os dados ficam cifrados;
sem a senha, nada aparece).

Identidade visual VAROS: fundo preto, paleta verde-turquesa, fonte Instrument Sans.

---

## Como funciona

```
   ┌──────────────┐   consulta o Yahoo,    ┌───────────────────┐   login+senha   ┌──────────────────┐
   │ atualizar.py │  calcula e CIFRA os    │ docs/dados.enc.js  │  descriptografa │  docs/index.html │
   │   (Python)   │ ─────────────────────► │  (cifrado)         │ ──────────────► │   (interface)    │
   └──────────────┘                        └───────────────────┘   no navegador  └──────────────────┘
     roda na nuvem                                                                a equipe acessa
     a cada 15 min                                                                por um link
```

- **O Python faz o trabalho pesado**: lê as carteiras, busca preços no Yahoo,
  calcula as variações ponderadas e os benchmarks, e **cifra tudo** (AES-256).
- **O navegador é a vitrine**: com o login e a senha certos, ele descriptografa
  o arquivo ali mesmo (Web Crypto) e desenha o painel. Sem a senha, é ilegível.

---

## Segurança: por que existe a pasta `docs/`

O GitHub Pages publica **tudo o que está na pasta que ele serve**. Se as
carteiras e o `atualizar.py` (que tem a senha) ficassem nessa pasta, qualquer um
poderia lê-los pela URL — e o login perderia o sentido.

Por isso o projeto é dividido:

| Fica em… | O quê | Publicado na web? |
|----------|-------|-------------------|
| **`docs/`** | `index.html`, `assets/`, `dados.enc.js` (cifrado) | **Sim** (é o que o Pages serve) |
| **raiz** | `atualizar.py`, `carteiras/`, `requirements.txt`, `.github/` | **Não** |
| **`pdfs/`** | PDFs de origem das carteiras | **Não** (no `.gitignore`) |

Ou seja: publica-se só o `docs/` (cifrado). O resto fica no repositório
**privado**, fora do alcance da web. Configure o Pages para servir **`/docs`**
(veja `COMO-PUBLICAR.md`).

---

## Login e senha

- Padrão: usuário **`VAROS`**, senha **`varos@2026`**.
- Para trocar: mude `USUARIO`/`SENHA` no topo do `atualizar.py`, **ou** (melhor)
  defina os *secrets* `MONITOR_USUARIO` / `MONITOR_SENHA` no GitHub. É uma senha
  **única** para todos — sem cadastro de usuários.
- Depois de trocar, rode o `atualizar.py` de novo para regerar o `dados.enc.js`.

---

## As carteiras (pasta `carteiras/`)

Uma carteira = **um CSV** em `carteiras/`. O **nome do arquivo** vira o nome no
painel (ex.: `Renda.csv` → "Renda").

```
ticker,empresa,peso,mercado
BBDC4,Bradesco,14.29
QQQM,Invesco NASDAQ 100,36,US
```

- **ticker** — código do ativo (sem `.SA`; o script adiciona para papéis da B3).
- **empresa** — nome amigável (opcional).
- **peso** — percentual de alocação. É o que torna a variação da carteira
  **ponderada**. A soma não precisa dar 100 (normaliza sozinho). Sem a coluna =
  pesos iguais.
- **mercado** — opcional. `US` = ativo em bolsa dos EUA (cotado em **US$**, sem
  `.SA`); vazio ou `BR` = B3, em **R$**. As carteiras Internacionais usam isso.

**Benchmark de cada carteira:** definido no dicionário `BENCHMARKS` no topo do
`atualizar.py`, pelo **nome da carteira**. Hoje:

| Carteira | Benchmark | Como é medido (ETF que replica) |
|----------|-----------|----------------------------------|
| Crescimento / Crescimento PRO | SMLL (Small Caps) | SMAL11 |
| Renda / Renda PRO | IDIV (Dividendos) | DIVO11 |
| FIIs / FIIs PRO | IFIX | XFIX11 |
| Internacional / Internacional PRO | S&P 500 | SPY |

Os índices SMLL/IDIV/IFIX não têm histórico no Yahoo, então usamos os ETFs que
os replicam como proxy (retorno praticamente igual ao do índice). O **Alpha** é
quanto a carteira rendeu acima do benchmark **no mês**.

---

## Rodar no seu computador (opcional)

Só para gerar/testar localmente. Na nuvem, o robô faz sozinho.

```bash
pip install -r requirements.txt
python3 atualizar.py
```

Gera `docs/dados.enc.js`. Para ver o painel, abra `docs/index.html` (pelo link
https do GitHub Pages é o ideal; localmente o Chrome abre pelo `file://`).

---

## Períodos e cálculos

- **Dia** = agora vs. o **fechamento do pregão anterior** (variação de hoje).
- **Semana** = vs. o pregão mais próximo de **7 dias** atrás.
- **30 dias** = vs. o pregão mais próximo de **30 dias** atrás (janela móvel — não é
  o mês corrente).
- **Variação da carteira** = média das variações dos ativos **ponderada pelos
  pesos**; por janela, só entram os ativos com dado naquela janela.
- Preços do **Yahoo Finance**, fechamento **ajustado** (proventos e
  desdobramentos), atraso de ~15 min. Ativos **US$** têm a variação medida em dólar.

## Além do desempenho

- **Exibir → Setores:** exposição por setor de cada carteira (ações/FIIs por setor;
  internacionais pela composição real dos ETFs, via Yahoo).
- **Exibir → Destaques:** maiores altas e baixas por período (hoje / semana / 30 dias).
- **Topo:** Dólar (Bacen, série 1), CDI (série 4389) e IPCA 12m (série 13522), da API pública do Banco Central.
- **Bitcoin** (na visão "Todas"): preço em US$ · R$ e variação nas duas moedas.

Ferramenta de **acompanhamento** — não é recomendação de investimento.
