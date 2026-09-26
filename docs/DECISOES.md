# Decisões do porte

Uma entrada por decisão: o que foi decidido, por quê e o que faria rever.
Datas em 2026-09. Decisões marcadas **(pendente do Caio)** foram tomadas
provisoriamente para o trabalho andar e precisam da confirmação dele.

**D1. Imagem base `osrf/ros:lyrical-desktop-full`.** ROS 2 Lyrical Luth
(LTS, Ubuntu 26.04), o alvo do ADR-002 do `semg-digital-twins`. A imagem já
traz o Gazebo Jetty (`gz sim` 10) e o `ros_gz`. As bibliotecas científicas vêm
do apt do Ubuntu (numpy 2.3, scipy 1.16, scikit-learn 1.7, PyWavelets 1.4).
O argumento `SKIP_ROS_APT_SOURCE=1` existe porque o ambiente de nuvem onde o
porte foi feito bloqueia `packages.ros.org`. *Rever se* for preciso algum
pacote ROS fora da imagem (usar `rosdep`). Isso aconteceu com o `rosbridge`,
e o apt não serviu: ver D19.

**D2. Plugin C++ substituído pelos sistemas oficiais do Gazebo + nó de
controle.** O `libarm_control.so` usava a API do Gazebo Classic, que não
existe no Jetty. Ele virou `JointStatePublisher` e `JointController` em modo
velocidade (o equivalente ao `joint->SetVelocity()` do plugin). A malha de
posição do `arm_controller.py`, `v = kp·(alvo − posição)`, virou o nó
`mestrado_emg/arm_controller`, com os kp do mestrado (1 no ombro e no
cotovelo, 10 na garra). Medido: com kp = 1 o cotovelo percorre 63 % do degrau
em 1 s, a resposta de 1ª ordem esperada. O limite de esforço passou de `-1`
para `1e6` porque o Gazebo só respeita os limites de posição sob controle por
velocidade quando há limite de esforço (aviso do próprio Gazebo). *Rever se* o
gêmeo digital passar a precisar de controle por torque.

> **Correção (2026-09-25).** A primeira versão usava o
> `JointPositionController` com `use_velocity_commands` e afirmava aplicar os
> kp do mestrado. **Estava errado:** nesse modo o Gazebo ignora o ganho e leva
> a junta ao alvo em um passo (medido: 0° → 162° em menos de 50 ms). O erro
> apareceu ao testar o modo espelho e foi corrigido com o nó de controle acima.

**D3. Retreinar em vez de reaproveitar os `.joblib`.** Achado 1 do
[inventário](INVENTARIO_MESTRADO.md). Cada modelo é salvo como *bundle* com a
configuração de features, o mapa classe→ângulo, a semente, o split e o SHA-256
do CSV. O classificador ao vivo lê a configuração do próprio bundle (achado 2).

**D4. Padrão MAV e split temporal.** MAV é o que o nó ao vivo calculava; RMS
continua disponível (`--feature rms`) e é o que reproduz o histórico. O split
`temporal` (blocos em ordem de gravação + 1 janela de purga = 250 ms) é o
padrão, porque o `legacy` mistura janelas vizinhas entre treino e teste.

**D5. Tópicos independentes de sensor, sem mensagens customizadas.**
`/emg/raw` (`Float32MultiArray`, lotes `[amostras × canais]`) e `/emg/imu`
(`sensor_msgs/Imu`). Trocar o Myo por outro sensor é escrever um nó driver.
O custo é que não há carimbo de tempo por amostra, só por lote.
*Rever se* um sensor novo exigir sincronização fina (criar `EmgSample.msg`).

**D6. Nó de reprodução (`emg_replay`) como substituto do hardware.** Toca o
CSV no ritmo real (200 Hz, lotes de 10). Permite rodar e testar o fluxo inteiro
sem o Myo. Reproduzir o arquivo de treino só demonstra a ligação entre as
partes; não é avaliação.

**D7. Janelas consecutivas sem descartar amostras.** O mestrado descartava as
amostras que chegavam enquanto classificava. Aqui o buffer é contínuo. É uma
diferença de comportamento pequena e deliberada.

