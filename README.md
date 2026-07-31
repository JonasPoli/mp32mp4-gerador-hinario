# Hinário CCB — Gerador de Vídeos e Thumbnails

Pipeline automatizado para geração de vídeos e thumbnails para o **Hinário 5 da Congregação Cristã no Brasil** no YouTube.

---

## Projetos Suportados

| Chave | Nome exibido | Instrumento |
|-------|-------------|-------------|
| `hinario5` | Teclado Yamaha PSR | Teclado |
| `hinos_de_ninar` | Hinos de Ninar | Caixinha de música |
| `orgao_yamaha` | Hinos em Orgão Yamaha | Órgão |
| `piano_yamaha` | Hinos em Piano Yamaha | Piano |
| `coros` | Coros Hinário 5 | Teclado |
| `hinario4` | Teclado Yamaha PSR (H4) | Teclado |
| `brass` | Hinos em Brass (Metais) | Metais (trompete, trombone) |
| `meia_hora` | Hinos de Meia Hora | Órgão Eletrônico Drawbar |
| `orquestra` | Hinos em Orquestra | Orquestra |
| `orquestra2` | Hinos em Orquestra CCB | Orquestra, Órgão, Coral e Naipes |
| `palhetas` | Hinos em Palhetas | Palhetas (oboé, clarinete) |
| `sopro` | Hinos em Sopro | Instrumentos de sopro |
| `string` | Hinos em Cordas (Strings) | Cordas (violino, viola, cello) |


---

## Scripts

### `gerar_videos.py` — Pipeline principal de vídeos
Gera os vídeos completos de cada hino:
1. Seleciona clipes de vídeo de fundo (natureza/flores)
2. Gera o frame inicial com o número e nome do hino (**thumbnail**)
3. Monta a sequência: frame estático → transição blur → clipes de fundo
4. Mixa o áudio MP3 com o vídeo de fundo
5. Salva o MP4 final em `output/`
6. Registra o progresso no banco SQLite (`progresso.db`)

```bash
# Gera todos os hinos pendentes:
python gerar_videos.py

# Gera apenas um hino:
python gerar_videos.py --apenas 290

# Especifica o projeto:
python gerar_videos.py --hinario hinario5

# Força regerar um hino já processado:
python gerar_videos.py --resetar 290 && python gerar_videos.py --apenas 290
```

---

### `gerar_thumb_v01.py` — Gerador de thumbnails (Pipeline v01)
Novo pipeline visual para thumbnails. Cria imagens 1920×1080px com 7 layers:

| Layer | O que é | Como funciona |
|-------|---------|--------------|
| 1 | Frame de vídeo | Frame aleatório extraído de um clipe MP4 com ffmpeg |
| 2 | Overlay de cor | Blend de cor sólida (preset) + vinheta radial nas bordas |
| 3 | Arte de linhas | Textura artística P&B, 12% opacidade |
| 4 | Máscara do canal | Identidade visual em PNG RGBA (moldura, logo, faixa bege) |
| 5 | Número do hino | Fonte Montserrat Black, rotacionado +3.5°, na faixa bege |
| 6 | Nome do hino | Caixa alta, multi-linha, rotacionado +3.5°, sombra difusa |
| 7 | Instrumento | PNG sem fundo, altura total (1080px), canto direito |

```bash
# Gera 10 thumbs aleatórias:
python gerar_thumb_v01.py

# Hinos específicos:
python gerar_thumb_v01.py --numero 53 328 5

# Com preset de cor fixo:
python gerar_thumb_v01.py --numero 53 --preset 2

# Lista os 8 presets disponíveis:
python gerar_thumb_v01.py --listar-presets
```

---

### `gerar_thumbs_batch.py` — Regeneração em lote de thumbnails
Regenera as thumbnails de múltiplos hinos usando o pipeline v01.
Salva em `thumbs/hino-{projeto}-NNN.png` (sobrescreve).

```bash
# Regenera hinos_de_ninar (todos) + orgao_yamaha (concluídos):
python gerar_thumbs_batch.py

# Só um projeto:
python gerar_thumbs_batch.py --projeto hinos_de_ninar

# Só um hino específico:
python gerar_thumbs_batch.py --apenas 53
```

---

### `baixar_videos_flores.py` — Download de clipes de fundo
Baixa clipes de vídeo de natureza de provedores gratuitos (Pexels, Pixabay)
para usar como fundo nos vídeos.

```bash
python baixar_videos_flores.py --query flores --out videos_flores/ --per-page 40
```

---

