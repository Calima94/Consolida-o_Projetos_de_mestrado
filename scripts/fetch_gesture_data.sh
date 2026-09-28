#!/usr/bin/env bash
# Download the hand-gesture sEMG data used in the course project that followed
# the thesis ("Hand Gesture Classification via LSTM Neural Networks", PPGINF
# UFABC) and write it as one CSV the training reads: data/gestos_1khz.csv.
#
# The data is the set of Toro-Ossaba et al., "LSTM Recurrent Neural Network
# for Hand Gesture Recognition Using EMG Signals", Applied Sciences 12(19),
# 9700, 2022, https://doi.org/10.3390/app12199700 (as the course report says;
# not compared with a copy from the authors): 8 participants x 5 gestures,
# 4-channel armband at 1 kHz, each gesture held for ~20 s. It comes from the
# course's Google Drive folder
# ("EMG hand gestures dataset", one folder per subject with 0.txt..4.txt,
# tab-separated, no header), pinned by file id and SHA-256.
#
# Output columns: time (s, restarting at 0 for every file, like the course's
# convert_files.py), channel1..channel4, participante (1..8) and position
# (gesto_0..gesto_4). The label is text on purpose: the training drops label
# 0, which in the thesis capture tool means "outside every category". The
# gesture names are not in the data or the notebooks, so the numbers stay.
#
# The same rows, stacked without the participant, are Raw_EMG_Data/
# arquivo_empilhado.csv of github.com/Calima94/DEEP_LEARNING_MYO_SIGNALS
# (checked: equal counts per gesture).
set -euo pipefail

DEST="$(cd "$(dirname "$0")/.." && pwd)/data"
OUT="$DEST/gestos_1khz.csv"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
mkdir -p "$DEST"

