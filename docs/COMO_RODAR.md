# Como rodar o braço no Gazebo na sua máquina

Passo a passo do zero até ver o braço do mestrado se mexendo no Gazebo. Tudo
roda dentro do Docker: você não instala ROS nem Gazebo no seu sistema.

> **O que foi testado e o que não foi.** Todos os comandos abaixo foram
> executados num Linux sem monitor (Gazebo sem janela e janelas num display
> virtual). No **Windows 11 + WSL2 + Docker Desktop** (Windows 11 build 26200,
> WSL 2.7.14.0, WSLg 1.0.73.2, Ubuntu 26.04.1, Docker Desktop 4.92.0) foram
> testados todos os passos:
> - o [passo 4](#4-ver-o-braço-no-gazebo): a janela do Gazebo abre e o braço
>   se move;
> - o [passo 5](#5-pilotar-o-braço-pelo-navegador): a interface web, no
>   navegador do Windows;
> - os passos 6 a 8, pelo menu, com o vídeo do mestrado e sEMG reproduzido. No
>   modo espelho, as janelas da câmera e do Gazebo abrem juntas.
>
> **Ainda não** foram testados o Linux com monitor de verdade, a interface web
> no Linux e no celular, a webcam e a faixa Myo. Se algo falhar, a seção
> [Se algo der errado](#se-algo-der-errado) cobre os casos mais prováveis.

Escolha o seu sistema:

- [Windows 11 (WSL2 + Docker Desktop)](#windows-11)
- [Linux (Ubuntu ou similar)](#linux)

Depois, siga para [Rodando](#rodando): é igual nos dois, muda só o arquivo de
janela (`compose.wsl.yaml` no Windows, `compose.gui.yaml` no Linux).

---

## Windows 11

### 1. Instalar o WSL2 com Ubuntu

No **PowerShell como administrador**:

```powershell
wsl --install -d Ubuntu
```

Reinicie se pedir. Na primeira abertura do "Ubuntu" (menu Iniciar), crie
usuário e senha. O Windows 11 já traz o WSLg, que mostra janelas Linux no
Windows; não precisa instalar servidor X.

### 2. Instalar o Docker Desktop

1. Baixe e instale o [Docker Desktop](https://www.docker.com/products/docker-desktop/).
2. Em *Settings → General*, deixe marcado **Use the WSL 2 based engine**.
3. Em *Settings → Resources → WSL integration*, ative a integração com o
   **Ubuntu**.
4. Deixe o Docker Desktop aberto enquanto usar o projeto.

> **Se o Docker Desktop disser "Virtualization not detected"** (ou o WSL
> reclamar de virtualização), o processador está com a virtualização desligada
> ou o Windows está sem os componentes necessários:
>
> 1. **Diagnóstico:** Gerenciador de Tarefas → *Desempenho* → *CPU* → linha
>    **Virtualização**.
> 2. **Se estiver "Desabilitado", ligue na BIOS/UEFI.** Para entrar:
>    *Configurações → Sistema → Recuperação → Inicialização avançada → Reiniciar
>    agora → Solução de problemas → Opções avançadas → Configurações de Firmware
>    UEFI*. Procure **Intel Virtualization Technology / VT-x** (Intel) ou
>    **SVM Mode / AMD-V** (AMD), ative, salve e saia.
> 3. **Se já estiver "Habilitado"**, ative os componentes do Windows no
>    PowerShell como administrador e reinicie:
>
>    ```powershell
>    dism.exe /online /enable-feature /featurename:VirtualMachinePlatform /all /norestart
>    dism.exe /online /enable-feature /featurename:Microsoft-Windows-Subsystem-Linux /all /norestart
>    bcdedit /set hypervisorlaunchtype auto
>    ```
>
>    Depois do reinício: `wsl --update` e `wsl --set-default-version 2`.
> 4. Abra o Docker Desktop de novo.
>
> Em computador institucional, a BIOS pode estar protegida por senha; aí o
> passo 2 depende da TI. Se o próprio Windows roda numa máquina virtual, é
> preciso habilitar a virtualização aninhada no hospedeiro.

### 3. Conferir, no terminal do Ubuntu (WSL)

```bash
docker version          # deve mostrar Client e Server
echo $DISPLAY           # deve mostrar :0 (é o WSLg)
```

Depois de baixar o projeto ([passo 1 de "Rodando"](#1-baixar-o-projeto)),
use a verificação rápida antes da sequência, e de novo a cada sessão (o Docker
Desktop pode ter ficado fechado depois de uma reinicialização do Windows):

```bash
scripts/check_docker.sh
```

Ela só lê o estado, sem mudar nada. Confere se o `docker` do Ubuntu é o da
integração (`/usr/bin/docker`), se o motor responde e se não ficou nenhum
simulador do projeto rodando. Em caso de problema, diz a causa provável e o
conserto; só termina com "Tudo certo" (código 0) se tudo passar.

O que esperar (medido no Windows 11 com o Docker Desktop 4.92): ao fechar o
Docker Desktop, ele retira o comando `docker` do Ubuntu na hora, mesmo com o
terminal aberto, e a verificação mostra a causa provável A (código 1). Logo
depois de abrir o Docker Desktop, enquanto a integração não chega, ela mostra
"Nem a causa A nem a B" e manda esperar ~10 s; o comando e o motor ficam
prontos praticamente juntos (código 0). O código 3, "motor não respondeu", é
raro: só apareceu uma vez, logo depois de mandar o Docker Desktop parar.

**Todos os comandos daqui para frente são no terminal do Ubuntu (WSL)**, não
no PowerShell. Trabalhe dentro do Linux (`~`), não em `/mnt/c/...`: é muito
mais rápido.

Arquivo de janela para o Windows: `docker/compose.wsl.yaml`.

---

## Linux

### 1. Instalar o Docker

Siga a [instalação oficial do Docker Engine](https://docs.docker.com/engine/install/ubuntu/)
e, para não precisar de `sudo`, os
[passos pós-instalação](https://docs.docker.com/engine/install/linux-postinstall/).
O plugin Compose v2 vem junto (`docker compose version`).

### 2. Liberar as janelas do container (uma vez por sessão gráfica)

```bash
xhost +local:
```

Arquivo de janela para o Linux: `docker/compose.gui.yaml`.

---

## Rodando

**Atalho: o painel.** Depois do passo 1, o painel faz os passos 2 a 9 com
botões no navegador, inclusive a interface web do passo 5, os testes e "parar
tudo". Cada botão usa os padrões abaixo; as opções ficam em "Opções", no
próprio cartão. Ao lado, a coluna "Saída" mostra o comando que rodou e o que ele
imprimiu. Roda no terminal do Ubuntu, fora do Docker:

```bash
python3 scripts/painel.py --abrir
```

Ele abre `http://localhost:8000` no navegador. Deixe o terminal aberto
enquanto usa o painel; fechá-lo (ou Ctrl+C) encerra o painel. O braço, o
sistema completo e o modo espelho continuam rodando depois disso, até você
clicar em Parar ou rodar `./scripts/stop.sh`. O painel só deixa rodar uma
simulação (ou captura) por vez.

**Atalho de terminal: o menu.** `scripts/menu.sh` faz os mesmos passos, pergunta
por pergunta, no lugar das telas do mestrado; só a interface web (passo 5) ainda
não está nele. Cada opção pergunta os campos (Enter
aceita o padrão entre colchetes), mostra o comando e pergunta se executa. Ele
descobre sozinho o arquivo de janela. Os passos abaixo são os mesmos comandos,
para rodar à mão.

```bash
scripts/menu.sh
```

Nos comandos abaixo, `JANELA` é o arquivo de janela do seu sistema. Defina uma
vez por terminal:

```bash
# Windows (WSL):
export JANELA=docker/compose.wsl.yaml
# Linux:
export JANELA=docker/compose.gui.yaml
```

### 1. Baixar o projeto

```bash
cd ~
git clone https://github.com/Calima94/Consolida-o_Projetos_de_mestrado.git
cd Consolida-o_Projetos_de_mestrado
```

Se o repositório for privado, o `git clone` pede autenticação do GitHub (use um
[token pessoal](https://docs.github.com/pt/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens)
como senha).

Se você já tinha clonado antes com `-b claude/consolidacao-mestrado-pxdelq`,
passe para a `main` (a branch principal) e atualize:

```bash
git checkout main && git pull
```

### 2. Baixar os dados do mestrado

```bash
./scripts/fetch_legacy_data.sh
```

Baixa para `data/` os CSVs de sEMG, a matriz e os scores históricos e o vídeo
da ferramenta de captura, todos de commits fixos e com SHA-256 conferido.

### 3. Construir a imagem (só na primeira vez)

```bash
docker compose -f docker/compose.yaml build
```

Baixa uns 2 GB (ROS 2 Lyrical + Gazebo Jetty), compila o `rosbridge` da
interface web (menos de 1 min; precisa de acesso ao GitHub) e leva alguns
minutos. Só precisa repetir quando o código mudar.

### 4. Ver o braço no Gazebo

```bash
docker compose -f docker/compose.yaml -f $JANELA run --rm shell \
  ros2 launch mestrado_bringup sim.launch.py
```

Abre a janela do Gazebo com o braço em pé sobre um pedestal azul. Em **outro
terminal** (na mesma pasta, com o `JANELA` definido), mova o cotovelo para 90°
(1,57 rad):

```bash
docker compose -f docker/compose.yaml run --rm shell \
  ros2 topic pub --once -w 1 /arm/elbow/cmd_pos std_msgs/msg/Float64 "{data: 1.57}"
```

O cotovelo dobra em cerca de 3 s, com a dinâmica do mestrado (controle P,
kp = 1). O ombro é `/arm/shoulder/cmd_pos`. Para voltar, publique `0.0`.

Encerre com **Ctrl+C** no primeiro terminal.

### 5. Pilotar o braço pelo navegador

Uma página no lugar do `ros2 topic pub`: setas e deslizadores para ombro,
cotovelo e garra, o braço desenhado de lado, o comando e a posição real lado a
lado, e uma parada de emergência. O Gazebo roda sem janela: quem desenha o
braço é o navegador.

```bash
# Windows (Docker Desktop):
docker compose -f docker/compose.yaml -f docker/compose.desktop.yaml up braco web
# Linux:
docker compose -f docker/compose.yaml up braco web
```

Abra **http://localhost:8080** (no Windows, no navegador do próprio Windows).
O ponto verde e "conectado" no topo dizem que a página alcançou o ROS e está
recebendo o estado das juntas.

- **Setas:** um clique move 5° (0,5 cm na garra); segurando, repete. O
  deslizador vai direto ao valor.
- **Comando × real:** o braço cheio é o que o Gazebo mede (`/joint_states`);
  o contorno tracejado azul é o alvo que o controlador está seguindo
  (`/arm/joint_targets`). A diferença some em ~3 s, com a dinâmica do mestrado.
  Um comando vindo de fora, como o `ros2 topic pub` do passo 4, também aparece.
- **Garra:** os dedos abrem para os lados, fora do plano da vista lateral, por
  isso a garra aparece também de frente, embaixo. A abertura é a distância
  entre as faces internas dos dedos: de 6 a 22 cm.
- **PARAR** (ou a tecla **Esc**): o controlador zera a velocidade das juntas e
  ignora qualquer comando (da página, do terminal ou do classificador) até você
  clicar em **Liberar**. Ao liberar, o braço fica onde está; não retoma o
  comando de antes da parada.
- As faixas dos deslizadores (ombro ±90°, cotovelo ±150°) evitam posições em
  que o braço bate no pedestal ou se dobra sobre si mesmo. O modelo aceita
  ±180°.

Para ver a janela do Gazebo ao lado, acrescente `-f $JANELA` e ponha
`GUI=true` antes do comando. Com `sim` no lugar de `braco` (passo 6), a
página mostra o classificador comandando o braço, e PARAR também o interrompe.

Por enquanto a página só abre neste computador: no Windows as portas são
publicadas em `127.0.0.1`, porque o `rosbridge` não tem senha. O celular é a
próxima etapa. Encerre com **Ctrl+C** ou `./scripts/stop.sh`.

Por que o Windows precisa do `compose.desktop.yaml`: no Docker Desktop, a rede
`host` dos containers fica dentro da máquina virtual do Docker e não é
alcançável nem do Windows nem do Ubuntu. O arquivo acrescenta um repasse de
portas (`web-portas`); os detalhes estão no cabeçalho dele. No Linux, nada
disso é preciso.

### 6. O sistema do mestrado completo: sEMG → classificador → braço

Sem Myo, o sEMG vem das gravações do mestrado, tocadas em tempo real.

```bash
# treina os 5 classificadores (uma vez); os modelos vão para models/
docker compose -f docker/compose.yaml run --rm train

# sobe Gazebo + reprodução do sEMG + kNN + controlador
GUI=true docker compose -f docker/compose.yaml -f $JANELA up sim
```

O braço alterna entre 0° e 90° conforme o classificador reconhece cada trecho
da gravação. No terminal, o `angle_monitor` mostra alvo e posição do ombro e do
cotovelo a cada segundo, como o painel do mestrado.

Para outro classificador: `MODEL=lda_6-10-20220_mav_temporal_latest.joblib`
antes do comando (os nomes estão em `models/`).

**Ver os resultados do treino** (a aba "Results" da tela do mestrado; opção 5
do menu):

```bash
docker compose -f docker/compose.yaml run --rm train \
  ros2 run mestrado_emg analyze_legacy /data/6_10_20220.csv --out /models/analise
```

Imprime uma tabela de acurácia, validação cruzada e AUC e grava em
`models/analise/6-10-20220_mav_temporal/`:

- `scores.png`: acurácia de cada classificador;
- `confusao.png`: matrizes de confusão;
- `roc.png`: curva ROC;
- `sinal_bruto.png`: sinal bruto;
- `features_por_canal.png` e `features_c1_c2.png`: features por categoria;
- `resumo.md`: o resumo.

No Windows, abra a pasta com `cd models/analise && explorer.exe .`. Opções:
`--feature rms`, `--split legacy`, `--cv 5` (partições), `--pair 3 4` (canais
do gráfico de dispersão). Se o comando não existir, a imagem é de antes desta
versão: reconstrua (passo 3). O que esses resultados querem dizer está em
[`ANALISE_RESULTADOS.md`](ANALISE_RESULTADOS.md).

**Wavelet, níveis, camadas e janela**, como na tela de treino do mestrado,
valem para `train_legacy` e `analyze_legacy`. No painel, ficam em "Parâmetros
do sinal"; no menu, respondendo `s` a "ajustar frequência, filtros, janela e
wavelet?". Por exemplo:

```bash
docker compose -f docker/compose.yaml run --rm train \
  ros2 run mestrado_emg train_legacy /data/6_10_20220.csv --out /models \
  --wavelet sym4 --levels 2 --wavelet-mode bands --layers 1 2
```

- `--wavelet` aceita as wavelets discretas do PyWavelets (`db7`, `sym4`,
  `coif2`, `haar`...); `--levels`, os níveis da decomposição; `--window-ms`, a
  janela (padrão 250 ms).
- `--wavelet-mode legacy` (padrão) repete o código do mestrado, em que a
  escolha de camadas não faz efeito e só a camada mais grossa é removida.
  `--wavelet-mode bands` mantém só as camadas de `--layers` (1 = a mais fina:
  50–100 Hz a 200 amostras/s; 2 = 25–50 Hz; e assim por diante) e, com
  `--approx`, também a aproximação.
- Escolhas diferentes das do mestrado entram no nome dos modelos e da pasta da
  análise (`..._sym4-n2-D12`), então não apagam os resultados do mestrado. O
  classificador usa na simulação os parâmetros com que foi treinado.
- Se os níveis passarem do que a janela comporta, o comando avisa: a db7 em
  janelas de 250 ms só tem 1 nível útil (o mestrado usava 4).

**Frequência de amostragem e filtros IIR**, também como na tela do mestrado
(D24). `--fs` é a taxa da gravação (padrão 200 Hz, a do Myo); o número de
canais vem do próprio CSV. Os filtros têm três modos:

- `--filters legacy` (padrão): os coeficientes do mestrado, que foram
  projetados para 200 Hz. Em outra taxa eles mudam de lugar (a 1000 Hz o
  passa-altas corta em ~71 Hz e o rejeita-faixa vai para ~300 Hz), e o comando
  avisa;
- `--filters design --highpass-hz 20 --mains-hz 60`: Butterworth calculado
  para a taxa escolhida (`--mains-hz 0` tira o rejeita-faixa);
- `--filters files --highpass-file ... --bandstop-file ...`: coeficientes SOS
  de arquivo, como o app do mestrado. Ponha os arquivos em `data/filtros/`; o
  painel lista o que estiver lá. Aceita o CSV do app (`Filter,Value,...`), 6
  números por linha, JSON ou `.npy`, e recusa filtro instável.

O painel lê a coluna `time` de cada gravação e, se a taxa medida for outra,
oferece "Usar ... Hz". A **parte de teste** do hold-out (`--test-size`,
padrão 30 %) fica no mesmo cartão e no menu.

**Os dados de gestos da disciplina** (8 participantes, 5 gestos, 4 canais a
1000 Hz) têm botão próprio no painel (Manutenção → Dados → Gestos da
disciplina) e opção 11 no menu:

```bash
./scripts/fetch_gesture_data.sh
```

O script baixa os 40 arquivos do Drive da disciplina, confere o SHA-256 de
cada um e grava `data/gestos_1khz.csv` (82 MB) com uma coluna `participante`.
No painel, "Como na disciplina" em "Parâmetros do sinal" põe os parâmetros
com que o app foi usado lá (1000 Hz, RMS, janela de 200 ms, sorteio com 20 %
de teste, semente 5). Com essa coluna, a análise acrescenta a validação por
participante: treina com sete pessoas e testa na oitava. Os resultados e o
porquê estão em [`ANALISE_GESTOS.md`](ANALISE_GESTOS.md).

### 7. Modo espelho: o braço do Gazebo copia o seu

Não precisa de sEMG. Com o **vídeo gravado no mestrado**:

```bash
CAMERA=/data/test_2_05.avi FLIP=false \
  docker compose -f docker/compose.yaml -f $JANELA up espelho
```

Abrem duas janelas: a câmera, com o braço marcado, e o Gazebo, com o cotovelo
seguindo o do vídeo. `FLIP=false` porque esse vídeo já foi salvo espelhado.

**Com a sua webcam:**

- **Linux:** acrescente `-f docker/compose.camera.yaml` (usa `/dev/video0`):

  ```bash
  docker compose -f docker/compose.yaml -f $JANELA -f docker/compose.camera.yaml up espelho
  ```

- **Windows:** a webcam normalmente **não** chega ao Linux do WSL2. Grave um
  vídeo curto com o app *Câmera* do Windows (braço de perfil, subindo e
  descendo o antebraço), copie para `data/` e use o arquivo:

  ```bash
  cp "/mnt/c/Users/<seu usuário>/Pictures/Camera Roll/<video>.mp4" data/meu_braco.mp4
  CAMERA=/data/meu_braco.mp4 docker compose -f docker/compose.yaml -f $JANELA up espelho
  ```

Se ele marcar o braço errado, troque `FLIP=false`/`true` ou use `ARM=left`.

### 8. Captura de dados (a ferramenta do `Capture_EMG_Data`)

Precisa de uma fonte de sEMG. Para ver o fluxo funcionando sem hardware (vídeo
do mestrado + sEMG reproduzido):

```bash
CAMERA=/data/test_2_05.avi FLIP=false EMG=replay SAMPLES=200 \
  docker compose -f docker/compose.yaml -f $JANELA run --rm captura
```

A janela mostra o braço em **laranja/vermelho enquanto grava** e verde fora
das categorias. Quando todas as categorias completam, a captura fecha sozinha
e salva `data/captura_<data><n>.csv`, no formato do mestrado mais a coluna
`angle_deg`.

Os campos da tela do mestrado viram variáveis: `N_CATEGORIES` (2–4, ângulos
170/90/60/45°), `TOLERANCE` (± graus), `SAMPLES` (amostras por categoria).
Com `CONTINUOUS=true` grava também fora das categorias, com o ângulo medido,
que é o dado necessário para regressão contínua.

Com o Myo (`EMG=myo` é o padrão), acrescente `-f docker/compose.myo.yaml`. No
Windows, o dongle precisa antes ser ligado ao WSL com
[usbipd](https://learn.microsoft.com/windows/wsl/connect-usb).

### 9. Encerrar

Qualquer uma destas formas encerra tudo, Gazebo inclusive:

- **Ctrl+C** no terminal onde rodou o comando;
- `./scripts/stop.sh` (o botão "Stop" do mestrado): para todos os containers
  do projeto, tanto os de `up` quanto os de `run`;
- `docker compose -f docker/compose.yaml stop`: só para os de `up`. Os de
  `docker compose run` (como o do passo 4) ele **não** para.

Antes de subir um simulador novo, confira com `docker ps` se não ficou outro
rodando (veja a tabela abaixo).

---

## Se algo der errado

| Sintoma | O que fazer |
|---|---|
| Docker Desktop: "Virtualization not detected" | Virtualização desligada na BIOS ou componentes do Windows faltando: ver o quadro no [passo 2 do Windows](#2-instalar-o-docker-desktop) |
| `The command 'docker' could not be found in this WSL 2 distro. We recommend to activate the WSL integration in Docker Desktop settings.` | **Mexer no botão de "WSL integration" costuma NÃO ser o conserto.** Rode `scripts/check_docker.sh`: ele consulta o lado Windows (se o Docker Desktop está rodando e qual é a distro padrão do WSL), diz qual causa é a provável e descarta a outra. **A (a mais comum):** o Docker Desktop não está rodando, por exemplo depois de reiniciar o Windows com "Start Docker Desktop when you sign in" desligado; abra o Docker Desktop e espere o motor subir (~10 s). **B:** a distro padrão do WSL é a `docker-desktop` (acontece quando o Docker Desktop foi instalado antes do Ubuntu), e a integração com a distro padrão nunca chega ao Ubuntu; confira com `wsl --list --verbose` no PowerShell (o `*` marca a padrão), conserte com `wsl --set-default Ubuntu` e reinicie o Docker Desktop. **Nem A nem B** (Docker Desktop rodando e a distro padrão já é o Ubuntu): se ele acabou de abrir, espere ~10 s; se continuar, aí sim ligue a chave do Ubuntu em *Settings > Resources > WSL integration* e clique em *Apply & restart*. **Armadilha:** se `command -v docker` mostrar um caminho em `/mnt/c/...`, é o binário do Windows alcançado por interop, e isso não prova que a integração funciona; o que vale é `/usr/bin/docker` e `docker version` mostrando Client **e** Server |
| `permission denied` no `docker` | Linux: faça os passos pós-instalação e abra outro terminal. Windows: o Docker Desktop precisa estar aberto e com a integração WSL ligada |
| A janela não abre (Linux) | Rode `xhost +local:` e confira se usou `-f docker/compose.gui.yaml` |
| A janela não abre (Windows) | `echo $DISPLAY` no Ubuntu deve dar `:0`; atualize o WSL (`wsl --update` no PowerShell) e confira se usou `-f docker/compose.wsl.yaml` |
| `timed out waiting for /mnt/wslg to be automounted` (Windows) | Seu `docker/compose.wsl.yaml` é anterior à correção: atualize o repositório (`git pull`). O Docker Desktop não consegue montar `/mnt/wslg` (nem `/mnt/host/wslg`); a versão atual usa só o socket X11 em `/tmp/.X11-unix`, que basta para a janela do Gazebo |
| `error gathering device information ... /dev/dri` (Linux sem aceleração gráfica) | Apague os blocos `devices:` do `docker/compose.gui.yaml`: sem `/dev/dri` o OpenGL do container cai sozinho para renderização por software. Ou rode sem janela (`GUI=false`) |
| Gazebo lento no Windows | Esperado: no WSL a renderização é por software (`LIBGL_ALWAYS_SOFTWARE=1`). O braço é simples e continua utilizável. **Não** tente acelerar pela GPU com `/dev/dxg` e o driver `d3d12` do Mesa: foi testado (RTX 5060) e a vista 3D fica preta, sem nenhum quadro desenhado; detalhes no topo de `docker/compose.wsl.yaml` |
| `ros2 topic pub` não mexe o braço | Deixe o `-w 1`: ele espera o simulador ser descoberto antes de publicar |
| Valores estranhos em `/joint_states`, ou o braço não obedece | Provavelmente há **dois simuladores rodando**: como tudo usa a rede do host, eles publicam nos mesmos tópicos e as leituras se misturam, sem erro nenhum. Confira com `docker ps`, pare tudo com `./scripts/stop.sh` e suba um só |
| Espelho marca o braço errado | Troque `FLIP` (`true`/`false`) ou `ARM=left` |
| Captura não termina | Alguma categoria não recebe amostras: aumente `TOLERANCE`, reduza `SAMPLES`, ou encerre com Ctrl+C (o que foi gravado é salvo) |
| `Myo dongle not found!` | Confira o dispositivo (`ls /dev/ttyACM*`) e passe `MYO_TTY=/dev/ttyACM0` com `-f docker/compose.myo.yaml` |
| Painel: "Não consegui usar a porta 8000" | Já há um painel aberto (use a aba que já existe) ou outro programa usa a porta: `python3 scripts/painel.py --abrir --porta 8001` |
| Painel: botão "Iniciar" apagado, com "Pare … antes" | Já há uma simulação ou captura rodando; duas ao mesmo tempo misturariam as leituras. Clique em Parar no cartão dela, ou em Parar tudo |
| `http://localhost:8080` não abre (Windows) | Faltou `-f docker/compose.desktop.yaml`: sem ele, as portas ficam dentro da máquina virtual do Docker. Confira com `docker ps` se o `mestrado-web-portas-1` está de pé |
| Página: "sem conexão com o rosbridge" | O serviço `web` caiu ou não subiu: veja `docker compose -f docker/compose.yaml logs web`. Se aparecer `file 'web.launch.py' was not found` ou `package 'rosbridge_server' not found`, a imagem é anterior a esta versão: reconstrua (passo 3) |
| Página: "conectado, mas sem /joint_states" | O braço não está rodando: suba `braco` (ou `sim`) junto com `web` |
| Página: "sem o arm_controller" | O Gazebo está de pé, mas o controlador não, ou a imagem é anterior a esta versão: reconstrua (passo 3). Sem ele, nem os comandos nem a parada têm efeito |
| PARAR mostra "A parada NÃO foi confirmada" | O controlador não respondeu em 3 s. No simulador, pare tudo com `./scripts/stop.sh`. Com braço físico, corte a alimentação |
