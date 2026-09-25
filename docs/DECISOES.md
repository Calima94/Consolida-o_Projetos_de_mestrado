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
pacote ROS fora da imagem (usar `rosdep`).

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
  `docker compose stop`; dentro do container, SIGINT e depois SIGTERM/SIGKILL
  no que sobrar.

Medido (2026-09-25, depois de D2 e D16): Ctrl+C 0,4 s, com ou sem as janelas do
Gazebo e da câmera (em display virtual); `docker compose stop` 0,5 s;
`stop.sh` 0,5 s; nenhum processo sobrando.

**D10. Dados fora do git.** `scripts/fetch_legacy_data.sh` baixa os CSVs de um
commit fixo do `Train_Myo_Signals` e confere o SHA-256. Mesma regra do
`semg-digital-twins`: dataset não se versiona, se referencia.

**D11. Licença Apache-2.0 (pendente do Caio).** Mesma do `Capture_EMG_Data` e
do `Train_Myo_Signals`, de onde vem parte do código (inclusive a cópia literal
em `tests/legacy_reference`). O `semg-digital-twins` usa MIT (ADR-004).
*Rever* se o Caio preferir alinhar com o `semg-digital-twins`.

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
