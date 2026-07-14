import shutil
import subprocess
import sys
from pathlib import Path

from huggingface_hub import snapshot_download

RAW_DIR = Path(__file__).parent / "raw"

HF_DATASETS = [
    "BothBosu/scam-dialogue",
    "BothBosu/single-agent-scam-conversations",
    "BothBosu/multi-agent-scam-conversation",
    "BothBosu/Scammer-Conversation",
    "FredZhang7/all-scam-spam",
]

KAGGLE_DATASETS = [
    "narayanyadav/fraud-call-india-dataset",
    "teeconnie/scam-and-non-scam-call-conversation-dataset",
]

NCSU_REPO_URL = "https://github.com/wspr-ncsu/robocall-audio-dataset.git"


def download_hf_datasets():
    target_root = RAW_DIR / "huggingface"
    target_root.mkdir(parents=True, exist_ok=True)
    for repo_id in HF_DATASETS:
        target = target_root / repo_id.replace("/", "__")
        if target.exists() and any(target.iterdir()):
            print(f"[hf] skip {repo_id}, already at {target}")
            continue
        print(f"[hf] downloading {repo_id}")
        try:
            snapshot_download(repo_id=repo_id, repo_type="dataset", local_dir=str(target))
            print(f"[hf] done {repo_id}")
        except Exception as exc:
            print(f"[hf] FAILED {repo_id}: {exc}")


def download_kaggle_datasets():
    target_root = RAW_DIR / "kaggle"
    target_root.mkdir(parents=True, exist_ok=True)
    try:
        import kagglehub
    except ImportError:
        print("[kaggle] kagglehub not installed, skipping")
        return

    for handle in KAGGLE_DATASETS:
        dest = target_root / handle.replace("/", "__")
        if dest.exists() and any(dest.iterdir()):
            print(f"[kaggle] skip {handle}, already at {dest}")
            continue
        print(f"[kaggle] downloading {handle}")
        try:
            cache_path = Path(kagglehub.dataset_download(handle))
            shutil.copytree(cache_path, dest, dirs_exist_ok=True)
            print(f"[kaggle] done {handle} -> {dest}")
        except Exception as exc:
            print(f"[kaggle] FAILED {handle}: {exc}")
            print(
                "[kaggle] set up ~/.kaggle/kaggle.json or KAGGLE_USERNAME/KAGGLE_KEY "
                "env vars from https://www.kaggle.com/settings then rerun this script"
            )


def download_ncsu_repo():
    target = RAW_DIR / "ncsu-robocall-audio-dataset"
    if target.exists():
        print(f"[ncsu] skip, already at {target}")
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    print(f"[ncsu] cloning {NCSU_REPO_URL}")
    result = subprocess.run(
        ["git", "clone", "--depth", "1", NCSU_REPO_URL, str(target)],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(f"[ncsu] FAILED: {result.stderr}")
    else:
        print("[ncsu] done")


def main():
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    download_hf_datasets()
    download_kaggle_datasets()
    download_ncsu_repo()


if __name__ == "__main__":
    sys.exit(main())
