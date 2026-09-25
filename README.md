# Consolidação dos projetos de mestrado

Os quatro repositórios do mestrado (*Simulador open-source de prótese de membro
superior controlado por sEMG*, UFABC, 2023) reunidos num só e portados para
**ROS 2 Lyrical Luth + Gazebo Jetty**, rodando em **Docker**.

É o ponto de partida técnico do projeto pessoal
[`semg-digital-twins`](https://github.com/Calima94/semg-digital-twins):
primeiro reproduzir fielmente o que o mestrado fazia, com o ambiente atual, e só
então evoluir.

```
sEMG (Myo ao vivo, ou CSV gravado) ──► /emg/raw ──► emg_classifier ──► /arm/*/cmd_pos ──► Gazebo Jetty
                                        /emg/imu ─┘   (features do mestrado + kNN)            (braço do mestrado)
```

## Estado

| | Situação |
|---|---|
| Pipeline de features (filtros, wavelet, MAV/RMS) | ✅ Idêntico ao código original (diferença < 1e-9, testado contra cópia literal) |
| Treino dos 5 classificadores | ✅ Reproduz exatamente os scores históricos (0,9444 nos cinco) |
| Braço no Gazebo Jetty | ✅ Massas, geometria e juntas do mestrado; controle P com os ganhos originais |
| Fluxo completo sem hardware (CSV → classificador → braço) | ✅ Coberto pelo teste de integração (`scripts/integration_test.sh`) |
| Encerrar com Ctrl+C / `docker compose stop` / `scripts/stop.sh` | ✅ Sem processos sobrando (medido) |
| Driver do Myo | ⚠️ Portado e com testes do protocolo, **mas nunca rodou com um Myo de verdade** |
| Janela do Gazebo | ⚠️ Testada só em display virtual (Xvfb); falta testar numa máquina com monitor |
| Ferramenta de coleta com webcam (`Capture_EMG_Data`) | ❌ Ainda não portada |

O que mudou em relação ao mestrado, e por quê, está em
[`docs/DECISOES.md`](docs/DECISOES.md). Os problemas encontrados no código
original estão em [`docs/INVENTARIO_MESTRADO.md`](docs/INVENTARIO_MESTRADO.md).

## Requisitos

- Docker com Compose v2.
- Para ver a janela do Gazebo: Linux com X11, ou Windows 11 com WSL2 (WSLg).
- **Nenhum hardware.** Sem Myo, o sistema reproduz as gravações do mestrado.

## Início rápido

Todos os comandos a partir da raiz do repositório.

```bash
# 1. Baixar os dados do mestrado (commit fixo, SHA-256 conferido) para ./data
./scripts/fetch_legacy_data.sh

# 2. Construir a imagem (ROS 2 Lyrical + Gazebo Jetty + este workspace)
docker compose -f docker/compose.yaml build

# 3. Treinar os 5 classificadores; os modelos vão para ./models
docker compose -f docker/compose.yaml run --rm train

# 4a. Rodar sem janela: CSV gravado -> kNN -> braço no Gazebo
docker compose -f docker/compose.yaml up sim

# 4b. Ou com a janela do Gazebo (no Linux, rode `xhost +local:` antes)
GUI=true docker compose -f docker/compose.yaml -f docker/compose.gui.yaml up sim
```

O nó `angle_monitor` imprime no terminal os ângulos alvo e atual do ombro e do
cotovelo, como fazia o painel PyQt do mestrado.

Para outro modelo ou outra gravação: `MODEL=lda_6-10-20220_mav_temporal_latest.joblib`
ou `CSV=train_with_openCV_list_16_05.csv` antes do `docker compose up`.

### Encerrar

Qualquer uma destas formas encerra tudo, inclusive o Gazebo:

- **Ctrl+C** no terminal do `docker compose up` (ou do `ros2 launch`);
- `docker compose -f docker/compose.yaml stop`;
- `./scripts/stop.sh`, o equivalente ao botão "Stop" do launcher do mestrado.
  No host ele para os serviços do compose; dentro do container manda SIGINT e,
  se algo sobrar, força o encerramento.

Tempos medidos: 0,4 s sem janela, 3,4 s com janela. No mestrado era preciso
`killall gzserver gzclient`; a causa e a correção estão na decisão D9.

### Trabalhar dentro do container

```bash
docker compose -f docker/compose.yaml run --rm shell
# dentro:
ros2 launch mestrado_bringup sim.launch.py gui:=false        # só o braço
ros2 topic pub --once /arm/elbow/cmd_pos std_msgs/msg/Float64 "{data: 1.57}"
ros2 run mestrado_emg train_legacy /data/6_10_20220.csv --out /models --feature rms --split legacy
```

## Usar o Myo

```bash
MYO_TTY=/dev/ttyACM0 SOURCE=myo docker compose -f docker/compose.yaml -f docker/compose.myo.yaml up sim
```

No Windows, primeiro conecte o dongle ao WSL2 com
[usbipd](https://learn.microsoft.com/windows/wsl/connect-usb). O ombro segue o
pitch do IMU, medido em relação à primeira leitura, como no mestrado.

## Trocar de sensor

Qualquer fonte de sEMG publica nos mesmos tópicos. O classificador e o
simulador não mudam.

| Tópico | Tipo | Conteúdo |
|---|---|---|
| `/emg/raw` | `std_msgs/Float32MultiArray` | Lote de amostras, `layout.dim = [("samples", n), ("channels", c)]` |
| `/emg/imu` | `sensor_msgs/Imu` | Orientação do sensor (opcional; move o ombro) |
| `/emg/label` | `std_msgs/Int32` | Categoria gravada (só no `emg_replay`) |
| `/emg/predicted_class` | `std_msgs/Int32` | Saída do classificador |
| `/arm/shoulder/cmd_pos`, `/arm/elbow/cmd_pos` | `std_msgs/Float64` | Alvo em radianos |
| `/joint_states` | `sensor_msgs/JointState` | Estado das juntas vindo do Gazebo |

Para um sensor novo:

1. Escreva um nó que publique `/emg/raw` (use `samples_to_msg` de
   `mestrado_emg/nodes/common.py`; `myo_driver.py` serve de modelo).
2. Os filtros do mestrado só valem a 200 Hz. Para outra taxa, use
   `LegacyFeatureConfig.for_sensor(fs_hz=..., n_channels=...)`, que recalcula o
   passa-altas e o rejeita-faixa de 60 Hz.
3. Grave dados e **retreine**: ganho, posição e taxa diferentes não deixam os
   modelos do Myo se transferirem.

## Testes e CI

```bash
pip install numpy scipy scikit-learn PyWavelets pandas joblib pyyaml pytest ruff
./scripts/fetch_legacy_data.sh
ruff check . && ruff format --check .
pytest
```

Os testes cobrem:

- equivalência com o código original;
- reprodução da matriz de treino e dos scores históricos;
- protocolo do Myo sem hardware;
- consistência entre o SDF, a ponte ROS↔Gazebo e os tópicos;
- o encerramento do grupo de processos do Gazebo.

O CI ([`.github/workflows/ci.yml`](.github/workflows/ci.yml)) roda isso e
também constrói a imagem, repete os testes dentro dela (incluindo os que
precisam de ROS) e executa o teste de ponta a ponta
[`scripts/integration_test.sh`](scripts/integration_test.sh). Esse teste treina
o kNN, sobe o fluxo inteiro sem janela, confere que o cotovelo segue o
classificador (0° ↔ 90°) e que tudo encerra limpo.

## Resultados reproduzidos

Com features RMS e o split original, os cinco classificadores dão **0,9444**,
exatamente o `scores_of_classifiers.csv` do mestrado. Outras configurações
estão no [inventário](docs/INVENTARIO_MESTRADO.md#resultados-reproduzidos).

São 60 janelas de um único sujeito e 16 a 18 janelas de teste: cada erro vale
6 pontos percentuais. Os números servem para conferir que o porte está fiel,
**não como resultado científico**.

## Estrutura

```
docker/                     Dockerfile, compose (base, janela, Myo), entrypoint
ros2_ws/src/
  mestrado_emg/             features, treino, protocolo do Myo e nós ROS 2
    mestrado_emg/nodes/     myo_driver, emg_replay, emg_classifier, angle_monitor
  mestrado_description/     modelo SDF do braço + mundo (Gazebo Jetty)
  mestrado_bringup/         launch files, ponte ros_gz, gz_sim_group
scripts/                    dados, stop.sh, teste de integração
tests/                      pytest (+ legacy_reference: cópia literal do código original)
docs/                       inventário do mestrado e decisões do porte
data/, models/              fora do git (baixados / gerados)
```

### De onde veio cada parte

| Mestrado | Aqui |
|---|---|
| `Train_Myo_Signals/mod_sig_emg.py`, `train_signals_emg.py` | `mestrado_emg/features.py`, `training.py` |
| `my_arm_def/.../capture_simple_sample.py`, `mod_sig_emg.py` | `mestrado_emg/features.py` |
| `MyoRaw`/`BT` (nos três repositórios) | `mestrado_emg/myo_protocol.py` |
| `my_arm_def/.../capture_braco_pos.py` + `myo_raw.py` | `nodes/myo_driver.py` + `nodes/emg_classifier.py` |
| `my_arm_def/.../arm_controller.py` + `arm_control.cpp` | `JointPositionController` no `model.sdf` |
| `my_arm_def/.../show_angles.py` (painel PyQt) | `nodes/angle_monitor.py` |
| `braco_antebraco_garra.sdf`, `braco_com_mesa.world` | `mestrado_description/` |
| `my_arm_definitive.launch.py` + `main.py` (launcher PyQt) | `mestrado_bringup/launch/` + `docker/compose.yaml` |
| Botão "Stop" (`stop_myo_and_gazebo`) | `scripts/stop.sh` + `gz_sim_group` |

## Problemas conhecidos

- O `parameter_bridge` do `ros_gz` às vezes cai com segfault (`exit code -11`)
  quando recebe dois SIGINT seguidos. É um defeito do pacote do ROS: ele estava
  encerrando de qualquer forma e não deixa nada preso.
- Com a janela, o encerramento leva cerca de 3 s porque a interface do Gazebo
  precisa ser finalizada pelo `gz_sim_group`.

## Uso de IA

O porte, os testes e esta documentação foram feitos com o Claude (Anthropic),
via Claude Code, a partir da leitura dos repositórios originais. A revisão e a
responsabilidade pelo conteúdo são do autor.

## Licença

Apache-2.0, a mesma do `Capture_EMG_Data` e do `Train_Myo_Signals`
(ver [D11](docs/DECISOES.md), pendente de confirmação).

## Autor

**Caio Lima** — UFABC