### `gerar_coletaneas.py` — Coletâneas temáticas
Gera vídeos de coletâneas de múltiplos hinos.

---

## Estrutura de Pastas

```
hinário/
│
├── assets/                      ← Todos os assets visuais do projeto
│   ├── mascaras/                ← Overlay de identidade visual
│   │   └── mascara-do-canal.png ← Máscara principal (moldura + logo CCB)
│   ├── texturas/                ← Texturas decorativas
│   │   └── arte-linhas/         ← PNGs P&B para efeito clarão (12% opac)
│   ├── imagens-base/            ← Imagens base para pipeline legado
│   │   ├── sem-numero.png       ← Base genérica (hinario4/5/coros)
│   │   ├── com-numero.png       ← Variante com campo de número
│   │   ├── hinos_de_ninar.png   ← Base do projeto hinos de ninar
│   │   ├── hinos_de_orgao.png   ← Base do projeto órgão
│   │   └── hinos_de_piano.png   ← Base do projeto piano
│   ├── instrumentos/            ← PNGs dos instrumentos (fundo transparente)
│   │   ├── teclado.png
│   │   ├── orgao.png
│   │   ├── piano.png
│   │   └── caixa-de-musica.png
│   └── logos/                   ← Logos sobrepostos nas thumbnails
│       ├── ninar.png
│       ├── orgao.png
│       └── piano.png
│
├── fontes/                      ← Dados e tipografia
│   ├── Montserrat.ttf           ← Fonte principal (variável, weight 400-900)
│   ├── fonts/                   ← Outras fontes
│   ├── hinario5.csv             ← Lista de hinos (Número, Nome) — Hinário 5
│   ├── hinario4_sequential.csv  ← Lista de hinos — Hinário 4
│   ├── coros.csv                ← Lista de coros
│   └── hinario04.pdf            ← PDF original do Hinário 4
│
├── mp3/                         ← Arquivos de áudio dos hinos
├── videos_flores/               ← Clipes de natureza/flores (fundo dos vídeos)
├── Photos-1-001/                ← Clipes adicionais (biblioteca local)
├── vinheta/                     ← Vinheta de abertura (MP4)
│
├── thumbs/                      ← Thumbnails geradas para upload no YouTube
│   └── v01/                     ← Versões JPG nativas do novo pipeline
├── output/                      ← Vídeos MP4 finais
├── hinos_txt/                   ← Letras dos hinos (TXT individuais + índice)
│
├── projetos.json                ← Configuração de todos os projetos
├── progresso.db                 ← Banco SQLite com status de geração
├── gerar_videos.py              ← Pipeline principal de vídeos
├── gerar_thumb_v01.py           ← Gerador de thumbnails (pipeline v01)
├── gerar_thumbs_batch.py        ← Regeneração em lote de thumbnails
├── gerar_coletaneas.py          ← Gerador de coletâneas temáticas
└── baixar_videos_flores.py      ← Downloader de clipes de fundo
```

---

## Configuração de Projetos (`projetos.json`)

Cada projeto no `projetos.json` define:

```json
{
  "nome_projeto": {
    "nome_exibicao": "Nome que aparece no YouTube",
    "csv_path": "fontes/hinario5.csv",
    "mp3_dir": "mp3",
    "imagem_base": "assets/imagens-base/sem-numero.png",
    "titulo_template": "Hino <numero-do-hino> - <nome-do-hino> | ...",
    "palavras_chaves": "...",
    "descricao": "...",
    "vinheta": "vinheta/vinheta.mp4",
    "desenho": { ... }
  }
}
```

**Variáveis de template disponíveis:**
- `<numero-do-hino>` — número do hino
- `<nome-do-hino>` — nome do hino com acentos
- `<nome-sem-acento>` — nome sem acentos
- `<nome-do-projeto>` — nome de exibição do projeto

---

## Banco de Dados (`progresso.db`)

SQLite com 4 tabelas:

| Tabela | Função |
|--------|--------|
| `videos` | Status de geração por projeto+hino (`pendente`, `processando`, `concluido`, `erro`) |
| `clipes` | Catálogo de clipes de vídeo disponíveis com contagem de usos |
| `downloads` | Histórico de downloads de clipes |
| `config` | Configurações gerais (ex: última query de download) |

---

## Dependências

```bash
pip install Pillow mutagen requests tqdm
brew install ffmpeg
```


## Automação e Pipeline Completo

