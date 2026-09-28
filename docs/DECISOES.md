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

**D23. Wavelet, níveis, camadas e janela voltam a ser escolhas.** A tela de
treino do mestrado deixava escolher a wavelet-mãe (campo livre, `db7`), os
níveis (1 a 4), as "layers to use" (1 a 4, isto é, as camadas 1..n) e a janela;
o porte tinha fixado tudo no padrão. Agora `train_legacy` e `analyze_legacy`
aceitam `--wavelet`, `--levels`, `--wavelet-mode`, `--layers`, `--approx` e
`--window-ms`, e o painel e o menu oferecem as mesmas escolhas. Os modelos
guardam a configuração, e o classificador ao vivo usa a do modelo (achado 2).

- **Dois modos de camadas.** `legacy` (padrão) reproduz o laço do mestrado, em
  que a escolha de camadas não faz efeito e só o D*n* é zerado (achado 4); é o
  que reproduz os modelos e os números históricos. `bands` mantém exatamente as
  camadas escolhidas (1 = a mais fina, `fs/4..fs/2`) e, se pedido, a
  aproximação, e zera o resto antes do MAV/RMS. É o que a tela prometia.
- **Nomes que não se sobrescrevem.** Escolhas diferentes das do mestrado viram
  um rótulo no nome de modelos, relatórios e pastas de análise
  (`..._temporal_sym4-n2-D12_latest.joblib`). Com as escolhas do mestrado os
  nomes não mudam, então os launch files e o menu seguem funcionando.
- **O nível útil é avisado, não imposto.** A db7 em janelas de 50 amostras só
  tem 1 nível útil (achado 25), mas o mestrado usava 4, então 4 continua
  permitido, com aviso.

Medido no `6_10_20220.csv` (CV temporal, 5 partições): o mestrado dá k-NN 0,98;
faixas D1+D2 com db7, 1,00; só D1, 0,95; db4 com 2 níveis e D1+D2, 0,98; haar
com D1 a D3, 0,98. A referência de amplitude fica entre 0,95 e 0,98 em todos.
Neste conjunto a escolha pouco importa, porque um único nível de amplitude já
separa as classes ([ANALISE_RESULTADOS.md](ANALISE_RESULTADOS.md)); ela deve
pesar em gravações com mais categorias ou com ângulo contínuo. A taxa e os
filtros IIR vieram depois (D24).

**D24. Taxa de amostragem e filtros IIR também são escolhas.** A tela do
mestrado tinha a frequência de captura e os arquivos dos dois filtros. Agora
`--fs` e `--filters legacy|design|files` fazem o mesmo em `train_legacy` e
`analyze_legacy`, e o painel e o menu oferecem as duas escolhas. O número de
canais vem do cabeçalho do CSV.

- **Os coeficientes do mestrado continuam o padrão**, mesmo em outra taxa,
  porque é o que a tela fazia e o que a disciplina usou. Foram projetados para
  200 Hz: a 1000 Hz o passa-altas vai de ~14 para ~71 Hz e o rejeita-faixa de
  60 para ~300 Hz. O terminal e o painel avisam e mostram onde eles cortam.
- **`design`** calcula, para a taxa escolhida, um Butterworth passa-altas de
  4ª ordem e um rejeita-faixa de 2ª ordem em torno da rede (60 ou 50 Hz, ou
  nenhum).
- **`files`** lê SOS de `data/filtros/`: o CSV do app do mestrado, 6 números
  por linha, JSON ou `.npy`. Recusa arquivo sem 6 colunas, com `a0` zero ou
  com polo fora do círculo unitário: um filtro instável faria o treino
  terminar em NaN sem dizer por quê.
- O painel mede a taxa pela coluna `time` e oferece "Usar ... Hz" quando ela
  difere da escolhida. Taxa, filtros e canais entram no nome dos modelos e das
  pastas (`fs1000-c4-hp20-rf60`).

