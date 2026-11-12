"""Real local Transformers adapters. No network or legacy detector fallback."""
import gc
import cv2
import numpy as np
import torch

from .config import POLICY, PROMPTS


def release_model(adapter):
    adapter.model.to("cpu")
    del adapter.model
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()


class GroundingDetector:
    def __init__(self, path, device):
        from transformers import AutoModelForZeroShotObjectDetection, AutoProcessor
        self.device = device
        self.processor = AutoProcessor.from_pretrained(str(path), local_files_only=True)
        self.model = AutoModelForZeroShotObjectDetection.from_pretrained(str(path), local_files_only=True).eval().to(device)

    @torch.inference_mode()
    def detect(self, image):
        rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        inputs = self.processor(images=rgb, text=POLICY["detectionPrompt"], return_tensors="pt").to(self.device)
        outputs = self.model(**inputs)
        result = self.processor.post_process_grounded_object_detection(outputs, inputs.input_ids,
            threshold=POLICY["boxThreshold"], text_threshold=POLICY["textThreshold"], target_sizes=[image.shape[:2]])[0]
        candidates = []
        for box, score, label in zip(result["boxes"].cpu().tolist(), result["scores"].cpu().tolist(), result["text_labels"]):
            box = [max(0., min(float(image.shape[1 if i % 2 == 0 else 0]), v)) for i, v in enumerate(box)]
            if box[2] > box[0] and box[3] > box[1]:
                candidates.append(dict(box=box, score=score, label=label))
        # Suppress duplicate same-label boxes, retaining distinct plates/objects.
        from .geometry import iou
        selected = []
        for candidate in sorted(candidates, key=lambda c: c["score"], reverse=True):
            if not any(candidate["label"] == c["label"] and iou(candidate["box"], c["box"]) > .7 for c in selected):
                selected.append(candidate)
        return selected


class ExerciseClassifier:
    def __init__(self, path, device):
        from transformers import XCLIPModel, XCLIPProcessor
        self.device = device
        self.processor = XCLIPProcessor.from_pretrained(str(path), local_files_only=True)
        self.model = XCLIPModel.from_pretrained(str(path), local_files_only=True).eval().to(device)
        self.num_frames = int(self.model.config.vision_config.num_frames)
        self.image_size = int(self.model.config.vision_config.image_size)
        self.texts = [text for prompts in PROMPTS.values() for text in prompts]

    @torch.inference_mode()
    def classify(self, frames):
        if len(frames) != self.num_frames:
            raise ValueError(f"X-CLIP requires {self.num_frames} temporal samples")
        # Transformers 4.57 XCLIPProcessor wraps VideoMAEImageProcessor through
        # ProcessorMixin's images argument. `videos` is silently ignored there.
        inputs = self.processor(text=self.texts, images=list(frames), return_tensors="pt", padding=True).to(self.device)
        logits = self.model(**inputs).logits_per_video[0].float().cpu().numpy()
        offset = 0
        scores = {}
        for label, prompts in PROMPTS.items():
            scores[label] = float(np.mean(logits[offset:offset+len(prompts)]))
            offset += len(prompts)
        decision, score, margin = decide(scores)
        return dict(scores=scores, promptLogits=logits.tolist(), decision=decision, score=score, margin=margin)


def decide(raw_scores):
    labels = list(raw_scores)
    values = np.asarray([raw_scores[label] for label in labels], dtype=np.float64)
    weights = np.exp(values-values.max())
    weights /= weights.sum()
    ranking = np.argsort(weights)[::-1]
    score = float(weights[ranking[0]])
    margin = float(weights[ranking[0]]-weights[ranking[1]])
    label = labels[ranking[0]]
    if score < POLICY["classificationMinScore"] or margin < POLICY["classificationMinMargin"]:
        label = "Unknown"
    return label, score, margin


class SamVideoTracker:
    def __init__(self, path, device):
        from transformers import Sam2VideoModel, Sam2VideoProcessor
        self.device = device
        self.processor = Sam2VideoProcessor.from_pretrained(str(path), local_files_only=True)
        self.model = Sam2VideoModel.from_pretrained(str(path), local_files_only=True).eval().to(device)
        self.session = self.processor.init_video_session(inference_device=device,
            inference_state_device="cpu", video_storage_device="cpu", dtype=torch.float32)
        self.memory_frames = max(self.model.config.num_maskmem, self.model.config.max_object_pointers_in_encoder) + 2
        self.numeric_ids = {}

    def add(self, object_id, frame_index, size, box=None, point=None):
        numeric = self.numeric_ids.setdefault(object_id, len(self.numeric_ids)+1)
        kwargs = dict(inference_session=self.session, frame_idx=frame_index, obj_ids=numeric, original_size=size)
        if box is not None:
            kwargs["input_boxes"] = [[list(box)]]
        if point is not None:
            kwargs["input_points"] = [[[[float(point[0]), float(point[1])]]]]
            kwargs["input_labels"] = [[[1]]]
        self.processor.add_inputs_to_inference_session(**kwargs)

    @torch.inference_mode()
    def track(self, frame_index, image):
        inputs = self.processor(images=cv2.cvtColor(image, cv2.COLOR_BGR2RGB), device=self.device, return_tensors="pt")
        outputs = self.model(inference_session=self.session, frame_idx=frame_index, frame=inputs.pixel_values[0])
        masks = self.processor.post_process_masks([outputs.pred_masks], original_sizes=inputs.original_sizes, binarize=True)[0]
        result = {}
        for object_id, numeric in self.numeric_ids.items():
            index = self.session.obj_id_to_idx(numeric)
            mask = masks[index, 0].cpu().numpy().astype(bool)
            history = self.session.output_dict_per_obj[index]
            current = history["cond_frame_outputs"].get(frame_index, history["non_cond_frame_outputs"].get(frame_index))
            logits = current.get("object_score_logits") if current else None
            confidence = float(torch.sigmoid(logits.float()).mean().item()) if logits is not None else 0.0
            result[object_id] = (mask, confidence)
        self.prune(frame_index)
        return result

    def prune(self, frame_index):
        """Retain SAM's complete finite temporal receptive field, not the full film."""
        cutoff = frame_index-self.memory_frames
        if self.session.processed_frames is not None:
            for key in list(self.session.processed_frames):
                if key < frame_index:
                    del self.session.processed_frames[key]
        for index, history in self.session.output_dict_per_obj.items():
            for key in list(history["non_cond_frame_outputs"]):
                if key < cutoff:
                    del history["non_cond_frame_outputs"][key]
            # Keep the original prompt and most recent correction as anchors.
            conditions = sorted(history["cond_frame_outputs"])
            for key in conditions[1:-1]:
                del history["cond_frame_outputs"][key]
            for table in (self.session.frames_tracked_per_obj[index], self.session.point_inputs_per_obj[index],
                          self.session.mask_inputs_per_obj[index]):
                for key in list(table):
                    if key < cutoff:
                        del table[key]
