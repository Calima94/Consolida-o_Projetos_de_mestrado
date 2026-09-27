# Análise dos dados de gestos da disciplina

## Contexto e escopo

Depois do mestrado, na disciplina de Deep Learning do PPGINF (UFABC), o app de
treino do mestrado foi usado em outro conjunto de dados. O relatório *Hand
Gesture Classification via Long Short-Term Memory (LSTM) Neural Networks*
comparou uma LSTM (PyTorch, ajustada com Optuna) com os cinco classificadores
do app. Relatou 97 % para a LSTM, 84,79 % para o LDA e 100 % para a árvore de
decisão, o kNN, o Naive Bayes e o SVM.

Este documento refaz a parte dos classificadores com o porte, nos mesmos dados
e com os mesmos parâmetros. **Não trata da dissertação**: o conjunto de dados,
o objetivo e os números são da disciplina. O mestrado é afetado só por um
detalhe de código, e só com menos de 8 canais (achado 26 abaixo). Com os 8
canais do Myo o problema não ocorre.

## Os dados

São os de Toro-Ossaba et al., *LSTM Recurrent Neural Network for Hand Gesture
Recognition Using EMG Signals*, Applied Sciences 12(19), 9700, 2022:
8 participantes × 5 gestos, bracelete de 4 canais a 1000 Hz, cerca de 20 s por
gesto. `scripts/fetch_gesture_data.sh` baixa os 40 arquivos da pasta da
disciplina no Drive e confere o SHA-256 de cada um. Depois grava
`data/gestos_1khz.csv`: 822 691 amostras, com as colunas `time`, `channel1..4`,
`participante` e `position`.

A figura 1 do relatório nomeia os gestos: mão aberta, preensão total, pinça,
apontar e o gesto "rock". Nem os dados nem os notebooks dizem qual arquivo
(0 a 4) é qual gesto. Por isso os rótulos ficam `gesto_0` a `gesto_4`.

## Como reproduzir

No painel:

1. Manutenção → Dados → **Gestos da disciplina** (uma vez; 82 MB).
2. Em "Parâmetros do sinal", **Como na disciplina**. Isso escolhe
   `gestos_1khz.csv`, 1000 Hz, RMS, janela de 200 ms, divisão `legacy` (sorteio),
   20 % de teste e semente 5, os valores do `parameters.csv` da disciplina. Os
   filtros e a wavelet ficam os do mestrado, como lá.
3. **Analisar**. As figuras vão para
   `models/analise/gestos-1khz_rms_legacy_fs1000-c4-w200/`.

No terminal:

```bash
docker compose -f docker/compose.yaml run --rm train \
  ros2 run mestrado_emg analyze_legacy /data/gestos_1khz.csv --out /models/analise \
  --feature rms --split legacy --seed 5 --test-size 0.2 --fs 1000 --window-ms 200
```

## Resultados

Acurácia com os filtros do mestrado, como na disciplina: 4110 janelas, 822 de
teste. Os filtros, feitos para 200 Hz, cortam em ~71 Hz e ~300 Hz a 1000 Hz, e
o comando avisa isso. Scikit-learn 1.7.2.

| Classificador | Hold-out (sorteio, 20 %) | CV embaralhada | CV temporal | Participante novo |
|---|---|---|---|---|
| LDA | 0,85 | 0,85 ± 0,00 | 0,82 ± 0,05 | 0,83 ± 0,06 |
| Naive Bayes | 0,88 | 0,89 ± 0,01 | 0,84 ± 0,08 | 0,84 ± 0,08 |
| "lin_svm" | 0,93 | 0,93 ± 0,01 | 0,88 ± 0,04 | 0,88 ± 0,05 |
| kNN | 0,95 | 0,94 ± 0,01 | 0,87 ± 0,04 | 0,89 ± 0,05 |
| Árvore | 0,91 | 0,91 ± 0,01 | 0,84 ± 0,04 | 0,83 ± 0,06 |
| Amplitude (referência) | 0,68 | 0,70 ± 0,00 | 0,69 ± 0,07 | 0,68 ± 0,08 |

- **Hold-out e CV embaralhada** sorteiam janelas, então o teste tem janelas
  vizinhas das de treino, das mesmas pessoas. É o que a disciplina mediu.
- **CV temporal** testa blocos contíguos de cada gesto.
- **Participante novo** treina com sete pessoas e testa na oitava, uma de cada
  vez (média ± desvio entre as oito). É o caso de quem põe a prótese sem ter
  gravado dados de treino. A análise acrescenta essa coluna sempre que o CSV tem
  a coluna `participante`.
- **A referência de amplitude** (um número por janela) fica em 0,68, bem abaixo
  dos classificadores. Aqui eles usam o padrão espacial dos canais, e não só o
  nível de ativação. É o contrário do conjunto de demonstração do mestrado
  ([ANALISE_RESULTADOS.md](ANALISE_RESULTADOS.md)).

