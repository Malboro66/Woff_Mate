# ✈️ WoFF BHaH II Watchdog

**WoFF BHaH II Watchdog** é uma aplicação companion em segundo plano para o simulador de voo *Wings over Flanders Fields: Between Heaven and Hell II* (WOFF BHaH II).

A aplicação monitoriza em tempo real as pastas de campanha do jogo, extrai dados de ficheiros de texto e binários ofuscados, e alimenta uma base de dados SQLite local. Além da extração de dados, o projeto introduz uma camada de RPG (Fadiga, Moral, Stress) e um gerador de Diário de Bordo narrativo, preparando o terreno para uma futura interface gráfica (WoFFBase UI).

---

## 🌟 Funcionalidades Principais

- **Monitorização em Tempo Real** — deteta automaticamente quando o jogo guarda progresso e processa os ficheiros sem interferir com o motor (Read-Only).
- **Engenharia Reversa de Ficheiros Binários** — decifra o `Pilot1Dossier.txt` e os ficheiros de esquadrões (Scratchpad), removendo a camada de ofuscação Hex e investigando a cifra interna (suspeita de ser XOR) implementada pela OBD Software.
- **Extração de Dados Pessoais** — nome real do piloto, data e local de nascimento, biografia gerada pelo jogo, ID da fotografia e membros do esquadrão (AI Wingmen) com patentes e biografias.
- **Plano de Voo e Mapa Tático** — lê o `mission.log` gerado pelo motor CFS3, extrai waypoints, converte coordenadas para Graus Decimais e regista a linha da frente de batalha.
- **Catálogo de Medalhas e Esquadrões** — no arranque, varre as pastas do jogo e cataloga todas as medalhas disponíveis e os parâmetros de todos os esquadrões.
- **Sistema RPG (Fase 2)** — calcula Fadiga, Moral e Stress do piloto com base no histórico de missões, ferimentos e tempo de voo.
- **Diário de Bordo Dinâmico** — gera entradas de texto imersivas para cada missão voada, baseadas no resultado, aeronave e vitórias obtidas.
- **Base de Dados SQLite Robusta** — transações atómicas e thread-safe para evitar corrupção de dados.

---

## ⚠️ Estado Atual do Projeto

| Componente | Estado |
|---|---|
| Camada Hex de ofuscação do Dossier | ✅ Decifrada |
| Cifra interna do Dossier (suspeita XOR) | 🔴 Em investigação |
| Parser de ficheiros de piloto (`;`-delimited) | ✅ Confirmado e funcional |
| Refatoração modular do watchdog | ✅ Concluída |

A decifragem completa do `Pilot1Dossier.txt` é o bloqueador atual do projeto. Próximos passos em avaliação:
1. Diff entre duas snapshots do Dossier (mesmo piloto, momentos diferentes) para isolar o padrão da cifra.
2. Decompilação do *Pilot Log Editor* (ferramenta Java da comunidade, por JJJ65) para comparar lógica de decifragem.
3. Alternativa: contornar o Dossier inteiramente, usando apenas os `.txt` delimitados por `;` já confirmados como fonte de dados fiável.

---

## 🏗 Arquitetura do Projeto
Woff_Mate/
│
├── config.py                  # Carrega e valida config.json (auto-deteção via Registo do Windows)
├── models.py                  # Dataclasses para Pilotos, Missões, etc.
├── maps.py                    # Tabelas estáticas de tradução e expressões regulares
├── normalization.py           # Limpeza de dados (datas, nações, conversão de coordenadas)
├── database.py                # Gestor SQLite (tabelas, upsert, RPG stats)
├── discovery.py                # Logger do modo de descoberta de ficheiros
├── handler.py                  # Eventos do sistema (Watchdog), ThreadPool, routing de parsers
├── campaign_engine.py          # Orquestrador da Fase 2 (RPG + Diário)
├── rpg_system.py                # Motor de cálculo de Fadiga, Moral e Stress
├── narrative_generator.py       # Gera os textos do Diário de Bordo
├── medal_cataloger.py            # Lê a pasta de Medalhas do jogo
├── squadron_cataloger.py          # Desofusca e lê a pasta de Esquadrões (Scratchpad)
├── woff_watchdog.py                # Orquestrador principal e CLI (ponto de entrada)
│
├── parsers/
│   ├── init.py
│   ├── xml_parser.py            # Lê ficheiros XML de configuração do motor (CFS3)
│   ├── mission_log_parser.py     # Extrai briefing, waypoints e membros do voo
│   ├── pilot_data_parser.py       # Lê Pilot{N}Log.txt, Claims.txt, Squads.txt (delimitados por ;)
│   └── dossier_parser.py           # [EM DESENVOLVIMENTO] Decifra o Pilot{N}Dossier.txt (Hex ✅ / cifra interna 🔴)
│
├── tests/
│   ├── test_normalization.py
│   └── test_xml_parser.py
│
├── config.example.json         # Modelo neutro versionado para a configuração local
└── requirements.txt

> **Nota:** os dados reais e confiáveis do piloto vêm dos ficheiros `.txt` delimitados por `;` (via `pilot_data_parser.py`), não do XML. O `xml_parser.py` trata apenas de ficheiros de configuração do motor CFS3.
>
> O `config.json` é criado pela auto-deteção ou copiado localmente a partir de
> `config.example.json`; por conter caminhos próprios da instalação, permanece
> ignorado pelo Git.

---

## 📦 Instalação

### Pré-requisitos
- Python 3.10 ou superior
- WoFF BHaH II instalado (a aplicação tenta detetar o caminho automaticamente via Registo do Windows)

