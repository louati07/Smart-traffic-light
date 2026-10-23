"""Dataset Merger, Class Remapper, and Deduplication Tool.

Contract (PLAN.md Section 7.1):
Unifies multiple source datasets into 4 standard classes:
0: ambulance
1: fire_truck
2: police_car
3: vehicle
Applies file-hash deduplication and fixed 80/10/10 train/val/test seeded split.
Generates data.yaml.
"""

import argparse
import hashlib
import random
import shutil
from pathlib import Path

import yaml

TARGET_CLASSES = ["ambulance", "fire_truck", "police_car", "vehicle"]

CLASS_SYNONYMS = {
    "ambulance": 0,
    "firetruck": 1,
    "fire_truck": 1,
    "fire truck": 1,
    "police": 2,
    "police_car": 2,
    "police car": 2,
    "car": 3,
    "truck": 3,
    "vehicle": 3,
    "normal vehicle": 3,
    "bus": 3,
}


def compute_file_hash(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def load_source_class_map(src_dir: Path) -> dict[int, int | None]:
    """Find data.yaml in or near src_dir and map source class_id -> target_class_id."""
    yaml_candidates = list(src_dir.glob("data.yaml")) + list(src_dir.glob("*.yaml"))
    if not yaml_candidates:
        # Search one level up if src_dir is a subfolder like train/
        yaml_candidates = list(src_dir.parent.glob("data.yaml"))

    if not yaml_candidates:
        print(f"Warning: No data.yaml found for {src_dir}. Assuming 1:1 default mapping.")
        return {}

    with open(yaml_candidates[0], "r", encoding="utf-8") as f:
        meta = yaml.safe_load(f)

    raw_names = meta.get("names", {})
    if isinstance(raw_names, list):
        src_names = {i: name for i, name in enumerate(raw_names)}
    elif isinstance(raw_names, dict):
        src_names = {int(k): v for k, v in raw_names.items()}
    else:
        src_names = {}

    mapping: dict[int, int | None] = {}
    for src_id, name in src_names.items():
        norm_name = str(name).strip().lower().replace("-", "_")
        target_id = CLASS_SYNONYMS.get(norm_name)
        mapping[src_id] = target_id
        if target_id is not None:
            print(f"  [{src_dir.name}] Class {src_id} '{name}' -> target {target_id} ({TARGET_CLASSES[target_id]})")
        else:
            print(f"  [{src_dir.name}] Class {src_id} '{name}' -> DROPPED (unmapped)")

    return mapping


def remap_and_write_label(src_lbl: Path, dest_lbl: Path, class_map: dict[int, int | None]) -> bool:
    """Read src_lbl, remap class IDs, write to dest_lbl. Returns True if any valid boxes remain."""
    new_lines = []
    with open(src_lbl, "r", encoding="utf-8") as f:
        for line in f:
            parts = line.strip().split()
            if not parts:
                continue
            src_cls_id = int(parts[0])
            if class_map:
                target_cls_id = class_map.get(src_cls_id)
            else:
                target_cls_id = src_cls_id if src_cls_id < len(TARGET_CLASSES) else None

            if target_cls_id is not None:
                new_line = f"{target_cls_id} " + " ".join(parts[1:]) + "\n"
                new_lines.append(new_line)

    dest_lbl.parent.mkdir(parents=True, exist_ok=True)
    with open(dest_lbl, "w", encoding="utf-8") as f:
        f.writelines(new_lines)
    return len(new_lines) > 0


def merge_datasets(source_dirs: list[Path], output_dir: Path, seed: int = 42) -> None:
    random.seed(seed)
    seen_hashes: set[str] = set()

    for split in ["train", "val", "test"]:
        (output_dir / "images" / split).mkdir(parents=True, exist_ok=True)
        (output_dir / "labels" / split).mkdir(parents=True, exist_ok=True)

    image_label_pairs: list[tuple[Path, Path, dict[int, int | None]]] = []

    for src in source_dirs:
        if not src.exists():
            print(f"Source dir not found: {src}")
            continue
        print(f"Processing source: {src}")
        class_map = load_source_class_map(src)
        for img_ext in ["*.jpg", "*.jpeg", "*.png"]:
            for img_path in src.rglob(img_ext):
                lbl_path = img_path.with_suffix(".txt")
                if not lbl_path.exists():
                    # Check labels/ subdirectory sibling
                    alt_lbl = img_path.parents[1] / "labels" / f"{img_path.stem}.txt"
                    if alt_lbl.exists():
                        lbl_path = alt_lbl
                    else:
                        continue
                file_hash = compute_file_hash(img_path)
                if file_hash in seen_hashes:
                    continue
                seen_hashes.add(file_hash)
                image_label_pairs.append((img_path, lbl_path, class_map))

    print(f"Discovered {len(image_label_pairs)} unique labeled image pairs across all sources.")
    random.shuffle(image_label_pairs)

    n_total = len(image_label_pairs)
    if n_total == 0:
        print("Warning: No image-label pairs found to merge.")
        return

    n_train = int(0.80 * n_total)
    n_val = int(0.10 * n_total)

    splits = {
        "train": image_label_pairs[:n_train],
        "val": image_label_pairs[n_train : n_train + n_val],
        "test": image_label_pairs[n_train + n_val :],
    }

    for split_name, items in splits.items():
        for img_path, lbl_path, class_map in items:
            dest_img = output_dir / "images" / split_name / img_path.name
            dest_lbl = output_dir / "labels" / split_name / f"{img_path.stem}.txt"
            shutil.copy2(img_path, dest_img)
            remap_and_write_label(lbl_path, dest_lbl, class_map)

    # Write data.yaml
    data_yaml_content = {
        "path": str(output_dir.resolve()).replace("\\", "/"),
        "train": "images/train",
        "val": "images/val",
        "test": "images/test",
        "names": {i: name for i, name in enumerate(TARGET_CLASSES)},
    }

    yaml_path = output_dir / "data.yaml"
    with open(yaml_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(data_yaml_content, f, sort_keys=False)

    print(f"Successfully generated merged dataset at {output_dir}")
    print(f"data.yaml written to {yaml_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--sources", nargs="+", default=["data/raw_datasets"])
    parser.add_argument("--output", default="data/processed_yolo")
    args = parser.parse_args()

    merge_datasets([Path(p) for p in args.sources], Path(args.output))