### `rodar_todos_projetos.sh` (atalho `~/hino.sh`)
Executa o pipeline completo de forma sequencial para todos os projetos configurados em `projetos.json`:
1. Gera o vídeo base (se ainda não existir).
2. Sincroniza e embute as legendas ASS no vídeo.
3. Atualiza o status no banco de dados para `concluido`.

```bash
./rodar_todos_projetos.sh \
  --preset-ffmpeg veryfast \
  --threads-ffmpeg 1 \
  --low-priority \
  --pausa-ffmpeg 1.5 \
  --pausa-entre-hinos 10.0
```

---

### `adicionar_legendas_batch.sh` — Re-processamento de Legendas em Lote
Usado exclusivamente para embutir/corrigir legendas em vídeos base que **já existem** gravados no disco, sem recriar a parte visual do vídeo base.

```bash
./adicionar_legendas_batch.sh \
  --preset-ffmpeg veryfast \
  --threads-ffmpeg 1 \
  --low-priority \
  --pausa-ffmpeg 1.5 \
  --pausa-entre-hinos 10.0
```

> [!CAUTION]
> ### 🚨 ATENÇÃO: NUNCA RODE OS DOIS SCRIPTS AO MESMO TEMPO
> **Não execute `rodar_todos_projetos.sh` e `adicionar_legendas_batch.sh` simultaneamente.**
> 
> **Motivos de Conflito:**
> 1. **Conflito no Banco de Dados (`progresso.db`)**: O script em batch reseta o status para `base_pronto`. Leituras e gravações simultâneas no SQLite causam erros de `database is locked`.
> 2. **Conflito de Arquivos de Vídeo (Race Condition)**: Ambos tentam ler, regravar e renomear os mesmos arquivos MP4 de saída (`output/<projeto>/hino-*.mp4`) simultaneamente, causando corrupção ou falhas de leitura.
> 3. **Conflito de Arquivos Temporários**: Ambos utilizam a pasta `Temp/` para gerar os arquivos `.ass` temporários de legenda, causando sobrescrita entre processos.
> 4. **Sobrecarga Térmica/CPU (Risco de Crash)**: Executar duas instâncias do FFmpeg em paralelo dobra a carga do processador e anula os intervalos de pausa (`--pausa-entre-hinos`), podendo ocasionar desarmamento/crash de hardware no Hackintosh por temperatura ou consumo de voltagem.

---

## Controle de Recursos e Estabilidade de Hardware

Para evitar travamentos e congelamentos da máquina (especialmente em sistemas Hackintosh) durante a renderização intensiva de centenas de hinos:

### Parâmetros Recomendados de Resfriamento
* `--preset-ffmpeg veryfast` (ou `ultrafast`): Reduz o esforço computacional do encoder x264.
* `--threads-ffmpeg 1`: Limita a quantidade de threads por processo do FFmpeg.
* `--low-priority`: Executa chamadas com baixa prioridade no SO (`nice` / `taskpolicy -c background` no macOS).
* `--pausa-ffmpeg 1.5`: Adiciona pausa em segundos após cada invocação do FFmpeg.
* `--pausa-entre-hinos 10.0`: Pausa a execução entre cada hino para permitir que o cooler resfrie a CPU.

### Monitoramento e Diagnóstico
* **`monitor_recursos.py`**: Monitor em segundo plano que registra uso de CPU, RAM, Swap e carga nos logs locais. O log é mantido automaticamente com limite máximo de 5 MB (`logs/monitor_recursos.log`).
* **`analisar_crashes.py`**: Utilitário para ler relatórios de diagnósticos do macOS e correlacionar Kernel Panics com picos de recursos do pipeline.

---

## Regras de Git e Arquivos Ignorados (`.gitignore`)

Para manter o repositório leve e evitar erros no `git push` (limite de 100 MB por arquivo no GitHub):
* **Logs**: O diretório `logs/` e arquivos `*.log` são estritamente ignorados pelo `.gitignore`.
* **Arquivos Temporários**: `_tmp_*`, `_test_*`, `Temp/`, `*.ass`, `_parte_*`, `_concat_*` e `_legendado_*` ficam fora do controle de versão e são limpos automaticamente pelo pipeline.

---

## Rodar rápido

```bash
# Execução padrão do pipeline completo com resfriamento térmico:
python rodar_todos_projetos.sh --pausa-entre-hinos 10 --preset-ffmpeg veryfast --threads-ffmpeg 1 --low-priority

# Gerar coletâneas:
python gerar_coletaneas.py --projeto hinos_de_ninar

# Gerar apenas a thumbnail de um hino específico:
python gerar_videos.py --thumbnail-apenas --numero 53 --projeto orgao_yamaha
```