### Passos

1. Clone o repositório e abra um terminal na sua raiz.
2. Crie um ambiente virtual:
```bash
   python -m venv .venv
```
3. Ative o ambiente virtual:
   - **Windows (PowerShell):** `.venv\Scripts\Activate.ps1`
   - **Windows (CMD):** `.venv\Scripts\activate.bat`
4. Instale o projeto e as dependências em modo editável:
```bash
   pip install -e .
```

Para desenvolvimento, instale também o `pytest` e o `pyright` conforme necessário.

---

## ⚙️ Configuração

Crie a configuração local a partir do modelo neutro incluído no repositório:

```bash
cp config.example.json config.json
```

No Windows PowerShell, use `Copy-Item config.example.json config.json`. Depois,
edite `watch_paths` e `export_path` com os caminhos da sua instalação. Se não
existir um `config.json`, o programa também tenta detetar o WoFF através do
Registo do Windows e cria o ficheiro quando a deteção é bem-sucedida.

O `config.json` contém caminhos próprios de cada instalação e não é versionado.
Também são locais e ignorados pelo Git os bancos SQLite, logs, ambientes
virtuais, caches, resultados de build e configurações do VS Code. Assim, instalar,
testar e executar um clone novo não adiciona esses artefactos ao repositório.

| Chave | Descrição |
|---|---|
| `watch_paths` | Pastas vigiadas pelo watchdog (normalmente `Pilots` e `Logs`) |
| `export_path` | Localização da base de dados SQLite (`woff_data.db`) |

### Atualização de versões anteriores

Se já possui um `config.json`, faça uma cópia antes de atualizar o repositório.
Como esse ficheiro era anteriormente rastreado, o Git poderá removê-lo durante a
atualização. Nesse caso, restaure a cópia depois; o `config.json` continuará local
e ignorado pelo Git.

---

## 🚀 Como Usar

Todos os comandos devem ser executados a partir da raiz do projeto.

### Modo Normal (Produção)
Inicia a monitorização em segundo plano. Corre até ser interrompido (`Ctrl+C`).
```bash
python -m woff.woff_watchdog
# Após instalar com `pip install -e .`:
woff-watchdog
```

### Modo Debug de Ficheiro Único
Testa a extração de um ficheiro específico e imprime os dados no terminal. Ideal para testar novos parsers sem abrir o jogo.
```bash
python -m woff.woff_watchdog --parse-file "C:\OBDSoftware\WOFF\OBDWW1 Over Flanders Fields\campaigns\CampaignData\Pilots\Pilot1Dossier.txt"
woff-watchdog --parse-file "C:\OBDSoftware\WOFF\OBDWW1 Over Flanders Fields\campaigns\CampaignData\Pilots\Pilot1Dossier.txt"
```

### Modo Descoberta
Regista em `woff_discovery.log` todos os ficheiros que o jogo gera, com um preview do conteúdo. Útil para mapear onde o jogo guarda novas informações.
```bash
python -m woff.woff_watchdog --discover
woff-watchdog --discover
```

### Ajuda
Mostra todas as opções disponíveis no CLI.
```bash
python -m woff.woff_watchdog --help
woff-watchdog --help
```

---

## 🎲 Sistema RPG e Diário de Bordo (Fase 2)

O Watchdog não se limita a ler ficheiros — ele interpreta-os. Sempre que uma missão termina e o `Pilot1Log.txt` é atualizado:

1. O `handler.py` insere a missão na base de dados.
2. O `CampaignEngine` é ativado em segundo plano.
3. Lê as últimas 10 missões do piloto na base de dados.
4. O `RPGSystem` calcula:
   - **Fadiga** — baseada em missões recentes (últimos 3 dias) e ferimentos.
   - **Moral** — baseada em vitórias, danos sofridos e estado atual do piloto.
   - **Stress** — baseado em contactos inimigos e aterragens forçadas.
5. O `NarrativeGenerator` cria um texto para o Diário de Bordo (ex: *"O céu de Flandres. Hoje voámos num Nieuport 10... O meu camarada Rene foi ferido."*).
6. Tudo é guardado nas tabelas `pilot_rpg_stats` e `diary_entries` da base de dados SQLite.

---

## 🗺 Roadmap do Projeto

- [x] **Fase 1 (Core):** Monitorização, Extração de Dados, Engenharia Reversa parcial do Dossier, Base de Dados SQLite.
- [~] **Fase 2 (Lógica):** Sistema de RPG (Fadiga/Moral/Stress), Gerador de Diário de Bordo — *decifragem completa do Dossier pendente.*
- [ ] **Fase 3 (UI PyQt6):** Interface gráfica (Dashboard do Piloto, Mapa Tático com coordenadas, Visualizador do Diário).
- [ ] **Fase 4 (Distribuição):** Empacotamento com PyInstaller e criação de instalador.

---

## 🛠 Tecnologias Utilizadas

- **Python 3.10+**
- **Watchdog** — monitorização de eventos do sistema de ficheiros
- **SQLite3** — base de dados local embutida (sem servidor)
- **Dataclasses & Threading** — modelos de dados limpos e processamento assíncrono
- **xml.etree.ElementTree** — parsing de ficheiros de configuração do motor CFS3

---

## ⚖️ Aviso Legal

Este projeto é uma ferramenta de terceiros não oficial, criada para fins de análise pessoal e educacional. Não modifica ficheiros do jogo (funciona em modo Read-Only) e não está afiliado à OBD Software.