**D25. Os dados de gestos da disciplina entram no projeto, com validação por
participante.** A disciplina de Deep Learning (PPGINF) usou o app do mestrado
nos dados de Toro-Ossaba et al. (2022,
[doi:10.3390/app12199700](https://doi.org/10.3390/app12199700)): 8 participantes, 5 gestos, 4 canais a
1000 Hz. `scripts/fetch_gesture_data.sh` os baixa com SHA-256 conferido e
grava um CSV só, com a coluna `participante`. No painel, "Como na disciplina"
preenche os parâmetros usados lá, e "Parte de teste (%)" dá o `--test-size`.

- **A validação por participante aparece quando o CSV diz quem gravou.**
  Treina com todos os outros e testa em cada participante: funciona em quem
  não gravou dados de treino? Hold-out e as outras CVs continuam iguais, para
  a reprodução da disciplina não mudar.
- **O rótulo é texto (`gesto_0`...)**, porque o treino descarta o rótulo 0
  ("fora de toda categoria" na captura). Os nomes dos gestos não estão nos
  dados nem nos notebooks.
- Resultado: 85–95 % com o sorteio da disciplina e 83–89 % com participante
  novo, não os 100 % relatados (achado 26). Detalhes em
  [ANALISE_GESTOS.md](ANALISE_GESTOS.md).

A LSTM da disciplina foi refeita com a mesma divisão por participante (D26).

**D26. A LSTM da disciplina, refeita igual, numa imagem própria.**
`mestrado_emg/lstm_gestos.py` repete o notebook PyTorch da disciplina e muda
só a divisão treino/teste: a do notebook (com sobreposição, achado 27), sorteio
sem sobreposição e participante novo.

- **Igual, inclusive no que parece errado.** A arquitetura (a recorrência corre
  entre as janelas do lote, achado 28), o dropout só na primeira época, a
  média móvel sem o último canal e os hiperparâmetros escolhidos olhando o
  teste ficam como estão. Corrigir qualquer um deles misturaria dois efeitos,
  e a pergunta era quanto a divisão muda o resultado. A reprodução com a
  divisão do notebook dá 97,0 % (o relatório diz 96,95 %), o que confere a
  fidelidade.
- **Uma diferença, pequena e declarada:** nas divisões novas, o valor máximo
  que normaliza as janelas vem só das de treino (o notebook o tira de todas).
- **Imagem própria (`docker/Dockerfile.lstm`, perfil `lstm` do compose).** O
  PyTorch para CPU ocupa ~1,7 GB com a imagem, e nada do ROS precisa dele. Com
  o perfil, `docker compose build` e o botão "Construir a imagem" continuam sem
  baixá-lo; o cartão do painel e a opção 12 do menu constroem na primeira vez.
  O `ci_local.sh` roda os testes da LSTM nessa imagem quando ela existe; o CI
  do GitHub não a constrói.
- **Rápido o bastante para um botão.** Cada treino dura ~15–25 s na CPU. Os 30
  treinos (3 sementes × 10 divisões) rodam em paralelo, um por núcleo, em
  cerca de 1 min com 20 núcleos, e com as mesmas sementes o resultado se
  repete exatamente.

Resultado: 97,0 % → 88,4 % sem a sobreposição → 82,7 % com participante novo,
abaixo do kNN (89 %) e do SVM (88 %) na mesma divisão
([ANALISE_GESTOS.md](ANALISE_GESTOS.md)). *Rever se* for testada uma LSTM que
percorra o tempo dentro da janela, ou hiperparâmetros escolhidos com
validação honesta: aí o módulo ganha uma opção, e a reprodução fiel continua
sendo o padrão.

**D27. Movimento real: um cotovelo humano gravado move o braço do Gazebo.**
O modo `movimento` (compose, painel, menu) lê o ângulo do cotovelo de um
ensaio do **Reach&Grasp** (Di Domenico et al., *Scientific Data* 12, 233,
2025; IIT Dataverse, [doi:10.48557/L6OWMM](https://doi.org/10.48557/L6OWMM),
versão 1.0, CC BY 4.0) e o publica como alvo em `/arm/elbow/cmd_pos`, no ritmo
da gravação (100 Hz). É o dataset principal do `semg-digital-twins` (ADR-007),
descrito no contrato de dados de lá (`docs/DATA_CONTRACT_REACH_GRASP.md`).

- **Por quê:** o gêmeo digital passa a funcionar com dados que já existem, sem
  sEMG, sem modelo e sem hardware, e com o mesmo alvo que a regressão contínua
  vai ter de prever.
- **Alvo:** `RElbow_X`, em graus, convertido direto para radianos, porque o
  cotovelo do simulador também é 0 quando estendido. Não há a inversão de
  180° − ângulo usada para a câmera.
- **Convenção confirmada (2026-09-27):** o contrato de dados mede que
  alcançar diminui o ângulo e levar à boca o aumenta, compatível com
  0° = estendido, mas não achou a confirmação na documentação do Plug-in-Gait.
  A conferência visual foi feita no Windows, com `EatFruit` do sujeito 1, na
  janela do Gazebo e na página do braço: o braço estica ao alcançar e dobra ao
  levar à boca. Os números concordam: na boca o ângulo chega a ~130°, e levar
  a mão à boca pede mais de ~120° de flexão; com a convenção oposta seriam
  ~50°.
- **Lacunas:** nas amostras em que o Vicon perdeu o cotovelo (9 dos 160
  ensaios, até 3,5 % delas), o alvo anterior é mantido. Nada é interpolado, e
  o log diz quantas foram.
- **Dados fora do git:** `scripts/fetch_reach_grasp.py` baixa só a cinemática
  (~2 MB por ensaio, ~280 MB tudo), fixa a versão 1.0 e confere o MD5 que o
  Dataverse publica. Usa só a biblioteca padrão.
- **Medido:** o controle do mestrado deixa o braço 0,7 a 0,8 s atrás da pessoa
  e corta os picos (achado 29). Isso fica como está, por fidelidade.

*Rever se* a convenção angular for desmentida, ou se o gêmeo digital precisar
seguir o braço em tempo real (aí o controle muda, em decisão própria).

**D28. As regras do CNPq sobre IA valem aqui também.** O `semg-digital-twins`
adota, na sua ADR-003, a **Portaria CNPq nº 2.664/2026** (Política de
Integridade na Atividade Científica, de 11/03/2026;
[anúncio oficial](https://www.gov.br/cnpq/pt-br/assuntos/noticias/cnpq-em-acao/cnpq-publica-portaria-que-institui-politica-de-integridade-na-atividade-cientifica))
como regra vinculante para qualquer material que vire publicação, submissão,
relatório ou entrega. Este repositório é a base de simulação daquele projeto e
foi feito quase todo com IA, então segue a mesma regra.

- **Por quê:** a portaria não proíbe usar IA; proíbe **esconder** o uso. Exige
  declarar a ferramenta, a fase e a finalidade, e põe no autor a
  responsabilidade por tudo, inclusive erros da ferramenta. As sanções vão de
  advertência a revogação de fomento e devolução de recursos.
- **O que muda na prática:** o [`CLAUDE.md`](../CLAUDE.md) passa a trazer as
  regras para toda sessão de IA neste repositório. PRs levam o label
  `agent:claude-code`, aplicado também aos PRs #1 a #9. A seção "Uso de IA" do
  README declara ferramenta, fase e finalidade. A documentação escrita
  predominantemente por IA leva rodapé. Toda referência tem link verificável:
  a de Toro-Ossaba et al. (2022), citada sem DOI na D25, ganhou
  [doi:10.3390/app12199700](https://doi.org/10.3390/app12199700), conferido no
  Crossref.
- **Vedado:** conteúdo de IA apresentado como de autoria humana, referência ou
  dado inventado, parecer de revisor escrito por IA, entrega sem revisão do
  Caio.
- **Mudanças de regra** entram por PR que o Caio aprova e integra.

*Rever se* a portaria mudar, a UFABC publicar norma própria, ou a ADR-003 do
`semg-digital-twins` for alterada.

---

*Redigido predominantemente por Claude (Anthropic), via Claude Code, a pedido do Caio Lima (declaração de uso de IA: Portaria CNPq nº 2.664/2026, D28). Aprovação: Caio Lima, pelo merge dos PRs.*