**D8. Modelo e mundo.** Juntas e links renomeados (`shoulder_joint`,
`elbow_joint`, …; os nomes antigos estão em comentários no SDF). Materiais
OGRE trocados por cores, porque o Jetty não os suporta. `self_collide`
desligado (links vizinhos se tocam por construção). Pedestal de 30 cm para o
ombro não roçar no chão. Massas, inércias, geometria, eixos e limites são os
do mestrado.

**D9. Encerramento limpo (o problema do botão "Stop").** Medido nesta
porta, com as mesmas causas do mestrado:

- o `ros_gz_sim` sobe o Gazebo via `/bin/sh -c` (dash), que não repassa SIGINT,
  e o `gz sim` com janela não repassa o sinal para os processos do servidor e da
  interface. Resultado: processos órfãos (o `killall` do mestrado).
  **Solução:** o Gazebo sobe pelo `gz_sim_group`, que o roda num grupo de
  processos próprio e manda qualquer sinal de parada para o grupo inteiro;
- no Docker, o `ros2 launch` como PID 1 ignorava o SIGTERM do
  `docker compose stop` e morria por SIGKILL após o timeout (30 s).
  **Solução:** `init: true`, `stop_signal: SIGINT` e
  `TINI_KILL_PROCESS_GROUP=1` no `compose.yaml`;
- os nós usam `spin_node()`, que ignora um segundo SIGINT durante a limpeza,
  para o driver do Myo sempre conseguir desconectar;
- `scripts/stop.sh` é o equivalente do botão: no host roda
  `docker stop` em todos os containers do projeto, incluindo os de
  `docker compose run`, que o `docker compose stop` ignora; dentro do
  container, SIGINT e depois SIGTERM/SIGKILL
  no que sobrar.

Medido (2026-09-25, depois de D2 e D16): Ctrl+C 0,4 s, com ou sem as janelas do
Gazebo e da câmera (em display virtual); `docker compose stop` 0,5 s;
`stop.sh` 0,5 s; nenhum processo sobrando.

**D10. Dados fora do git.** `scripts/fetch_legacy_data.sh` baixa os CSVs de um
commit fixo do `Train_Myo_Signals` e confere o SHA-256. Mesma regra do
`semg-digital-twins`: dataset não se versiona, se referencia.

**D11. Licença MIT (decisão do Caio, 2026-09-25).** Alinha com o
`semg-digital-twins` (ADR-004). A primeira versão usava Apache-2.0, herdada do
`Capture_EMG_Data` e do `Train_Myo_Signals`; como o autor é o mesmo, ele pode
relicenciar o próprio código. O código de terceiros fica com os seus termos em
`THIRD_PARTY_NOTICES.md`:

- myo-raw (Danny Zhu) e o fork do Alvipe são MIT, compatíveis. O aviso de
  copyright passou a acompanhar o código, como a MIT exige; antes faltava;
- a PyoConnect (Cosentino) não tem licença verificável;
- a base da ferramenta de captura é de Alan Mendes, cujo repositório não tem
  arquivo de licença. **Pendente:** a concordância dele para que essa parte
  passe a MIT; até lá, ela segue os termos do `Capture_EMG_Data` (Apache-2.0).

**D12. Capture_EMG_Data portado sem a interface PyQt.** Os campos da tela
(número de categorias, tolerância, amostras) viraram argumentos do launch e
variáveis do compose. A janela do OpenCV com o traçado do braço continua,
laranja/vermelho enquanto grava. A câmera (`elbow_angle_camera`) e a gravação
(`emg_recorder`) são nós separados, então a gravação funciona com qualquer
fonte de sEMG. O CSV mantém o formato do mestrado mais a coluna `angle_deg`.
Corrigido o bug de conclusão de categoria (achado 17). ESC e também Ctrl+C
salvam o que já foi gravado (no mestrado, só o ESC salvava).

**D13. MediaPipe 1.x com a API Tasks.** A API `mp.solutions.pose` usada no
mestrado não existe mais no MediaPipe 1.0 (achado 18). O `PoseLandmarker`
tem os mesmos 33 marcos, então os índices 11-13-15 e a fórmula do ângulo não
mudam. A partir da 1.0 o wheel é `py3-none`, o que permite rodar no
Python 3.14 da imagem. É instalado com `--no-deps`, com as dependências vindas
do apt. O modelo `pose_landmarker_full` (equivalente ao `model_complexity=1`
do mestrado) é fixado por versão e SHA-256. *Rever se* o Google mudar a API
Tasks.

