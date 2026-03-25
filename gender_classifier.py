import torch
import torch.nn as nn
from torchvision import transforms, models
from PIL import Image
import cv2


class GenderClassifier:
    """
    MobileNetV3-Small binary classifier.
    All crops for a frame are batched into one GPU forward pass.
    Runs on a dedicated CUDA stream so it does not block YOLO's default stream.
    """

    CLASSES = ["F", "M"]

    def __init__(self, weights_path, device=None):
        self.device   = device or torch.device(
            "cuda" if torch.cuda.is_available() else "cpu"
        )
        self.use_fp16 = self.device.type == "cuda"

        # Dedicated CUDA stream — GPU work here overlaps with YOLO's stream
        self.stream = (
            torch.cuda.Stream(device=self.device)
            if self.device.type == "cuda"
            else None
        )

        # Build model and load weights
        self.model = models.mobilenet_v3_small()
        in_features = self.model.classifier[3].in_features
        self.model.classifier[3] = nn.Linear(in_features, len(self.CLASSES))

        # weights_only=True: safe loading, no arbitrary code execution
        state_dict = torch.load(
            weights_path, map_location=self.device, weights_only=True
        )
        self.model.load_state_dict(state_dict)
        self.model.to(self.device)
        if self.use_fp16:
            self.model.half()
        self.model.eval()

        self.transform = transforms.Compose([
            transforms.Resize((224, 224)),
            transforms.ToTensor(),
            transforms.Normalize(
                mean=[0.485, 0.456, 0.406],
                std =[0.229, 0.224, 0.225],
            ),
        ])

    def _crop_to_tensor(self, frame, box):
        """Crop one bounding box from the frame and return a float32 tensor, or None."""
        x1, y1, x2, y2 = map(int, box)
        x1 = max(0, x1);  y1 = max(0, y1)
        x2 = min(frame.shape[1], x2);  y2 = min(frame.shape[0], y2)
        crop = frame[y1:y2, x1:x2]
        if crop.size == 0 or crop.shape[0] < 2 or crop.shape[1] < 2:
            return None
        return self.transform(
            Image.fromarray(cv2.cvtColor(crop, cv2.COLOR_BGR2RGB))
        )

    def predict(self, frame, boxes):
        """
        Run a single batched forward pass for all boxes.

        Parameters
        ----------
        frame : np.ndarray  full BGR frame
        boxes : (N, 4)      xyxy pixel boxes

        Returns
        -------
        list[dict]  one {"label": str, "confidence": float} per box,
                    same order as input; invalid crops return label="?"
        """
        if len(boxes) == 0:
            return []

        # Build tensor list — track which original indices are valid
        tensors, valid = [], []
        for i, box in enumerate(boxes):
            t = self._crop_to_tensor(frame, box)
            if t is not None:
                valid.append(i)
                tensors.append(t)

        # Pre-fill with fallback for invalid crops (list comprehension = independent dicts)
        results = [{"label": "?", "confidence": 0.0} for _ in range(len(boxes))]
        if not tensors:
            return results

        # Single forward pass on dedicated CUDA stream
        ctx = (
            torch.cuda.stream(self.stream)
            if self.stream is not None
            else torch.no_grad()
        )
        with ctx:
            with torch.no_grad():
                batch = torch.stack(tensors).to(self.device)
                if self.use_fp16:
                    batch = batch.half()
                logits = self.model(batch)
                probs  = torch.softmax(logits.float(), dim=1)
                confs, preds = torch.max(probs, dim=1)

        # Synchronise before reading results back to CPU
        if self.stream is not None:
            self.stream.synchronize()

        for out_i, orig_i in enumerate(valid):
            results[orig_i] = {
                "label":      self.CLASSES[preds[out_i].item()],
                "confidence": float(confs[out_i].item()),
            }
        return results