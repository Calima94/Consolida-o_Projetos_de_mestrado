# Avisos de terceiros

O repositório é MIT (ver `LICENSE`). As partes abaixo vêm de terceiros ou de
código do mestrado escrito em conjunto, e mantêm os seus próprios termos.

## myo-raw — `ros2_ws/src/mestrado_emg/mestrado_emg/myo_protocol.py`

Protocolo do Myo portado das classes `MyoRaw`/`BT` usadas nos repositórios do
mestrado, que por sua vez vêm de:

- **dzhu/myo-raw** — <https://github.com/dzhu/myo-raw> — MIT, texto abaixo.
- **Alvipe/myo-raw** — <https://github.com/Alvipe/myo-raw> — fork do anterior,
  mesma licença MIT (arquivo `LICENSE` do fork, conferido em 2026-09-25).
- **PyoConnect**, de Fernando Cosentino —
  <http://www.fernandocosentino.net/pyoconnect> — **licença não verificada**:
  a página não informa licença e não há repositório com arquivo de licença.

```
The MIT License (MIT)

Copyright (c) 2014 Danny Zhu

Permission is hereby granted, free of charge, to any person obtaining a copy of
this software and associated documentation files (the "Software"), to deal in
the Software without restriction, including without limitation the rights to
use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of
the Software, and to permit persons to whom the Software is furnished to do so,
subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS
FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR
COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER
IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN
CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
```

## Base da ferramenta de captura — Alan Mendes

`ros2_ws/src/mestrado_capture/` (lógica de ângulo e de categorias) e
`tests/legacy_reference/capture_pose_module.py` (cópia literal) vêm do
[Capture_EMG_Data](https://github.com/Calima94/Capture_EMG_Data), cuja versão
base, sem o módulo de EMG, é de **Alan Mendes (alans96)**:
<https://github.com/alans96/arm_robotics>. O Capture_EMG_Data foi publicado sob
Apache-2.0 e credita o código a "Caio Lima e Alan Mendes".

**Situação:** o repositório `alans96/arm_robotics` não tem arquivo de licença
(conferido em 2026-09-25). O relicenciamento dessa parte para MIT depende da
concordância do Alan Mendes; até lá, considere-a sob os termos do
Capture_EMG_Data (Apache-2.0).

## Código do próprio autor publicado antes sob Apache-2.0

`Train_Myo_Signals`, `Capture_EMG_Data` (exceto a parte acima) e `my_arm_def`
são do autor deste repositório, que os relicencia aqui sob MIT. A cópia literal
em `tests/legacy_reference/train_myo_signals_mod_sig_emg.py` está nesse caso.