# participant gesture drive-id sha256
FILES=(
  "1 0 1Z_azkzW6Lo3H6AiqsQqZuhgTklPSDl-S b959a02c4b5d11a746d026e6284b2eb17423c12e56865ca956a68bacb5830f2e"
  "1 1 1wfU4P-P2LxIx6aVZJRXt0g_a_9bRUAZI 24cfc56f117d75fcb5dce3a37d73ab1ebc8ff89d45825d61677e8741207ecadc"
  "1 2 16I7QzD0ditzqimAC8xj8YXnG1vJVv6Lc 76c8f5d7a198b664df2584f464881e3aefa338b85cce3e5046106149412c2a90"
  "1 3 1UbdSaFpTKvcnJ5d0sVIPQMi1LpXKIvNT 3738ce2217e47aeb05ce56a0e81c2adc908362bbea480680ea486ec8019ee742"
  "1 4 13MogWyIT5IdP1ta4nzq3Npz843uDjTpF 3c098943dd578d1becea284bd44b5986a4cef56296da6e1fb0dc9f60466b6449"
  "2 0 1djCQ4TzQ33N0JXiboEPYBJtbzAM01gY5 cc32f7e97a6439d47a0cb6725c665a26632bf1de4e021afeab940cf7974dc495"
  "2 1 1g1t0QsjzoXIU3GoJ6zACR6youBlsV4zp cc325ad184f651fb0a05398506796fd74cb6fa9dd5b1f59c3c289c36fe3674ff"
  "2 2 1svl9cuK4zBgcTp3AJfod8iNYAP32QwsE f8fc49dc9c7a68a989614cc8f78ba0809ae2facd9e498f6ba2f97e27a4279b9b"
  "2 3 1DxA3Y7pgDYigHPEFCF1j9-4DL-72BJIy 6f7af79cc41da02e9ccc972b24f0a1862a0b26baa570de8232260ba87854d1e6"
  "2 4 1rtmWpR2Y7Ogfykt2F17O27MfWn-tt-h_ 0318a7b2f88e2851da84e0de5ea39007a6082f10a4f3bcfc1ba4c0005814f685"
  "3 0 1ANrHZ3Zg-2XGfFy__gJKaxQzcfmGbQZ9 f93d68a04f43ec8d9f02d9bd10d77d5cb23c81096b0509702b7292a0ee3b3888"
  "3 1 1JJDRFBNk8vZLPtSvN_HYroV7CnUnIppE 618380cca43f52a42db09b67e2c5f5723b01b07f1265a84c628eae65a6c34514"
  "3 2 1rCJxXdagvlcTjPWKDAslrcAWlZgUS-wx c4b9eb741c636071740fef4edad27f41f99b5704ab827c54e3f3d836a70f52a1"
  "3 3 1lPKzH4akFBGOI-OPKGX-B2Mpl5YCs-Tg 7b1ae1f96dc6ad2301e5ceea3ba90add3c077cb58d0a6465e86e028dee119b4d"
  "3 4 1de1LLP1s1GJQhPZ_CCyVJAAndB7UxKem 910a19d22ebf728f915c581c30406468069df48fff84e7633d021e75ecbe9188"
  "4 0 1TiH6LI_0FwOo8N0CJzSTJN_1f3EZzegZ 0085a73a7856a2acecfb9b07814e0d218c1ff99ce424b144374a8626f0a23ef2"
  "4 1 1H8CrOU9GZWycGOHQRz-EuucIKALLQ91p 31260e84768b8784a2883bbe281b1aa8d269c9bcc0cee82236eef9bc3ba572d1"
  "4 2 1ScpPdzFSNu4PHcOYGwdeSHfl6tzzgSzl 5d71ca4174cfaefecf989084300678c3276515d48162cf3c1e439913acd8ecbd"
  "4 3 1Pr3qJ4ElBTVJLWh-sojE3G6ZNK3jSwJo 01b96c1e025cf21294192e8e5ef1bbf01e0095e9edb30e1879f0cca867bbd4b0"
  "4 4 1qMUH8yD21X52usdfNQbTLmVdAc2lbG0n 27b504079ca7119fa8c6520ba5df2423b81d6b3785b1cfdd131348243f2f140a"
  "5 0 1hnPlR7qHWn2KED3_8D4SCMidSkz6mtwH 77c70fbb3c28bc5e73fcf29c211df81e73839416e96648a8ddf0c49d61088d6c"
  "5 1 127c7BdLR-6w5UvW7TSmq_htass0L8NQX c9aaba230df886829adba3e705687a4676b3332f290f48bf4258385741e6e9bd"
  "5 2 1KEAYZVD8WHtTl7qsHBSPNGWG6EEwSk3a 2ac25aa2cd36bfe1a39fbc25292663e7b2018cbb56aa7843db9a7113d907753a"
  "5 3 11QRj2tDl-Nbu3novy1MQDPmUTdrRS-WZ 654d75ece5515df445740e4abbf396327df51bdd8e4c74a98061b123d1edb0a6"
  "5 4 16UxrqQUbJon8grcr5ZddzHgFVdhjtA7s ec2501a03eb7a31c5deeb0410145574964d942294c1092f1b7722d2fa0b8e1ca"
  "6 0 1DZeM9ftC6yeUXwWouDkBi_qg-PPLOaSv d931d7e8604337af4b846b679badaa843f79cf658edc51cc710127bf09a6fa00"
  "6 1 1MGD4cokkL6FqXyE-D_kU7oFrE1vOuShW 13aedfbf5bd94f50ed93778f41fc29b171feffa559b617106c7d5f67453d3762"
  "6 2 1ZyizlO21PMu_GCuDG1FdqXg9Ztz6bDMF 44312b71ace5353ff5e284b88d9cbb2c9b3c314269b820edd7ee840887299985"
  "6 3 11TWnC1v4zyDluEqxNXARdJFntPwJHHSZ 4ec64f7c2323a337beac3281ec0ac7e16764eb33be3c986e9dc129e1f549a27a"
  "6 4 1GfC6Iejojiq913M5-1DBPOM3cJ6GAn9w 51538d94d5d404a40fc89b2bf48e248e3ab33cf7ae9379284e8126fee884f184"
  "7 0 1pXA09IH45EB6rz153K8tTHJzkm21LSNV fe9838a7f3d96c6b95fbcb789823e2175a835a6ac42849150224d531151bb973"
  "7 1 1Kq27Xtgz6AJ4BtHEdk41bTIz_QW268Uv 7c52360fcbe3d34dfccc7f48a5b7c0ac78192f78d195fc2cfe03df55b8890cd8"
  "7 2 1q567_Yybeqwiqhvpnve9JCEedw90jsCF 5e146692d0c81af1013342aa8d95bb943a3a99322ad21a598a3998486283ad48"
  "7 3 12hZ7U7zRo4-WeH_tjyJAewy-sFxV0PTi b6f9127bcf578fc84a4bbca0fc9faa10f93dfbb968b50082069e02e4a36baea2"
  "7 4 1I1T6KgS651ksRnnZIyHTStaynQW51lbs 89ba9be13de11a3a008b01fc3162d4e45d6b11f90e7544b9388e73f66272db10"
  "8 0 1ka_xzV5jqkboE3Kj7Vifh9rYObP6wrQK b07f34a91cdbfaf7ca129c6149754893f05de829639d41805cac9345960d8e21"
  "8 1 1NvGg6RjJQfvXWOL5MgJ5RX3vCGXU6vLX 744ac2e1e071d5efb4266f56a07ea2c5969b6494a7ab6230ac3149dc16e8047a"
  "8 2 1k4EHP90DNJl53dKHZBw3YtnWrAHHrbp3 0dae48fc956a86c085db068f89cba962a394b1e3dd1051a88077dd3461b3fbc4"
  "8 3 1Hxs56L_ilGpD8-wCAA_bA_TMNsT-BqiI 51d566ddc6efd012248d96d355dc1b1fa05a3d7c02cef2e4a6411bf7eb851425"
  "8 4 1nOET1FhteTCs-HjZuihnMC71JGc18CRh 1c2130dca728a7b74247eee5ee9a1825bd8c47c4579a6d6d64e6d4f468ec6f02"
)

for linha in "${FILES[@]}"; do
  read -r p g id sha <<<"$linha"
  arquivo="$TMP/s${p}_g${g}.txt"
  curl -fsSL --retry 3 "https://drive.usercontent.google.com/download?id=${id}&export=download" -o "$arquivo"
  echo "${sha}  ${arquivo}" | sha256sum -c --quiet -
  echo "ok participante ${p}, gesto ${g}"
done

# Stack them as the training reads them (participant by participant).
python3 - "$TMP" "$OUT.tmp" <<'PY'
import sys
from pathlib import Path

origem, destino = Path(sys.argv[1]), Path(sys.argv[2])
with open(destino, "w", newline="\n") as out:
    out.write("time,channel1,channel2,channel3,channel4,participante,position\n")
    for p in range(1, 9):
        for g in range(5):
            valores = (origem / f"s{p}_g{g}.txt").read_text().split()  # 4 per row
            if len(valores) % 4:
                sys.exit(f"s{p}_g{g}.txt: {len(valores)} valores, não múltiplo de 4 canais")
            for i in range(0, len(valores), 4):
                t = f"{i // 4 / 1000:.3f}"
                out.write(",".join([t, *valores[i : i + 4], str(p), f"gesto_{g}"]) + "\n")
PY
mv "$OUT.tmp" "$OUT"
echo "${OUT} ($(wc -l < "$OUT") linhas, 8 participantes x 5 gestos, 1000 Hz, 4 canais)"
