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

## A LSTM, refeita (achados 27 e 28)

### O que o notebook faz

No notebook PyTorch da disciplina (`Deep_Learning_EMG_Pytorch_Modificado.ipynb`,
commit `f7d28a4` de `Calima94/DEEP_LEARNING_MYO_SIGNALS`), a divisão não
separa treino e teste:

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

E a rede não é bem uma LSTM sobre o sinal (achado 28):

- `forward` achata a janela de 200 × 4 em 800 números (`x.view(batch, -1)`) e
  entrega ao `nn.LSTM` um tensor de **2 dimensões**. O PyTorch lê isso como
  **uma sequência só, sem lote, cujos passos são as janelas do lote**. A
  recorrência corre de uma janela para a seguinte dentro do lote, e não ao
  longo do tempo dentro de cada janela. Para cada janela, a rede vê 800
  números soltos, como um classificador comum, mais um estado herdado da
  janela anterior do lote.
- O dropout só atua na primeira época: `validate()` põe o modelo em modo de
  avaliação ao fim de cada época e nada o volta para o modo de treino.
- A média móvel usa `range(d.shape[1] - 1)` e deixa o último canal sem
  suavizar.
- Os números do relatório não são todos do mesmo modelo. Os 39 137 parâmetros
  são do modelo padrão, de 12 unidades. Os 0,41 MB são do escolhido pelo
  Optuna, de 32 unidades (106 917 parâmetros). O texto fala em 64 unidades.

### Refeita com as divisões honestas

`mestrado_emg/lstm_gestos.py` repete o notebook: as mesmas janelas, o mesmo
pré-processamento, a mesma rede, os mesmos hiperparâmetros e 200 épocas,
inclusive as particularidades acima. **Só a divisão muda.** No painel, é o
cartão "Refazer a LSTM da disciplina" (cerca de 1 min com 20 núcleos, numa
imagem própria com PyTorch); no menu, a opção 12. Cada divisão roda com 3
sementes; a de participante novo, com as 8 pessoas em cada semente.

Com a divisão do próprio notebook, a reprodução dá **97,0 %** (o relatório diz
96,95 %). Com as mesmas 4095 janelas, 819 de teste e 78 % delas também no
treino, a reprodução é fiel.

| Divisão | Teste também no treino | LSTM | kNN | SVM | LDA |
|---|---|---|---|---|---|
| Como no notebook | 78 % | 97,0 % ± 0,5 | – | – | – |
| Sorteio sem sobreposição (mesmas pessoas) | 0 % | 88,4 % ± 1,4 | 95 % | 93 % | 85 % |
| Participante novo | 0 % | 82,7 % ± 7,1 | 89 % ± 5 | 88 % ± 5 | 83 % ± 6 |

Os clássicos são os da tabela de resultados acima: hold-out de 20 % com a
semente 5, e participante novo. A LSTM é a média de 3 sementes; na divisão por
participante, o desvio é entre as oito pessoas.

| Participante | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 |
|---|---|---|---|---|---|---|---|---|
| LSTM | 94 % | 86 % | 80 % | 85 % | 81 % | 69 % | 88 % | 78 % |
| kNN | 94 % | 87 % | 84 % | 92 % | 93 % | 78 % | 92 % | 89 % |

O que isso mostra:

- **A sobreposição sozinha vale 9 pontos**: de 97 % para 88 %, sem mudar mais
  nada.
- **Com participante novo, a LSTM fica em 83 %**, abaixo do kNN (89 %) e do SVM
  (88 %) e empatada com o LDA (83 %). A conclusão do relatório (os clássicos,
  com um bom pré-processamento, ficam à frente da LSTM) se mantém nas divisões
  honestas. Os números mudam: nenhum lado chega perto de 100 % ou de 97 %.
- **A ordem das janelas não importa, o estado herdado sim.** Ler o teste em
  ordem de gravação (vizinhas do mesmo gesto) dá o mesmo que em ordem
  sorteada. Mas cada janela sozinha, sem estado herdado, perde de 5 a 12
  pontos (85 %, 83 % e 77 % nas três divisões). A rede aprendeu a contar com
  um estado vindo de outra janela, qualquer que seja. Ao vivo, com as janelas
  chegando em sequência, ela teria esse estado, e o número a esperar é o de
  "em ordem de gravação", igual ao da tabela.
- O gesto 3 é o mais confundido, com o 1 e o 4. O gesto 0 acerta 97–100 %. O
  relatório diz que a mão aberta acertou 100 %, o que sugere que o gesto 0 é a
  mão aberta, mas não confirma.

Não foi feito, e pode mudar esses números: ajustar os hiperparâmetros com uma
validação honesta (os do notebook foram escolhidos olhando o teste com
sobreposição) e uma LSTM que percorra o tempo dentro da janela.

## O que muda

- O mestrado não muda: com 8 canais o recorte `iloc[:, :8]` pega exatamente as
  features. O porte reproduz os 0,9444 históricos
  ([INVENTARIO_MESTRADO.md](INVENTARIO_MESTRADO.md#resultados-reproduzidos)).
- Para os dados de gestos, os números a citar são os das tabelas acima.
  Com o sorteio da disciplina: kNN 95 %, SVM 93 %, árvore 91 %, NB 88 %,
  LDA 85 %, LSTM 88 %. Com participante novo: clássicos de 83 % a 89 %, LSTM
  83 %.
- Em aberto: o nome de cada gesto; a LSTM com hiperparâmetros escolhidos sem
  olhar o teste e percorrendo o tempo dentro da janela.
