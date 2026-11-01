# YOLO Model Weights

The development workspace currently contains `best.pt`, a fine-tuned YOLO11n checkpoint for `ambulance`, `fire_truck`, `police_car`, and `vehicle` detection. The 26.6 MB checkpoint is Git-ignored, so it is **not included in a fresh clone or public upload**.

To reproduce the current inference test, obtain the checkpoint from the project owner and place it at:

```text
vision/weights/best.pt
```

Then install `vision/requirements.txt`, run `python vision/evaluate_model.py`, and review the report described in [`docs/AI_MODEL_EVALUATION.md`](../../docs/AI_MODEL_EVALUATION.md). That report distinguishes metrics stored in the checkpoint from the sampled-video inference run and does not claim an independent test-set score.

The training workflow is in [`vision/train/train_colab.ipynb`](../train/train_colab.ipynb). It starts from pretrained YOLO11n and fine-tunes it using the prepared dataset. Raw training data and labels are not committed. Do not claim the model can be independently retrained from this repository unless the dataset provenance, access, and licensing are also supplied.

Model weights are excluded from Git by design. For distribution, publish them as a separately versioned release/artifact with the training-data and model-license information, rather than committing a large binary into the source repository.