Com filtros projetados para 1000 Hz (passa-altas de 20 Hz, rejeita-faixa em
60 Hz) os números quase não mudam: kNN 0,94 no hold-out e 0,87 ± 0,06 com
participante novo.

Por participante (participante novo, filtros do mestrado):

| Participante | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 |
|---|---|---|---|---|---|---|---|---|
| kNN | 0,94 | 0,87 | 0,84 | 0,92 | 0,93 | 0,78 | 0,92 | 0,89 |
| "lin_svm" | 0,95 | 0,88 | 0,84 | 0,94 | 0,88 | 0,78 | 0,89 | 0,91 |
| LDA | 0,83 | 0,82 | 0,80 | 0,92 | 0,84 | 0,72 | 0,79 | 0,89 |

Os participantes 3 e 6 são os mais difíceis; o 6 fica abaixo de 0,80 em
todos os classificadores.

## Os 100 % do app na disciplina (achado 26)

A função `sklearn_spare_test_train` do app (`mod_sig_emg.py`) separa as
entradas com `Train.iloc[:, :8]`: as 8 primeiras colunas da matriz de
features. Ela foi escrita para os 8 canais do Myo, e aí as 8 colunas são
exatamente as features. **Com 4 canais, a matriz tem 5 colunas, e a quinta é a
`Category`.** O recorte leva junto o rótulo, e o classificador recebe a
resposta como entrada.

Conferido rodando a própria função do app nas mesmas janelas:

| | LDA | GNB | "lin_svm" | kNN | Árvore |
|---|---|---|---|---|---|
| App, como na disciplina | 0,8479 | 1,0000 | 1,0000 | 1,0000 | 1,0000 |
| App, só as 4 colunas de canais | 0,8479 | 0,8783 | 0,9282 | 0,9477 | 0,9100 |
| Porte (hold-out acima) | 0,85 | 0,88 | 0,93 | 0,95 | 0,91 |

A primeira linha é o `scores_of_classifiers.csv` da disciplina. A segunda
coincide com o porte. O LDA dá o mesmo valor nas duas porque não aproveitou a
coluna do rótulo, e por isso os **84,79 % do relatório são um número válido**.
Os 100 % dos outros quatro não são: sem o rótulo eles ficam entre 88 % e 95 %
com o mesmo sorteio, e entre 83 % e 89 % com participante novo.

O porte não tem esse problema: `load_legacy_csv` escolhe as colunas de entrada
pelo nome (`channel…`), e o rótulo e o participante ficam à parte, com
qualquer número de canais.

## E os 97 % da LSTM? (achado 27)

Não refiz a LSTM. Mas, lendo o notebook PyTorch da disciplina
(`Deep_Learning_EMG_Pytorch_Modificado.ipynb`), a comparação também não se
sustenta do lado dela:

- `EMGDataset` sorteia a divisão treino/teste **dentro do construtor**, com
  `np.random.shuffle` e sem semente. O conjunto de treino e o de teste são dois
  objetos construídos um depois do outro, e **cada um sorteia a sua própria
  ordem**. O teste (os 20 % finais de um sorteio) e o treino (os 80 % iniciais
  de outro sorteio) se sobrepõem: em média, 80 % das janelas de teste também
  estão no treino, só com um ruído de 5 % do desvio padrão somado.
- O Optuna escolhe os hiperparâmetros pela acurácia nesse mesmo conjunto de
  teste (97,68 % no melhor ensaio). Os 96,95 % finais são medidos nele também.
- O notebook Keras de referência (os 90 %) divide com
  `train_test_split(test_size=0.2, stratify=Y)`: janelas sorteadas, sem
  sobreposição, mas com as mesmas pessoas no treino e no teste.

Detalhe menor: a média móvel usa `range(d.shape[1] - 1)` e deixa o último canal
sem suavizar.

Os 97 % são, então, um limite superior, e não se sabe quanto cairiam. Para
comparar LSTM e classificadores clássicos é preciso **a mesma divisão para os
dois**. A mais útil para prótese é a de participante novo, que a análise já
calcula para os clássicos (83–89 %).

## O que muda

- O mestrado não muda: com 8 canais o recorte `iloc[:, :8]` pega exatamente as
  features. O porte reproduz os 0,9444 históricos
  ([INVENTARIO_MESTRADO.md](INVENTARIO_MESTRADO.md#resultados-reproduzidos)).
- Para os dados de gestos, os números a citar são os da tabela de resultados.
  Com o sorteio da disciplina: kNN 95 %, SVM 93 %, árvore 91 %, NB 88 %,
  LDA 85 %. Com participante novo: 83 % a 89 %.
- Em aberto: a LSTM com divisão por participante, e o nome de cada gesto.
