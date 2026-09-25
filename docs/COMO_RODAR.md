# Como rodar o braço no Gazebo na sua máquina

Passo a passo do zero até ver o braço do mestrado se mexendo no Gazebo. Tudo
roda dentro do Docker: você não instala ROS nem Gazebo no seu sistema.

> **O que foi testado e o que não foi.** Todos os comandos abaixo foram
> executados num Linux sem monitor (Gazebo sem janela e janelas num display
> virtual). **Não** foram testados no Windows/WSL2, com monitor de verdade nem
> com webcam. Se algo falhar nesses pontos, a seção
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

### 3. Conferir, no terminal do Ubuntu (WSL)

```bash
docker version          # deve mostrar Client e Server
echo $DISPLAY           # deve mostrar :0 (é o WSLg)
```

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
git clone -b claude/consolidacao-mestrado-pxdelq \
  https://github.com/Calima94/Consolida-o_Projetos_de_mestrado.git
cd Consolida-o_Projetos_de_mestrado
```

Se o repositório for privado, o `git clone` pede autenticação do GitHub (use um
[token pessoal](https://docs.github.com/pt/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens)
como senha). Depois do merge na `main`, o `-b claude/...` deixa de ser
necessário.

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

Baixa uns 2 GB (ROS 2 Lyrical + Gazebo Jetty) e leva alguns minutos. Só
precisa repetir quando o código mudar.

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

### 5. O sistema do mestrado completo: sEMG → classificador → braço

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

### 6. Modo espelho: o braço do Gazebo copia o seu

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

### 7. Captura de dados (a ferramenta do `Capture_EMG_Data`)

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

### 8. Encerrar

Qualquer uma destas formas encerra tudo, Gazebo inclusive:

- **Ctrl+C** no terminal onde rodou o comando;
- `docker compose -f docker/compose.yaml stop`;
- `./scripts/stop.sh` (o botão "Stop" do mestrado).

---

## Se algo der errado

| Sintoma | O que fazer |
|---|---|
| `permission denied` no `docker` | Linux: faça os passos pós-instalação e abra outro terminal. Windows: o Docker Desktop precisa estar aberto e com a integração WSL ligada |
| A janela não abre (Linux) | Rode `xhost +local:` e confira se usou `-f docker/compose.gui.yaml` |
| A janela não abre (Windows) | `echo $DISPLAY` no Ubuntu deve dar `:0`; atualize o WSL (`wsl --update` no PowerShell) e confira se usou `-f docker/compose.wsl.yaml` |
| `error gathering device information ... /dev/dri` (Linux sem aceleração gráfica) | Apague os blocos `devices:` do `docker/compose.gui.yaml`: sem `/dev/dri` o OpenGL do container cai sozinho para renderização por software. Ou rode sem janela (`GUI=false`) |
| Gazebo lento no Windows | Esperado: no WSL a renderização é por software. O braço é simples e continua utilizável |
| `ros2 topic pub` não mexe o braço | Deixe o `-w 1`: ele espera o simulador ser descoberto antes de publicar |
| Espelho marca o braço errado | Troque `FLIP` (`true`/`false`) ou `ARM=left` |
| Captura não termina | Alguma categoria não recebe amostras: aumente `TOLERANCE`, reduza `SAMPLES`, ou encerre com Ctrl+C (o que foi gravado é salvo) |
| `Myo dongle not found!` | Confira o dispositivo (`ls /dev/ttyACM*`) e passe `MYO_TTY=/dev/ttyACM0` com `-f docker/compose.myo.yaml` |
