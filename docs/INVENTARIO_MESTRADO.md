# Inventário técnico do mestrado

Levantamento feito em 2026-09-24/25, lendo o código dos cinco repositórios do
mestrado e rodando o que dava para rodar. Tudo aqui foi **conferido no código ou
medido**. Quando algo não pôde ser verificado, está escrito.

## Os repositórios

| Repositório | Papel no mestrado | Stack original | O que virou aqui |
|---|---|---|---|
| [Capture_EMG_Data](https://github.com/Calima94/Capture_EMG_Data) | Coleta de sEMG (Myo) rotulada por ângulo de cotovelo via webcam + MediaPipe | Python 3, PyQt5, OpenCV, MediaPipe 0.8, pyserial | `mestrado_capture` (câmera + gravação) e `mestrado_emg/myo_protocol.py` |
| [Train_Myo_Signals](https://github.com/Calima94/Train_Myo_Signals) | Features + treino/comparação de 5 classificadores | Python 3, PyQt5, scikit-learn 1.1, PyWavelets | `mestrado_emg/features.py` e `mestrado_emg/training.py` |
| [my_arm_def](https://github.com/Calima94/my_arm_def) | Braço em ROS 2 + Gazebo controlado pelo classificador ao vivo | ROS 2 Foxy, Gazebo 11 (Classic), plugin C++, PyQt5 | `mestrado_description`, `mestrado_bringup` e os nós de `mestrado_emg` |
| [ROS2_arm_py](https://github.com/Calima94/ROS2_arm_py) | Template de pacote ROS 2 | — | Nada a portar: só o esqueleto gerado pelo `ros2 pkg create` e um `main.py` de exemplo do PyCharm |

Ambiente original, segundo o `requirements.yml` do `my_arm_def`: Ubuntu 20.04,
Python 3.8.5 (Anaconda), ROS 2 Foxy, Gazebo 11.

## O pipeline do mestrado

```
Myo (BLED112, 200 Hz, 8 canais)
  │  Capture_EMG_Data: rótulo = categoria de ângulo do cotovelo (webcam + MediaPipe)
  ▼
CSV bruto ──► Train_Myo_Signals ──► *_teste.joblib (LDA, GNB, "lin_svm", kNN, árvore)
                                          │
Myo ao vivo ──► my_arm_def/capture_braco_pos (janela 250 ms → features → kNN)
                     │ classe → POSITIONS_TO_USE = [0, 90, 120, 135, 150]° (cotovelo)
                     │ IMU (pitch relativo à 1ª leitura) → ombro
                     ▼
                myo_raw → serviços pos_reach* → arm_controller (P) → plugin C++ → Gazebo 11
```

Features, iguais no treino e ao vivo (salvo o item 2 abaixo): filtro IIR
passa-altas → rejeita-faixa em torno de 60 Hz → reconstrução wavelet db7 de 4
níveis → MAV ou RMS por canal em janelas de 250 ms (50 amostras).

## Achados

Numerados para referência. A coluna "No porte" diz o que foi feito com cada um.

| # | Achado | Evidência | No porte |
|---|---|---|---|
| 1 | **O kNN (o classificador usado ao vivo) e a árvore de decisão não carregam** no scikit-learn atual. LDA, GNB e SVC carregam com aviso de versão | `joblib.load` com scikit-learn 1.9.1: `AttributeError: EuclideanDistance` (kNN) e `ValueError: node array ... incompatible dtype` (árvore) | Retreino a partir do CSV bruto (`train_legacy`) |
| 2 | **Treino e uso ao vivo usavam features diferentes.** O treino calculava RMS e o nó ao vivo, MAV | `Train_Myo_Signals/Parameters/parameters.csv`: `type_matrix = rms`. `my_arm_def/.../capture_simple_sample.py`: `type_matrix = "mav"`. RMS reproduz a `training_matrix_csv_m_class.csv` com erro de 6e-14; MAV não (teste `test_rms_features_reproduce_the_thesis_training_matrix`) | Cada modelo é salvo junto com a configuração de features, e o classificador ao vivo usa a do modelo |
| 3 | Os `.joblib` dentro do `my_arm_def` **não são os mesmos** do `Train_Myo_Signals/files_joblib` (MD5 diferentes) | `md5sum` | Não dá para saber com que features eles foram treinados. Não afeta o porte, que retreina |
| 4 | **O laço da wavelet ignora `layers_to_catch`.** `for i in range(1, -1, -(levels + 1))` visita só `i = 1`, e `-1` nunca está entre as camadas (números positivos), então o detalhe mais grosso (cD4) é **sempre** zerado, qualquer que seja a escolha "layers to use" da tela de treino | Leitura do código + teste `test_wavelet_layers_setting_is_effectively_ignored` | **Reproduzido de propósito** como padrão (mudaria as features dos modelos históricos). O modo `faixas` faz o que a tela prometia (D23) |
| 5 | **"lin_svm" não é linear:** é `svm.SVC(decision_function_shape='ovo')`, kernel RBF | `mod_sig_emg.apply_classifiers` | Nome histórico mantido, docstring explica |
| 6 | Nomes dos filtros trocados: `sos_low_pass_` é passa-altas (zeros `[1, -2, 1]`), e no `parameters.csv` `sos_high_pass_` guarda os coeficientes do rejeita-faixa e vice-versa. O treino aplicava os dois em ordem inversa à do ao vivo | Coeficientes nos dois repositórios | **Inofensivo:** os dois filtros são lineares e invariantes no tempo com estado inicial zero, e a ordem não altera o resultado (confirmado no teste de equivalência). Nomes corrigidos no porte |
| 7 | `m_rms_values_` do `my_arm_def` tem nomes indefinidos (`n_of_chanels_and_category`, `rms_table_`) | `my_arm_def/.../mod_sig_emg.py` | Ao vivo só o MAV funcionava. O porte usa uma implementação única |
| 8 | A avaliação histórica é otimista: `StratifiedShuffleSplit` por janela põe janelas vizinhas da mesma gravação no treino e no teste; um sujeito, uma sessão, **18 janelas de teste** | `mod_sig_emg.Strat_train_test` | Split `legacy` só para reproduzir o histórico; split `temporal` (blocos + 1 janela de purga) como padrão |
| 9 | `OrdinalEncoder` ajustado separadamente em treino e teste | `mod_sig_emg.encode_data` | Inofensivo com split estratificado; o porte usa um índice de classe único |
| 10 | Árvore de decisão sem `random_state`: resultado não reprodutível | `apply_classifiers` | `random_state = seed` |
| 11 | Caminhos absolutos fixos (`/home/caio/my_arm_def/neigh_teste.joblib`, `/home/caio/.../braco_antebraco_garra.sdf`) | `mod_sig_emg.predict_data`, `spawn_arm.py` | Viraram parâmetros de ROS |
| 12 | Lei de controle não linear: `vel = kp·e + vel_atual·kd·e`; o ombro publicava só o erro (`kp` efetivo 1) | `arm_controller.py` | Nó `arm_controller` com `v = kp·e` e os mesmos `kp` (ver D2). O termo `kd` foi removido |
| 13 | **Inércia do braço (`link_1`) cerca de 36× maior que a de um cilindro de 1,924 kg × 22 cm** (0,2806 contra 0,0079 kg·m²). A do antebraço confere (0,00484). As da garra também parecem altas | Cálculo `m(3r²+L²)/12` | **Mantida** por fidelidade. Com controle por velocidade o efeito é pequeno. Revisar ao evoluir o gêmeo digital |
| 14 | O comentário do modo EMG diz "0x02 → 50 Hz filtrado", mas 0x02 é `send_emg` a 200 Hz; o modo de 50 Hz é o sinal retificado do handle 0x28 | Comentários do `start_raw` e taxa medida nos CSVs (~200 amostras/s) | Byte 0x02 mantido (é o que gravou os dados de treino); comentário corrigido |
| 15 | **O programa não saía com Ctrl+C.** O botão "Stop" do launcher mandava SIGINT ao launch e rodava `killall gzserver gzclient gazebo` 100 vezes | `my_arm_def/main.py`, `stop_myo_and_gazebo()` | Causas e solução em [DECISOES.md](DECISOES.md), D9 |
| 16 | No botão "Stop", o `MyoRaw().disconnect()` não fazia nada: uma instância nova tem `conn = None` | `MyoRaw.disconnect` | O que sempre limpou a conexão presa foi o `connect()` desconectar os handles 0–2 antes de escanear, e isso foi mantido |
| 17 | **Bug na conclusão das categorias da captura.** `check_if_num_samples_is_complete` enumera `Counter(rótulos).values()`: se uma categoria posterior recebe amostras antes de uma anterior, a *anterior* é marcada como completa | `pose_module.py` + teste `test_thesis_completion_bug_is_fixed`, que roda a função original | Contagem por categoria (`CategoryRecorder`) |
| 18 | A API `mp.solutions.pose` **não existe no MediaPipe 1.x** | Conteúdo do wheel `mediapipe-1.0.1` | API Tasks (`PoseLandmarker`), mesmos marcos (D13) |
| 19 | A gravação usava o último ângulo medido indefinidamente, mesmo se a câmera perdesse o braço | Variável global `actual_angle` | Ângulo com mais de 0,5 s é tratado como desconhecido |
| 20 | O vídeo salvo pela ferramenta (`Videos/test_2_05.avi`) já está espelhado e tem o traçado desenhado por cima | O vídeo | Processar com `flip=false` (D14). O traçado atrapalha a detecção onde cobre o braço |
| 21 | **Os arquivos `train_with_openCV_list_16_05*.csv` foram gravados no modo de 50 Hz do Myo** (envoltória retificada: valores de 17 a 637, ~40 amostras/s), mas eram o arquivo padrão da tela de treino, que os processava como 200 Hz. O `6_10_20220.csv`, dos scores históricos, é bruto (−27 a 15, ~177 amostras/s) | Coluna `time` e faixa de valores; `train_emg_data.ui` | `analyze_legacy` mede a taxa e avisa; os dois arquivos ficam fora dos resultados ([ANALISE_RESULTADOS.md](ANALISE_RESULTADOS.md)) |
| 22 | **Categoria e tempo confundidos.** No `6_10_20220.csv` cada categoria é um único bloco contínuo, gravado uma depois da outra, e uma regra de um número (média do MAV dos 8 canais) acerta tanto quanto os cinco classificadores | `analyze_legacy`: referência `amplitude` 1,00 no hold-out e 0,98 na CV temporal | Documentado; a referência `amplitude` entra em toda análise |
| 23 | Os SOS do mestrado não têm o ganho: o passa-altas amplifica 15,5× e o rejeita-faixa 1,5× na banda de passagem | `scipy.signal.sosfreqz` | **Inofensivo** para os cinco classificadores, que não mudam com escala uniforme; mantido por fidelidade |
| 24 | A curva ROC da tela de treino usava a previsão 0/1, o que dá um ponto só; o campo `cv` existia, mas as chamadas de validação cruzada estavam comentadas | `Train_Myo_Signals/main.py` (`plot_roc_curve`), `mod_sig_emg.apply_classifiers` | ROC com escore contínuo e CV temporal e embaralhada no `analyze_legacy` |
| 25 | **A etapa wavelet do mestrado quase não altera as features.** Zerar só o cD4 (6,25–12,5 Hz a 200 Hz) muda o MAV em 0,3% (mediana por canal e janela no `6_10_20220.csv`), porque o passa-altas já removeu essa faixa. E a db7 em janelas de 50 amostras só tem 1 nível útil; com 4, os níveis mais profundos são dominados por efeitos de borda | Medido com o pipeline do porte; `pywt.dwt_max_level(50, 14) = 1` | Documentado. Wavelet, níveis, camadas e janela voltaram a ser escolhas (D23), com o nível útil avisado no painel e no terminal |
| 26 | **Com menos de 8 canais, o app treina com o rótulo como entrada.** `sklearn_spare_test_train` separa as features com `iloc[:, :8]`; com os 4 canais dos dados de gestos da disciplina, a quinta coluna é a `Category`. Daí os 100 % de GNB, "lin_svm", kNN e árvore no relatório da disciplina; o LDA (84,79 %) não aproveitou a coluna. Com 8 canais (o mestrado) o recorte é exato | A própria função do app nos mesmos dados: 1,00 com o rótulo, 0,88–0,95 sem ele, igual ao porte ([ANALISE_GESTOS.md](ANALISE_GESTOS.md)) | O porte escolhe os canais pelo nome. Dados, parâmetros e validação por participante no painel (D25) |
| 27 | **No notebook LSTM da disciplina, treino e teste se sobrepõem.** Cada `EMGDataset` sorteia a sua própria divisão, sem semente, então ~80 % das janelas de teste também estão no treino; o Optuna escolhe os hiperparâmetros por esse mesmo teste | `Deep_Learning_EMG_Pytorch_Modificado.ipynb`, células 4, 6, 11 e 17 | Refeita igual, mudando só a divisão (`lstm_gestos`, D26): 97,0 % como no notebook, 88,4 % sem sobreposição, 82,7 % com participante novo ([ANALISE_GESTOS.md](ANALISE_GESTOS.md)) |
| 28 | **A "LSTM" da disciplina não percorre o tempo da janela.** `forward` achata a janela 200 × 4 em 800 números e passa ao `nn.LSTM` um tensor 2-D, que o PyTorch lê como uma sequência só cujos passos são as janelas do lote; a recorrência vai de uma janela à seguinte. Ainda: o dropout só atua na primeira época (`validate()` deixa o modelo em avaliação), o último canal fica sem média móvel, e os 39 137 parâmetros do relatório são do modelo padrão de 12 unidades, não do escolhido (32 unidades, 106 917 parâmetros, os 0,41 MB) | Células 4, 7, 8 e 13 do notebook; contagem de parâmetros com o `EMGModel` dele. Sem o estado herdado (uma janela por vez), a acurácia cai de 5 a 12 pontos | Reproduzido de propósito, para mudar só a divisão. Uma LSTM sobre o tempo da janela fica em aberto |
| 29 | **O controle do mestrado não acompanha um cotovelo humano.** Com kp = 1 (constante de tempo de ~1 s), o cotovelo do Gazebo repete um movimento gravado do Reach&Grasp com a forma certa (correlação 0,98), mas 0,7 a 0,8 s atrasado, e corta os picos: chega a 83 % da excursão em `ReaCyl` (sujeito 1) e a 67 % em `EatFruit`, que é mais rápido | `scripts/check_movement.py` sobre o modo movimento real (D27), 2026-09-27 | **Mantido** por fidelidade (kp é parâmetro do `arm_controller`, `kp.elbow_joint`). Um gêmeo digital que siga o braço em tempo real vai precisar de outro controle: decisão futura, não deste porte |

## Ângulo do cotovelo: MediaPipe 1.x × ferramenta original

No trecho do vídeo do mestrado em que o braço aparece sem o traçado por cima,
o `PoseLandmarker` (modelo *full*, visibilidade ≥ 0,5) comparado ao número que
a ferramenta original imprimiu na tela:

| Quadro | 180 | 195 | 210 | 225 | 240 |
|---|---|---|---|---|---|
| Ferramenta do mestrado (impresso no vídeo) | 94 | 93 | 94 | 94 | 95 |
| Porte (MediaPipe 1.0.1) | 92,2 | 93,3 | 95,6 | 93,6 | 96,1 |

Diferença máxima de 1,8°; o teste `test_mediapipe_matches_thesis_angles_on_thesis_video`
aceita até 3°. No começo do vídeo, com o braço esticado quase fora do quadro e
coberto pelo traçado antigo, a visibilidade é baixa e as leituras são
descartadas.

## Resultados reproduzidos

Arquivo `6_10_20220.csv`: um sujeito, uma sessão, 2 categorias, 60 janelas de
250 ms. Semente 42. Python 3.14, scikit-learn 1.7.2 (imagem Docker).

| Configuração | LDA | GNB | "lin_svm" | kNN | Árvore | Janelas de teste |
|---|---|---|---|---|---|---|
| Histórico (`scores_of_classifiers.csv`) | 0,9444 | 0,9444 | 0,9444 | 0,9444 | 0,9444 | 18 |
| Porte, RMS + split `legacy` | 0,9444 | 0,9444 | 0,9444 | 0,9444 | 0,9444 | 18 |
| Porte, MAV + split `legacy` | 1,0000 | 0,9444 | 0,9444 | 0,9444 | 0,9444 | 18 |
| Porte, MAV + split `temporal` | 0,8750 | 0,9375 | 1,0000 | 1,0000 | 0,9375 | 16 |

A segunda linha **reproduz exatamente** o histórico (teste
`test_historical_scores_are_reproduced`). Com 16 a 18 janelas de teste, cada
erro vale 6 pontos percentuais: essas acurácias servem para conferir que o
porte funciona, **não como resultado científico**. Não há avaliação
entre sujeitos possível com esses dados.
