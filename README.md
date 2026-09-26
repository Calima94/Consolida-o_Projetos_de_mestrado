# Consolidação dos projetos de mestrado

Os repositórios do mestrado (*Simulador open-source de prótese de membro
superior controlado por sEMG*, UFABC, 2023) reunidos num só e portados para
**ROS 2 Lyrical Luth + Gazebo Jetty**, rodando em **Docker**.

É o ponto de partida técnico do projeto pessoal
[`semg-digital-twins`](https://github.com/Calima94/semg-digital-twins):
primeiro reproduzir fielmente o que o mestrado fazia, com o ambiente atual, e só
então evoluir.

```
                 captura (webcam + MediaPipe) ──► /capture/elbow_angle_deg ──► emg_recorder ──► CSV rotulado
                                                        │ (modo espelho)
sEMG (Myo, ou CSV gravado) ──► /emg/raw ──► emg_classifier ──► /arm/*/cmd_pos ──► arm_controller ──► Gazebo Jetty
                               /emg/imu ─┘  (features do mestrado + kNN)            (P, kp do mestrado)   (braço do mestrado)
```

**Para rodar na sua máquina, siga [`docs/COMO_RODAR.md`](docs/COMO_RODAR.md)**
(Windows 11 com WSL2, ou Linux).

## Estado

| | Situação |
|---|---|
| Pipeline de features (filtros, wavelet, MAV/RMS) | ✅ Idêntico ao código original (diferença < 1e-9, testado contra cópia literal) |
| Treino dos 5 classificadores | ✅ Reproduz exatamente os scores históricos (0,9444 nos cinco) |
| Braço no Gazebo Jetty | ✅ Massas, geometria e juntas do mestrado; controle P com os kp originais (resposta de 1ª ordem medida: 63 % em 1 s com kp = 1) |
| Fluxo completo sem hardware (CSV → classificador → braço) | ✅ Teste de ponta a ponta no CI |
| Ferramenta de captura (`Capture_EMG_Data`) | ✅ Portada; ensaio completo sem hardware (vídeo do mestrado + sEMG reproduzido) no CI |
| Ângulo do cotovelo com MediaPipe 1.x | ✅ No vídeo do mestrado, diferença ≤ 3° em relação ao que a ferramenta original mediu |
| Modo espelho (o braço do Gazebo copia o seu, via câmera) | ✅ Novo; testado com o vídeo do mestrado |
| Encerrar com Ctrl+C / `docker compose stop` / `scripts/stop.sh` | ✅ Sem processos sobrando (medido) |
| Driver do Myo | ⚠️ Portado e com testes do protocolo, **mas nunca rodou com um Myo de verdade** |
| Janelas (Gazebo e câmera) | ✅ Windows 11 + WSL2 + Docker Desktop: janela do Gazebo abre e o braço se move (renderização por software). ⚠️ Linux com monitor e a janela da câmera só testados em display virtual (Xvfb); webcam não testada |

O que mudou em relação ao mestrado, e por quê, está em
[`docs/DECISOES.md`](docs/DECISOES.md). Os problemas encontrados no código
original estão em [`docs/INVENTARIO_MESTRADO.md`](docs/INVENTARIO_MESTRADO.md).

## Requisitos

- Docker com Compose v2.
- Para ver as janelas: Linux com X11, ou Windows 11 com WSL2 (WSLg).
- **Nenhum hardware.** Sem Myo, o sistema reproduz as gravações do mestrado;
  sem webcam, usa um vídeo.

## Início rápido

A partir da raiz do repositório. O passo a passo completo, com instalação e
solução de problemas, está em [`docs/COMO_RODAR.md`](docs/COMO_RODAR.md).

```bash
./scripts/fetch_legacy_data.sh                            # dados do mestrado -> ./data
docker compose -f docker/compose.yaml build               # imagem ROS 2 + Gazebo
docker compose -f docker/compose.yaml run --rm train      # 5 classificadores -> ./models

# sistema do mestrado: sEMG gravado -> kNN -> braço (sem janela)
docker compose -f docker/compose.yaml up sim

# com janela: acrescente -f docker/compose.gui.yaml (Linux) ou -f docker/compose.wsl.yaml (Windows)
GUI=true docker compose -f docker/compose.yaml -f docker/compose.gui.yaml up sim

# modo espelho com o vídeo do mestrado
CAMERA=/data/test_2_05.avi FLIP=false docker compose -f docker/compose.yaml -f docker/compose.gui.yaml up espelho
```

### Encerrar

Ctrl+C, `./scripts/stop.sh` (o equivalente ao botão "Stop" do mestrado; para
também os containers de `docker compose run`) ou
`docker compose -f docker/compose.yaml stop` (só os de `up`). Tempo medido: 0,4 s, com ou sem
janelas, sem processos sobrando. No mestrado era preciso
`killall gzserver gzclient`; a causa e a correção estão na decisão D9.

## Serviços do compose

| Serviço | O que faz | Variáveis principais |
|---|---|---|
| `train` | Treina os 5 classificadores a partir do CSV | — |
| `sim` | Gazebo + fonte de sEMG + classificador + controlador | `SOURCE` (`replay`/`myo`), `CSV`, `MODEL`, `GUI` |
| `espelho` | Gazebo + câmera: o braço copia o cotovelo visto | `CAMERA`, `FLIP`, `ARM`, `GUI` |
| `captura` | Ferramenta de captura: câmera + sEMG rotulado por categoria | `EMG`, `CAMERA`, `N_CATEGORIES`, `TOLERANCE`, `SAMPLES`, `CONTINUOUS` |
| `shell` | Terminal com o workspace carregado | — |

Arquivos adicionais: `compose.gui.yaml` (janelas no Linux),
`compose.wsl.yaml` (janelas no Windows/WSLg), `compose.camera.yaml` (webcam),
`compose.myo.yaml` (dongle do Myo).

## Tópicos

Qualquer fonte de sEMG publica nos mesmos tópicos. Trocar de sensor é escrever
um nó driver; classificador e simulador não mudam.

| Tópico | Tipo | Conteúdo |
|---|---|---|
| `/emg/raw` | `std_msgs/Float32MultiArray` | Lote de amostras, `layout.dim = [("samples", n), ("channels", c)]` |
| `/emg/imu` | `sensor_msgs/Imu` | Orientação do sensor (opcional; move o ombro) |
| `/emg/label` | `std_msgs/Int32` | Categoria gravada (só no `emg_replay`) |
| `/emg/predicted_class` | `std_msgs/Int32` | Saída do classificador |
| `/arm/<junta>/cmd_pos` | `std_msgs/Float64` | Alvo em radianos (`shoulder`, `elbow`, `gripper_left`, `gripper_right`) |
| `/arm/<junta>/cmd_vel` | `std_msgs/Float64` | Velocidade que o `arm_controller` envia ao Gazebo |
| `/joint_states` | `sensor_msgs/JointState` | Estado das juntas vindo do Gazebo |
| `/capture/elbow_angle_deg` | `std_msgs/Float64` | Ângulo do cotovelo medido pela câmera (≈ 170° esticado) |
| `/capture/recording`, `/capture/status` | `Bool`, `String` | Estado da captura (cor do traçado e progresso na janela) |

### Trocar de sensor

1. Escreva um nó que publique `/emg/raw` (use `samples_to_msg` de
   `mestrado_emg/nodes/common.py`; `myo_driver.py` serve de modelo).
2. Os filtros do mestrado só valem a 200 Hz. Para outra taxa, use
   `LegacyFeatureConfig.for_sensor(fs_hz=..., n_channels=...)`, que recalcula o
   passa-altas e o rejeita-faixa de 60 Hz.
3. Grave dados com a ferramenta de captura e **retreine**: ganho, posição e
   taxa diferentes não deixam os modelos do Myo se transferirem.

## Testes e CI

```bash
pip install numpy scipy scikit-learn PyWavelets pandas joblib pyyaml pytest ruff
./scripts/fetch_legacy_data.sh
ruff check . && ruff format --check .
pytest
```

Os testes cobrem:

- equivalência com cópias literais do código original (features e regras de
  categoria da captura);
- reprodução da matriz de treino e dos scores históricos;
- o ângulo do MediaPipe contra o que a ferramenta original imprimiu no vídeo;
- a lei de controle e a resposta de 1ª ordem;
- o protocolo do Myo sem hardware;
- a consistência entre o SDF, a ponte ROS↔Gazebo, o controlador e o compose;
- o encerramento do grupo de processos do Gazebo.

O CI ([`.github/workflows/ci.yml`](.github/workflows/ci.yml)) roda isso,
constrói a imagem, repete os testes dentro dela (incluindo os que dependem de
ROS e MediaPipe) e executa dois testes de ponta a ponta:

- [`integration_test.sh`](scripts/integration_test.sh): sEMG → kNN → cotovelo
  0° ↔ 90°, com encerramento limpo;
- [`capture_test.sh`](scripts/capture_test.sh): captura completa com o vídeo
  do mestrado e o modo espelho.

## Resultados reproduzidos

Com features RMS e o split original, os cinco classificadores dão **0,9444**,
exatamente o `scores_of_classifiers.csv` do mestrado. Outras configurações
estão no [inventário](docs/INVENTARIO_MESTRADO.md#resultados-reproduzidos).
São 60 janelas de um único sujeito e 16 a 18 janelas de teste: os números
servem para conferir que o porte está fiel, **não como resultado científico**.

## Estrutura

```
docker/                     Dockerfile, compose (base, janela Linux/WSL, webcam, Myo)
ros2_ws/src/
  mestrado_emg/             features, treino, protocolo do Myo, controle e nós ROS 2
  mestrado_capture/         ângulo do cotovelo (MediaPipe) e gravação rotulada
  mestrado_description/     modelo SDF do braço + mundo (Gazebo Jetty)
  mestrado_bringup/         launch files (sim, mestrado, captura, espelho), ponte, gz_sim_group
scripts/                    dados, stop.sh, testes de ponta a ponta
tests/                      pytest (+ legacy_reference: cópias literais do código original)
docs/                       como rodar, inventário do mestrado e decisões do porte
data/, models/              fora do git (baixados / gerados)
```

### De onde veio cada parte

| Mestrado | Aqui |
|---|---|
| `Train_Myo_Signals/mod_sig_emg.py`, `train_signals_emg.py` | `mestrado_emg/features.py`, `training.py` |
| `my_arm_def/.../capture_simple_sample.py`, `mod_sig_emg.py` | `mestrado_emg/features.py` |
| `MyoRaw`/`BT` (nos três repositórios) | `mestrado_emg/myo_protocol.py` |
| `my_arm_def/.../capture_braco_pos.py` + `myo_raw.py` | `nodes/myo_driver.py` + `nodes/emg_classifier.py` |
| `my_arm_def/.../arm_controller.py` + plugin `arm_control.cpp` | `nodes/arm_controller.py` + `JointController` no `model.sdf` |
| `my_arm_def/.../show_angles.py` (painel PyQt) | `nodes/angle_monitor.py` |
| `braco_antebraco_garra.sdf`, `braco_com_mesa.world` | `mestrado_description/` |
| `my_arm_definitive.launch.py` + `main.py` (launcher PyQt) | `mestrado_bringup/launch/` + `docker/compose.yaml` |
| Botão "Stop" (`stop_myo_and_gazebo`) | `scripts/stop.sh` + `gz_sim_group` |
| `Capture_EMG_Data/pose_module.py` | `mestrado_capture/pose.py` (MediaPipe Tasks) + `categories.py` |
| `Capture_EMG_Data/capture_myo_*.py` (janela PyQt + gravação) | `nodes/elbow_angle_camera.py` + `nodes/emg_recorder.py` + `captura.launch.py` |

## Problemas conhecidos

- O `parameter_bridge` do `ros_gz` às vezes cai com segfault (`exit code -11`)
  quando recebe dois SIGINT seguidos. É um defeito do pacote do ROS: ele estava
  encerrando de qualquer forma e não deixa nada preso.
- A webcam normalmente não chega ao WSL2; no Windows use um vídeo gravado
  (ver `docs/COMO_RODAR.md`).
- O ângulo da câmera é uma projeção 2D: o braço precisa se mover num plano
  paralelo à câmera, como no mestrado.

## Uso de IA

O porte, os testes e esta documentação foram feitos com o Claude (Anthropic),
via Claude Code, a partir da leitura dos repositórios originais. A revisão e a
responsabilidade pelo conteúdo são do autor.

## Licença

MIT, a mesma do `semg-digital-twins` (ver [`LICENSE`](LICENSE) e a decisão
D11). O código de terceiros incluído mantém os seus termos, listados em
[`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md): o protocolo do Myo vem do
myo-raw (MIT), e a lógica da ferramenta de captura tem base de Alan Mendes, cuja
parte depende da concordância dele para passar a MIT.

## Autor

**Caio Lima** — UFABC
