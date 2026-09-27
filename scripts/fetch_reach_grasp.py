#!/usr/bin/env python3
"""Download the Reach&Grasp Vicon trials (elbow angle) for the movement replay.

Reach&Grasp: Di Domenico et al., "Reach&Grasp: a multimodal dataset of the
whole upper-limb during simple and complex movements", Scientific Data 12, 233
(2025). Data on IIT Dataverse, DOI 10.48557/L6OWMM, version 1.0, licence
CC BY 4.0 (cite the dataset and the article when using it).

Only the Vicon kinematics are fetched (``acq-vicon``: CSV + channels TSV +
JSON, ~0.3 GB for the 10 subjects x 16 tasks; one trial is ~1-2 MB). The sEMG
is not needed to replay a movement. The same download, with the sEMG and a
full inspection, is ``scripts/fetch_dataset.py`` of ``semg-digital-twins``;
the files described there (``docs/DATA_CONTRACT_REACH_GRASP.md``) are the
ones used here, with the same folder layout.

Every file is checked against the MD5 published by Dataverse; files already
present and correct are skipped. Standard library only.

    scripts/fetch_reach_grasp.py                           # all subjects and tasks
    scripts/fetch_reach_grasp.py --subjects 1 --tasks ReaCyl EatFruit
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
import urllib.request
from pathlib import Path

SERVER = "https://dataverse.iit.it"
DOI = "doi:10.48557/L6OWMM"
VERSION = "1.0"  # pinned: adopting a new Dataverse version is a deliberate change
REPO = Path(__file__).resolve().parents[1]


def retrying(what: str, action, retries: int = 4):
    """``action()``, tried again after 2, 4, 8 and 16 s when it raises.

    Dataverse is a remote server: one timeout (seen in CI while listing the
    files) should not end the download.
    """
    for attempt in range(retries + 1):
        try:
            return action()
        except Exception as exc:  # network errors and bad checksums are retried
            if attempt == retries:
                raise
            wait = 2 ** (attempt + 1)
            print(f"  retry {attempt + 1} for {what} in {wait}s ({exc})", file=sys.stderr)
            time.sleep(wait)
    raise AssertionError("unreachable")


def list_vicon_files(retries: int = 4) -> list[dict]:
    """Vicon file records of the pinned version: id, path, size, md5."""
    url = f"{SERVER}/api/datasets/:persistentId/versions/{VERSION}?persistentId={DOI}"

    def get() -> dict:
        with urllib.request.urlopen(url, timeout=120) as r:  # noqa: S310 (fixed https host)
            return json.loads(r.read())["data"]

    data = retrying("the file list", get, retries)
    # the version check stays outside the retries: a wrong version stays wrong
    got = f"{data['versionNumber']}.{data['versionMinorNumber']}"
    if got != VERSION:
        raise RuntimeError(f"Dataverse returned version {got}, expected {VERSION}")
    out = []
    for f in data["files"]:
        df = f["dataFile"]
        if "_acq-vicon_" not in df["filename"]:
            continue
        out.append(
            {
                "id": df["id"],
                "path": f"{f.get('directoryLabel', '')}/{df['filename']}".lstrip("/"),
                "size": df["filesize"],
                "md5": df["checksum"]["value"],
            }
        )
    return out


def md5_of(path: Path) -> str:
    h = hashlib.md5()  # noqa: S324 (integrity check against the publisher's MD5)
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def md5_ok(got: str, published: str) -> bool:
    """Equal, or equal on every legible digit if the published MD5 is masked.

    One published checksum of the dataset (an sEMG sidecar, not a Vicon file)
    arrived with characters replaced by 'X' (semg-digital-twins data contract,
    section 2); such a value is compared on the digits that are there.
    """
    if got == published:
        return True
    if published.strip("0123456789abcdef") == "":
        return False
    return len(got) == len(published) and all(
        p == g for p, g in zip(published, got, strict=True) if p in "0123456789abcdef"
    )


def fetch(f: dict, root: Path, retries: int = 4) -> bool:
    """Download one file and check it; False if it was already there."""
    dest = root / f["path"]
    if dest.exists() and dest.stat().st_size == f["size"] and md5_ok(md5_of(dest), f["md5"]):
        return False
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".part")
    url = f"{SERVER}/api/access/datafile/{f['id']}?format=original"

    def get() -> bool:
        with urllib.request.urlopen(url, timeout=300) as r, open(tmp, "wb") as out:  # noqa: S310
            while chunk := r.read(1 << 20):
                out.write(chunk)
        got = md5_of(tmp)
        if not md5_ok(got, f["md5"]):
            raise RuntimeError(f"MD5 mismatch for {f['path']}: {got} != {f['md5']}")
        tmp.replace(dest)
        return True

    return retrying(f["path"], get, retries)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--out", default=str(REPO / "data" / "reach_grasp"))
    p.add_argument("--subjects", nargs="+", type=int, help="1 to 10 (default: all)")
    p.add_argument("--tasks", nargs="+", help="e.g. ReaCyl EatFruit (default: all 16)")
    args = p.parse_args(argv)

    files = list_vicon_files()
    if args.subjects:
        prefixes = tuple(f"sub-{s:02d}_" for s in args.subjects)
        files = [f for f in files if f["path"].rsplit("/", 1)[-1].startswith(prefixes)]
    if args.tasks:
        files = [f for f in files if any(f"_task-{t}_" in f["path"] for t in args.tasks)]
    if not files:
        print("nothing matches --subjects/--tasks", file=sys.stderr)
        return 1
    root = Path(args.out)
    total = sum(f["size"] for f in files)
    print(f"Reach&Grasp {DOI} v{VERSION}, Vicon: {len(files)} files, {total / 1e6:.0f} MB")
    print(f"  -> {root}")
    new = sum(fetch(f, root) for f in files)
    print(f"ok: {len(files)} files checked by MD5 ({new} downloaded, {len(files) - new} present)")
    print("CC BY 4.0: cite Di Domenico et al., Sci Data 12, 233 (2025) and the dataset DOI.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
