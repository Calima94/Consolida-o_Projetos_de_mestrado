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

**D2. Plugin C++ substituído pelos sistemas oficiais do Gazebo.** O
`libarm_control.so` usava a API do Gazebo Classic, que não existe no Jetty.
`JointStatePublisher` e `JointPositionController` com
`use_velocity_commands` reproduzem o controle do mestrado (`SetVelocity` com
ganho P). Ganhos do mestrado: kp 1 no ombro e no cotovelo, 10 na garra. O
limite de esforço passou de `-1` para `1e6` porque o Gazebo só respeita os
limites de posição sob controle por velocidade quando há limite de esforço
(aviso emitido pelo próprio Gazebo). *Rever se* o gêmeo digital passar a
precisar de controle por torque.

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

Medido: Ctrl+C 0,4 s (sem janela) e 3,4 s (com janela, em display virtual),
`docker compose stop` 0,5 s, `stop.sh` 0,5 s, sem processos sobrando.

**D10. Dados fora do git.** `scripts/fetch_legacy_data.sh` baixa os CSVs de um
commit fixo do `Train_Myo_Signals` e confere o SHA-256. Mesma regra do
`semg-digital-twins`: dataset não se versiona, se referencia.

**D11. Licença Apache-2.0 (pendente do Caio).** Mesma do `Capture_EMG_Data` e
do `Train_Myo_Signals`, de onde vem parte do código (inclusive a cópia literal
em `tests/legacy_reference`). O `semg-digital-twins` usa MIT (ADR-004).
*Rever* se o Caio preferir alinhar com o `semg-digital-twins`.

**D12. Capture_EMG_Data fica para a próxima etapa.** A ferramenta de coleta
(PyQt5 + OpenCV + MediaPipe + webcam) não entra no fluxo de simulação e
depende de hardware que hoje não existe. O protocolo do Myo já foi portado.