**D14. Filtro de visibilidade e `flip` configurável.** Leituras com
visibilidade < 0,5 no ombro, cotovelo ou punho são descartadas: no vídeo do
mestrado, eram elas que discordavam do ângulo original. `flip` é `true` para
webcam (como no mestrado) e `false` para vídeos salvos pela ferramenta antiga,
que já gravava a imagem espelhada.

**D15. Modo espelho (novo).** Com `mirror_to_sim`, o ângulo medido pela
câmera vai direto para o cotovelo simulado (180° − ângulo). Serve para ver o
gêmeo digital funcionando sem sEMG e, mais adiante, como referência de ângulo
contínuo.

**D16. Encerramento determinístico dos nós.** SIGINT/SIGTERM só pedem a
parada; o nó sai entre dois callbacks. Um `KeyboardInterrupt` no meio de um
callback chegou a interromper a liberação de memória do MediaPipe, e poderia
cortar a desconexão do Myo ou a escrita do CSV.

**D17. As telas PyQt viraram um menu de terminal e figuras em arquivo.** As
três janelas do mestrado (captura, treino/resultados e lançador do Gazebo)
estão no `scripts/menu.sh`, que pergunta os campos, mostra o comando do
`docker compose` e o executa. A aba "Results" virou o `analyze_legacy`, que
grava PNGs (acurácia, matrizes de confusão, ROC, sinal bruto, features) e um
resumo, em vez de desenhar numa janela: funciona no Docker sem depender de
janela e o resultado fica guardado. Usa o `matplotlib` que já vinha na imagem.
Acrescenta o que a tela não tinha: validação cruzada temporal e embaralhada,
ROC com escore contínuo, conferência da taxa de amostragem e a referência
`amplitude`. *Rever se* for preciso editar parâmetros do pipeline com
frequência, caso em que uma interface gráfica voltaria a compensar.

**D18. Interface web: uma página que fala o protocolo do rosbridge.** A guia 1
de `VISAO_E_ARQUITETURA.md` (o braço) é `web/index.html`: um arquivo só, sem
dependências nem etapa de build, servido pelo serviço `web` junto com o
`rosbridge`. A página fala o protocolo JSON do rosbridge diretamente, numa
classe de umas 65 linhas, em vez de carregar o `roslib.js`: assim funciona sem
internet, num Pi ou num celular, e não há versão de biblioteca para
acompanhar. A vista lateral usa as medidas do SDF. A garra aparece também de
frente, porque os dedos deslizam no eixo de rotação do ombro e do cotovelo e se
sobrepõem na vista lateral. As faixas dos deslizadores (ombro ±90°, cotovelo
±150°, abertura de 6 a 22 cm) são conveniência de interface, não limites de
segurança; o SDF aceita ±180°. O serviço `braco` sobe só o braço, sem janela,
para ser pilotado pela página. *Rever se* a página crescer a ponto de precisar
de componentes (as guias de treino e captura), caso em que um framework pode
compensar.

**D19. `rosbridge` compilado do código-fonte na imagem.** O `rosbridge` não
vem no `desktop-full`. Instalado pelo apt, ele não carregou
(`undefined symbol: has_buffer_fields_builtin_interfaces__msg__Time`, medido
em 2026-09-26). O motivo: o `packages.ros.org` só guarda a última
sincronização, e a imagem base local estava uma sincronização atrás (254 de 351
pacotes ROS com versão mais nova). Atualizar a pilha inteira mudaria o Gazebo
validado. Por isso o Dockerfile clona a tag 4.2.1, confere o commit e compila
os pacotes necessários contra o ROS da própria imagem (menos de 1 min). Assim
as mensagens sempre casam com a base, qualquer que seja a sincronização. As
dependências Python vêm do arquivo do Ubuntu, e a imagem continua sem baixar
nada de `packages.ros.org`. O workspace é compilado por cima (`/ws/install`
encadeia `/opt/rosbridge/install`), então o entrypoint não mudou. *Rever se* a
imagem base passar a ser fixada por digest numa sincronização conhecida, caso
em que o pacote do apt dessa mesma sincronização serviria.

