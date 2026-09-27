# Visão e arquitetura — para onde este projeto está indo

> **Para que serve este documento.** O trabalho acontece em sessões separadas, com
> agentes diferentes, e sem isto cada sessão recomeça do zero e refaz decisões já
> tomadas. Leia antes de propor mudanças de arquitetura. A seção
> [Decisões que não devem ser revertidas](#decisões-que-não-devem-ser-revertidas)
> existe porque cada item dela já custou tempo real.
>
> Escrito em 26/09/2026 e atualizado no mesmo dia, com a guia 1 (braço) pronta;
> em 27/09/2026 entrou o movimento real (Reach&Grasp, D27).
> Atualize-o quando uma decisão mudar — não deixe o documento envelhecer em
> silêncio.

---

## 1. Onde o projeto está hoje

Estado **verificado rodando** em Windows 11 + WSL2 + Docker + ROS 2, em 26/09/2026:

| Módulo | Como se roda | Estado |
|---|---|---|
| Captura (sEMG + ângulo do cotovelo) | menu, opção 9 | funciona com vídeo gravado e sEMG reproduzido |
| Treino dos classificadores | menu, opção 4 | 5 classificadores + referência de amplitude |
| Análise dos resultados | menu, opção 5 | 6 figuras PNG + resumo + JSON |
| Braço no Gazebo | menu, opção 6 | janela abre, cotovelo obedece comando |
| Sistema completo | menu, opção 7 | sEMG → classificador → braço, laço fechado |
| Modo espelho | menu, opção 8 | vídeo → visão computacional → braço |
| Movimento real (Reach&Grasp, D27) | menu, opção 14; painel, cartão "Movimento real" (COMO_RODAR, passo 8) | cotovelo humano gravado (Vicon) → braço, o alvo da regressão contínua. **Testado só no Linux e no CI**, ainda não no Windows |
| **Interface web — guia 1 (braço)** | `up braco web` → `http://localhost:8080` (COMO_RODAR, passo 5) | navegador → rosbridge → ROS 2 → Gazebo sem janela; comando × real; parada de emergência |

O modelo é `braco_antebraco_garra`: ombro, cotovelo e **garra** (duas juntas).
Os tópicos de comando já existem: `/arm/{shoulder,elbow,gripper_left,gripper_right}/{cmd_pos,cmd_vel}`.
O estado real volta em `/joint_states`; o alvo que o controlador segue, em
`/arm/joint_targets`. A parada de emergência é o serviço `/arm/estop`.

**O que NÃO se consegue testar nesta máquina, e por quê:**

- **webcam ao vivo** — o WSL2 não expõe câmera ao Linux. Contorno: vídeo gravado (`CAMERA=/data/test_2_05.avi`).
- **faixa Myo (sEMG real)** — `usbipd` não instalado e nenhum dongle presente. Contorno: `EMG=replay`.

Os dois contornos exercitam o *fluxo* inteiro. O que falta é só a captação física.

---

## 2. Para onde vai: três camadas

**Camada 1 — interface web contra a simulação.** É o que se constrói primeiro.

**Camada 2 — a mesma interface no celular.** Sem reescrever nada: é a mesma página.

**Camada 3 — braço físico.** A mesma interface, trocando o endereço do ROS.

A ordem importa e não é arbitrária: **a interface vem antes do hardware.** A mesma
página pilota o Gazebo e o braço real, porque os dois falam ROS 2. Se o braço chegar
antes da interface existir, ele fica na caixa esperando software. Se a interface
existir antes, no dia que o braço chegar ele se mexe.

---

## 3. Arquitetura decidida, e o porquê de cada escolha

### 3.1 Interface web por websocket, não PyQt

A dissertação tinha três telas PyQt. Elas já foram substituídas por um menu de
terminal (`scripts/menu.sh`) e, para quem não quer digitar comandos, por um
painel no navegador (`scripts/painel.py`, decisão D22) que liga e desliga cada
parte do sistema com botões. O painel é o lançador, não uma das guias: ele roda
no host e chama o `docker compose`, enquanto as guias falam com o ROS.

O destino é **página web falando com o ROS 2 por `rosbridge`** (websocket + JSON).
Três consequências, todas boas:

1. roda em qualquer navegador — o mesmo código no notebook e no celular;
2. as três guias viram três páginas, sem PyQt e sem depender de WSLg;
3. **o Gazebo deixa de precisar de janela.**

### 3.2 Gazebo headless

Esta é a consequência mais importante da escolha acima, e resolve um problema medido.

Neste projeto a renderização do Gazebo é por software (`LIBGL_ALWAYS_SOFTWARE=1`).
A aceleração por GPU **foi testada e não funciona** — ver
[Decisões que não devem ser revertidas](#decisões-que-não-devem-ser-revertidas).

Com a interface web, quem desenha o braço é o navegador, a partir dos quatro
ângulos de `/joint_states`. O componente pesado simplesmente não é desenhado.
O problema de renderização deixa de existir em vez de ser contornado.

Feito: o serviço `braco` sobe o Gazebo sem janela por padrão (`GUI=false`), e a
página desenha o braço.

### 3.3 Desenho do braço em 2D, não 3D

O braço é **planar**: ombro e cotovelo giram no mesmo plano. Uma vista lateral em
SVG é exata, não perde informação, desenha em qualquer celular e dispensa
biblioteca 3D.

Se um dia houver objetos a manipular e a terceira dimensão passar a importar,
troca-se só esse componente. Não comece por 3D.

### 3.4 Divisão de trabalho entre as máquinas

| Onde | O quê | Por quê |
|---|---|---|
| **Notebook (Legion)** | desenvolvimento e **treino** dos modelos | tem CPU e GPU; treino é pesado e ocasional |
| **Raspberry Pi** (futuro) | nós ROS 2, **classificação**, serial com os servos, servidor websocket | precisa estar sempre ligado, ao lado do braço |
| **Celular** | apenas interface | manda intenção, recebe estado |

A assimetria que justifica isso: **treinar é pesado e ocasional; classificar é leve
e constante.** Um k-NN ou SVM sobre 8 canais de MAV roda em microssegundos.

**Regra de segurança:** o celular é interface, **nunca** o laço de controle. Servo de
30 kg·cm belisca, Wi-Fi varia e celular dorme a tela. O laço de controle e os limites
moram no lado sempre ligado. Se a conexão cair, o braço **para** — não repete o
último comando.

Como isso está hoje: a **parada de emergência mora no `arm_controller`**, não na
página. A página só chama o serviço `/arm/estop` e mostra o estado que o
controlador publica. O controlador também não repete comando: ele segue um alvo
de posição e, quando a página cai, termina o último movimento e para. **Falta o
watchdog:** hoje ninguém percebe que a conexão caiu. Para o braço físico, o
controlador deve parar sozinho se a página ficar muda por mais que um tempo
curto.

**Ganho adicional do Pi:** sendo Linux nativo, ele elimina de uma vez todo o atrito
de WSL2 — câmera em `/dev/video0`, USB sem `usbipd`, ROS 2 nativo. Cada contorno
deste repositório para Windows deixa de ser necessário lá.

---

## 4. As três guias

### Guia 1 — Braço (feita)

A mais fácil e a que prova a arquitetura inteira: navegador → websocket → ROS 2 → Gazebo.

- setinhas e deslizadores para ombro, cotovelo e garra, publicando em `/arm/*/cmd_pos`
- assinatura de `/joint_states` mostrando **comando e realidade lado a lado**
- vista lateral 2D do braço
- parada de emergência

Mostrar comando contra realidade não é enfeite: é o mesmo sinal que o aprendizado
vai usar depois, e é o que revela se o controlador está acompanhando.

**Como ficou** (`web/index.html`, serviços `braco` e `web`):

- **Uma página, sem dependências nem build.** Ela fala o protocolo JSON do
  rosbridge diretamente (umas 65 linhas) em vez de carregar o `roslib.js`,
  para funcionar num Pi ou num celular sem internet.
- **"Comando" é o alvo que o controlador está seguindo** (`/arm/joint_targets`),
  não o que a página mandou. Assim a tela mostra a verdade mesmo quando quem
  comanda é o classificador ou o terminal, e mesmo durante a parada. O braço
  real aparece cheio; o comando, como contorno tracejado por cima.
- **A garra aparece também de frente.** Os dedos deslizam em x, o mesmo eixo de
  rotação do ombro e do cotovelo, e por isso ficam sobrepostos na vista
  lateral. A vista lateral continua exata para ombro e cotovelo.
- **Parada latched:** ao parar, o controlador zera as velocidades e ignora
  qualquer `cmd_pos` até liberar. Ao liberar, o alvo passa a ser a posição
  atual, e o braço não retoma um comando de antes da parada.

### Guia 2 — Treino

Disparar o treino, acompanhar e mostrar os resultados. Hoje as figuras saem como
PNG em `models/analise/<...>/`. A guia recupera a interatividade que a aba
"Results" do mestrado tinha e o menu não tem: escolher classificador e ver a
matriz correspondente.

### Guia 3 — Captura

A mais difícil no PC, porque depende de câmera e sEMG — justamente o que o WSL2
não entrega.

**No celular ela fica mais fácil que no PC**, e esse é um argumento forte para o
celular: a câmera é nativa e o navegador tem acesso. Medir o ângulo do cotovelo
pela câmera do próprio celular elimina o problema em vez de contorná-lo.

### Manipular objetos

Colocar objetos no mundo é fácil. **Fazer a garra agarrar é a parte cara** —
atrito, contato e controle das juntas da garra. A saída prática que a área usa é
um plugin que fixa o objeto na garra quando há contato e força suficiente, em vez
de simular atrito de verdade. É aceitável desde que documentado como tal.

---

## 5. O laço de aprendizado

A intenção declarada: *"o classificador era a base, mas observando o braço e vendo
o robô capturando os objetos ele ia aprendendo."*

### O problema que precisa ser enfrentado antes de codar

**Atribuição de crédito.** Se o robô não pega o objeto, não se sabe o que errou: o
classificador leu mal a intenção, a trajetória estava errada, ou o objeto escorregou.
O sucesso da tarefa **não diz o que a pessoa queria**. Sem separar isso, o
aprendizado persegue ruído.

### A escada — os dois primeiros degraus valem quase tudo

**Degrau 1 — regressão do ângulo contínuo. Possível hoje.**
O módulo de captura já grava `angle_deg`, o ângulo medido pela câmera, lado a lado
com o sEMG. Isso é rótulo contínuo e verdadeiro. Treinar **regressão do ângulo** em
vez de classificar duas categorias. Supervisionado, sem reforço, pipeline já existe
(foi para isso que `CONTINUOUS=true` foi feito).

Isto também resolve o achado da análise: com ângulo contínuo sai-se do regime em
que um único número de amplitude separa dois blocos.

**Degrau 2 — adaptação contínua.**
Enquanto a pessoa usa, a câmera segue fornecendo pares (sEMG, ângulo) e o modelo se
atualiza. Isto é co-adaptação, ideia estabelecida em controle mioelétrico: a pessoa
aprende a gerar o sinal e o decodificador aprende a lê-lo, ao mesmo tempo.

**Degrau 3 — recompensa por pegar o objeto.**
Aprendizado por reforço. É onde a atribuição de crédito morde. **Não começar por aqui.**

O degrau 1 é a ponte entre o que a análise mostrou e o que se quer construir.
Não é desvio, é o caminho.

---

## 6. Hardware: critério de compra

**O critério é realimentação de posição de junta, não preço.**

Sem feedback de junta o laço de aprendizado fica *estruturalmente impossível*: só se
sabe o que foi **comandado**, nunca o que **aconteceu**. O erro entre comando e
realidade — que é o sinal de aprendizado — não existe.

| Candidato | DOF | Feedback | ROS 2 | Observação |
|---|---|---|---|---|
| **MeArm** e genéricos MG996 | 4–6 | **não** (só corrente) | via Arduino | **descartado** pelo critério acima |
| **Waveshare RoArm-M2-S** | 4 | sim (ângulo, carga, corrente, temperatura) | repo oficial | ESP32 com WiFi e app web de fábrica; casa com a simulação |
| **SO-101 (LeRobot)** | 6 | sim (barramento serial) | bringup + MoveIt 2 | ~US$ 199; ecossistema LeRobot traz aprendizado por imitação pronto |

**Decisão de ordem:** não comprar antes da interface existir.

**Em aberto:** se o braço é para o Caio usar com a faixa de sEMG fechando o ciclo do
mestrado, o SO-101 muda bastante o que dá para fazer no aprendizado. Se é para ter
algo tangível se mexendo, o RoArm-M2-S entrega mais rápido.

---

## 7. Decisões que não devem ser revertidas

Cada item custou tempo real. Não desfaça sem um teste novo que justifique.

1. **Não atualizar driver de vídeo nesta máquina** — nem Intel, nem NVIDIA. Dois
   updates causaram instabilidade. As versões validadas pela Lenovo são as que
   funcionam.

2. **Não tentar aceleração por GPU no Gazebo sob WSL2.** Foi testado com tudo
   presente — `/dev/dxg` mapeado, `/usr/lib/wsl` montado, `d3d12_dri.so` na imagem,
   `MESA_LOADER_DRIVER_OVERRIDE=d3d12`. A janela abre e **não desenha frame nenhum**.
   Manter `LIBGL_ALWAYS_SOFTWARE=1`. Está documentado no cabeçalho de
   `docker/compose.wsl.yaml`.

3. **Não montar `/mnt/wslg` no container.** O mecanismo de bind-mount do Docker
   Desktop não dá conta, em nenhum caminho. Montar só `/tmp/.X11-unix`.

4. **Não mover o clone para o disco do Windows.** Medido: ~60× mais lento em
   operações de arquivo, e `C:\Dev` é tão lento quanto o OneDrive — o custo é
   atravessar a fronteira WSL↔Windows, não a sincronização. O clone fica no ext4.

5. **Nunca dois simuladores ao mesmo tempo.** Eles publicam nos mesmos tópicos e as
   leituras se misturam **sem dar erro**. Conferir `docker ps` antes de subir, ou
   rodar `scripts/check_docker.sh` (saída 4 avisa).

6. **Docker Desktop sem AutoStart, de propósito.** A máquina também grava culto ao
   vivo; Docker subindo sozinho tiraria memória na hora errada. Abrir à mão antes de
   trabalhar. `scripts/check_docker.sh` diagnostica.

7. **Os 88–100% não são alegação do mestrado.** A dissertação é contribuição de
   *ferramenta*: seus quatro objetivos específicos são de construção, nenhum de
   acurácia. Aqueles números são de demonstração, sobre um conjunto de duas classes
   com **uma única transição** no arquivo inteiro, separável por um único limiar de
   amplitude sem sobreposição. Ver `docs/ANALISE_RESULTADOS.md`.

8. **Não instalar pacote ROS compilado pelo apt na imagem.** O packages.ros.org só
   guarda a última sincronização, e a imagem base ficou uma sincronização atrás
   (254 de 351 pacotes). O `rosbridge` do apt instalou, mas não carregou:
   `undefined symbol: has_buffer_fields_builtin_interfaces__msg__Time`. Ele é
   compilado do código-fonte no Dockerfile, contra o ROS da própria imagem
   (decisão D19).

9. **No Docker Desktop, a rede `host` não é alcançável do Windows nem do Ubuntu.**
   Medido com um `http.server` em modo host: sem resposta dos dois lados. Portas
   publicadas funcionam, mas só a partir de rede bridge, e o mesmo número não
   pode ser usado dos dois lados ("address already in use"). Por isso existem o
   repasse `web-portas` e o `compose.desktop.yaml` (decisão D20). Não tente
   publicar portas no serviço `web` nem tirá-lo do modo host: o DDS precisa dele.

---

## 8. Em aberto

- Qual braço comprar — depende do uso pretendido (seção 6).
- Como o celular alcança a página enquanto o servidor estiver no WSL2. O repasse
  do `compose.desktop.yaml` já publica as portas no Windows, só que em
  `127.0.0.1`. Trocar por `0.0.0.0` e liberar o firewall talvez baste, sem
  `netsh portproxy` (não testado). Antes, a página precisa de alguma
  autenticação, porque o rosbridge dá controle de todo o grafo ROS. No Pi, o
  problema de rede não existe.
- O watchdog de conexão no `arm_controller` (seção 3.4), antes do braço físico.
- Como medir o ângulo do cotovelo no navegador do celular.
- Se vale colocar objetos no mundo antes ou depois da guia de treino.

---

## 9. Ordem de construção proposta

1. ~~`rosbridge` no compose + guia do braço com vista 2D~~ — **feito** (26/09/2026), arquitetura provada
2. acesso pelo celular na rede local
3. guia de treino, recuperando a interatividade dos resultados
4. degrau 1 do aprendizado: regressão do ângulo contínuo
5. objetos no mundo e garra que agarra
6. guia de captura, provavelmente já mirando a câmera do celular
7. braço físico

Cada etapa deve funcionar sozinha antes da seguinte começar.
