# Guia de Estabilidade de Hardware para Hackintosh

Este guia fornece orientações passo a passo para diagnosticar e solucionar instabilidades físicas de hardware (processador, memória RAM e temperatura) no seu Hackintosh que causam desligamentos abruptos ou Kernel Panics durante o pipeline de renderização de vídeo.

---

## 1. Instabilidade na Memória RAM (Erros de "Page Fault")
O FFmpeg e os scripts Python em paralelo carregam e manipulam volumes massivos de dados na RAM. Timings agressivos (perfil XMP) ou módulos de memória instáveis causam corrupção de dados silenciosa, resultando em reboots ou pânicos do tipo `page fault` (erro tipo 14).

### Como Testar a Memória RAM de Forma Confiável:
O teste de memória **deve ser executado fora do macOS**, pois o sistema operacional esconde e protege partes da memória física.

1. **MemTest86 (Recomendado):**
   - Baixe a versão gratuita do [MemTest86](https://www.memtest86.com/) ou [MemTest86+](https://www.memtest86.com/).
   - Grave em um pendrive usando a ferramenta de criação fornecida por eles.
   - Reinicie o Hackintosh, entre no menu de boot da placa-mãe (geralmente F8, F11 ou F12) e selecione o pendrive.
   - Deixe rodar por pelo menos **4 passagens completas** (isso pode levar algumas horas).
   - **Se aparecer qualquer erro (linhas vermelhas):** A memória está instável ou com defeito.

### Como Solucionar na BIOS:
Se o teste do MemTest86 falhar ou se você suspeitar de instabilidade:
- **Desative o XMP/EOCP:** Entre na BIOS e desative o perfil de overclock automático da memória (XMP), deixando-a rodar na frequência padrão de fábrica (geralmente 2133MHz ou 2666MHz). Se os crashes pararem, o problema era o perfil XMP.
- **Ajuste Manual da Voltagem de RAM (DRAM Voltage):** Se quiser manter o XMP, tente aumentar ligeiramente a voltagem das memórias na BIOS (ex: de 1.35V para 1.36V ou 1.37V, mantendo limites seguros).
- **Limpeza Física:** Remova os pentes de memória, limpe os contatos dourados com uma borracha branca escolar macia e reinstale-os firmemente.

---

## 2. Instabilidade no Processador (CPU Core Instável / Queda de Voltagem)
A codificação de vídeo utiliza instruções vetoriais pesadas (AVX). Sob carga total de todos os núcleos, ocorre o fenômeno chamado **Vdroop** (a voltagem fornecida pela placa-mãe para a CPU cai subitamente). Se o núcleo não tiver voltagem suficiente, ele "calcula errado", resultando em Kernel Panic instantâneo (ex: `panic(cpu 4)`).

### Como Estressar a CPU no macOS:
1. **Prime95 (mprime) para macOS:**
   - Baixe o [Prime95 para macOS](https://www.mersenne.org/download/).
   - Execute o binário e selecione a opção **"Small FFTs"** (esta opção estressa agressivamente a CPU e gera o máximo de calor e consumo).
   - Se o computador travar, reiniciar ou der Kernel Panic nos primeiros 10-30 minutos, o processador está instável sob carga pesada.
2. **Monitorar Temperaturas:**
   - Use utilitários como **Intel Power Gadget** ou os sensores do **HWMonitorSMC2** (se você usa VirtualSMC no Hackintosh).
   - Se a temperatura passar de **90°C a 95°C**, a CPU entrará em superaquecimento (Thermal Throttling) ou a placa-mãe desligará o computador instantaneamente para evitar danos físicos.

### Como Solucionar na BIOS:
Se o processador falhar no teste de estresse ou der pânico em núcleos específicos:
- **Load Line Calibration (LLC):** Esta opção na BIOS serve para combater o Vdroop. Altere a configuração de LLC de *Auto* para um perfil intermediário/alto (ex: Level 3 ou Level 4 em placas ASUS/ASRock, ou High/Turbo em Gigabyte). Isso estabiliza a voltagem entregue à CPU sob carga total.
- **Ajustar Undervolt/Curve Optimizer:** Se você fez undervolting (redução manual de voltagem para diminuir o calor):
  - Aumente ligeiramente a voltagem da CPU (Vcore offset).
  - Se estiver usando AMD Ryzen com Curve Optimizer e o log apontar instabilidade em um core específico (ex: Core 4), reduza o valor negativo configurado para esse núcleo específico (ex: mude de -20 para -10 ou -5).
- **Substituir Pasta Térmica:** Se as temperaturas subirem muito rápido sob carga pesada, verifique a montagem do cooler, limpe a poeira e aplique uma pasta térmica de alta qualidade.

---

## 3. Desligamento Repentino Sem Logs (Reboot sem Kernel Panic)
Se o computador simplesmente "apagar" e reiniciar sem gerar tela de erro ou sem criar um arquivo `.panic` na pasta `/Library/Logs/DiagnosticReports/`, o problema quase certamente **não é de software**.

### Causas Físicas Comuns:
1. **Fonte de Alimentação Insuficiente ou Defeituosa:**
   - A GPU e a CPU exigem picos altos de corrente durante a renderização. Se a fonte não conseguir entregar energia estável, os circuitos de proteção da fonte desarmam e o PC desliga.
2. **Superaquecimento Crítico (Shutdown de Proteção):**
   - O chip de monitoramento da placa-mãe desliga a alimentação do sistema instantaneamente se a temperatura da CPU atingir o limite térmico crítico (geralmente 100°C ou 105°C).
3. **Placa-mãe / VRM Superaquecida:**
   - Os reguladores de voltagem (VRM) da placa-mãe alimentam a CPU. Em renderizações longas, se o gabinete não tiver boa ventilação, os VRMs esquentam demais e entram em proteção térmica.
