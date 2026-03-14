import numpy as np


class SimpleTracker:
    def __init__(self, max_age=5, min_hits=2, iou_threshold=0.3, alpha=0.7):
        """
        Lightweight tracker to stabilize CV detections.

        Args:
            max_age: Frames to keep a track alive after losing it (anti-flicker).
            min_hits: Consecutive frames before confirming a new detection.
            iou_threshold: Minimum overlap to match detections between frames.
            alpha: EMA smoothing factor (0.1 = very smooth/laggy, 0.9 = responsive/jittery).
        """
        self.max_age = max_age
        self.min_hits = min_hits
        self.iou_threshold = iou_threshold
        self.alpha = alpha
        self.tracks = (
            []
        )  # Each track: {'id': int, 'bbox': [y1, x1, y2, x2], 'hits': int, 'age': int, 'label': str}
        self.track_count = 0

    @staticmethod
    def calculate_iou(boxA, boxB):
        # box format: [ymin, xmin, ymax, xmax]
        yA = max(boxA[0], boxB[0])
        xA = max(boxA[1], boxB[1])
        yB = min(boxA[2], boxB[2])
        xB = min(boxA[3], boxB[3])

        interArea = max(0, xB - xA + 1) * max(0, yB - yA + 1)
        boxAArea = (boxA[2] - boxA[0] + 1) * (boxA[3] - boxA[1] + 1)
        boxBArea = (boxB[2] - boxB[0] + 1) * (boxB[3] - boxB[1] + 1)

        iou = interArea / float(boxAArea + boxBArea - interArea)
        return iou

    def update(self, detections):
        """
        detections: list of dicts like {'bbox': [y1,x1,y2,x2], 'label': '...'}
        returns: list of stabilized tracks
        """
        # 1. Update existing tracks age
        for track in self.tracks:
            track["age"] += 1

        matched_detections = [False] * len(detections)
        matched_tracks = [False] * len(self.tracks)

        # 2. Match detections to tracks using IoU
        for i, track in enumerate(self.tracks):
            best_iou = 0
            best_det_idx = -1

            for j, det in enumerate(detections):
                if matched_detections[j]:
                    continue

                # Use track label to ensure we don't match a table with a chair
                if det.get("nombre") != track.get("label"):
                    continue

                iou = self.calculate_iou(track["bbox"], det["bbox"])
                if iou > best_iou:
                    best_iou = iou
                    best_det_idx = j

            if best_iou > self.iou_threshold:
                matched_tracks[i] = True
                matched_detections[best_det_idx] = True

                # Apply EMA smoothing to bbox
                new_bbox = detections[best_det_idx]["bbox"]
                old_bbox = track["bbox"]
                smoothed_bbox = [
                    int(self.alpha * new_bbox[k] + (1 - self.alpha) * old_bbox[k])
                    for k in range(4)
                ]

                track["bbox"] = smoothed_bbox
                track["hits"] += 1
                track["age"] = 0  # Reset age since it was matched
                # Update other metadata if provided
                track["metadata"] = detections[best_det_idx].get("metadata", {})
                track["confianza"] = detections[best_det_idx].get("confianza", 0.8)

        # 3. Create new tracks for unmatched detections
        for j, matched in enumerate(matched_detections):
            if not matched:
                det = detections[j]
                self.track_count += 1
                self.tracks.append(
                    {
                        "id": self.track_count,
                        "bbox": det["bbox"],
                        "label": det.get("nombre", "Objeto"),
                        "hits": 1,
                        "age": 0,
                        "confianza": det.get("confianza", 0.8),
                        "metadata": det.get("metadata", {}),
                    }
                )

        # 4. Filter out old tracks
        self.tracks = [t for t in self.tracks if t["age"] <= self.max_age]

        # 5. Return confirmed tracks (those with enough hits)
        return [t for t in self.tracks if t["hits"] >= self.min_hits]