**D20. Docker Desktop: repasse de portas para a interface web.** Todos os
serviços ROS usam `network_mode: host`, para o DDS se descobrir entre
containers. No Docker Desktop, "host" é a máquina virtual do Docker. Uma porta
aberta ali não responde nem ao Windows nem ao Ubuntu do WSL (medido com um
`http.server` em modo host). Portas publicadas chegam aos dois, mas só a partir
de rede bridge. O `compose.desktop.yaml` sobe então o `web-portas`, que publica
8080 e 9090 e repassa cada conexão para a máquina virtual
(`docker/port_forward.py`, uma cópia de bytes, que deixa o websocket intacto).
O `web` passa a escutar em 18080 e 19090, porque a porta publicada também é
ocupada dentro da máquina virtual, e o mesmo número dos dois lados dá "address
already in use" (medido). A página e o celular continuam usando 8080 e 9090,
como no Linux. As portas são publicadas só em `127.0.0.1`, porque o
`rosbridge` não tem autenticação. O `web-portas` fica declarado, desligado,
no `compose.yaml` (perfil `desktop`, reativado com `!reset`). Sem isso, os
outros comandos o acusavam de container órfão e sugeriam `--remove-orphans`.
*Rever se* a opção "Enable host networking" do Docker Desktop for testada e
funcionar: ela dispensaria o repasse.

**D21. Parada de emergência e alvo publicado no `arm_controller`.** A regra
de `VISAO_E_ARQUITETURA.md` (seção 3.4) é que o laço de controle e a segurança
morem no lado sempre ligado, nunca na página. Por isso a parada é um serviço do
controlador, `/arm/estop` (`std_srvs/SetBool`). Com `true`, ele manda
velocidade zero a todas as juntas e ignora `cmd_pos` de qualquer origem até
receber `false`. Ao parar e ao liberar, o alvo vira a posição atual, e o braço
não retoma um comando anterior à parada. O estado sai em `/arm/estop_active`
(*transient local*, a cada mudança e uma vez por segundo), o que também diz à
página que o controlador está vivo. O controlador passou a publicar ainda o
alvo que está seguindo, em `/arm/joint_targets`, que é o "comando" que a
página mostra ao lado do real. Esse é o par comando × realidade de que o
aprendizado vai precisar. A lei de controle do mestrado não mudou. Medido no
Gazebo: parado a caminho de 90°, o cotovelo ficou em 70,36° sem deriva em 5 s;
um `cmd_pos` enviado do terminal durante a parada foi ignorado. *Rever se*
houver braço físico: aí falta o watchdog de conexão, para o controlador parar
sozinho quando a página ficar muda.

**D22. Painel no navegador, rodando no host, para os comandos do projeto.**
`scripts/painel.py` serve `scripts/painel.html` em `http://localhost:8000`: um
cartão por ação do menu, com as opções recolhidas e os mesmos padrões, mais
testes e "parar tudo". Roda no host (o Ubuntu do WSL, ou o Linux) e não no
Docker, porque é ele que sobe e para os containers; usa só a biblioteca padrão
do Python, então não há nada a instalar. Não substitui as guias de
`VISAO_E_ARQUITETURA.md`, que falam com o ROS pelo `rosbridge`: o painel liga e
desliga o sistema, as guias o operam. Escolhas:

- **Lista fechada de ações:** cada botão monta um comando conhecido e cada
  parâmetro é conferido contra os arquivos que existem e os valores do menu.
  Não há como pedir um comando qualquer. Os testes comparam os comandos de
  treino e análise com os que o menu imprime.
- **Simulações destacadas (`up -d`):** fechar o painel não derruba o braço; os
  registros são acompanhados com `logs -f`. Tarefas com fim (captura, treino,
  testes) pertencem ao painel e param com ele (SIGINT, como Ctrl+C: a captura
  salva o que gravou). Medido: com o braço rodando, Ctrl+C no painel parou o
  acompanhamento e deixou o braço de pé; fechar a janela do `.bat` encerrou o
  painel sem deixar processo.
- **Uma simulação ou captura por vez**, conferido no servidor pelos containers
  que estão rodando, e não só na página.
- **Só `127.0.0.1`.** Todo POST exige o cabeçalho `X-Painel`, que uma página de
  outra origem não consegue mandar sem um preflight de CORS, que o servidor
  nunca aprova. O cabeçalho `Host` tem de ser `localhost`, o que barra DNS
  rebinding.

*Rever se* o painel precisar ficar acessível pela rede (por exemplo, no Pi): aí
ele precisa de autenticação, como o `rosbridge`.
