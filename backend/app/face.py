from __future__ import annotations

from pathlib import Path


class FaceVerifier:
    def __init__(self) -> None:
        self.available = False
        self.reason = "DeepFace not installed; using filename fallback for development."
        try:
            from deepface import DeepFace  # type: ignore

            self._deepface = DeepFace
            self.available = True
            self.reason = ""
        except Exception:
            self._deepface = None

    def warm(self) -> None:
        if self.available and self._deepface is not None:
            try:
                self._deepface.build_model("Facenet")
            except Exception:
                self.available = False
                self.reason = "DeepFace warm-up failed; using development fallback."

    def verify(self, probe_path: Path, reference_path: Path) -> tuple[bool, float, str]:
        if self.available and self._deepface is not None:
            result = self._deepface.verify(
                img1_path=str(probe_path),
                img2_path=str(reference_path),
                model_name="Facenet",
                detector_backend="opencv",
                enforce_detection=False,
            )
            distance = float(result.get("distance", 1))
            score = max(0.0, min(100.0, (1 - distance) * 100))
            return bool(result.get("verified")), score, "deepface"
        matched = probe_path.stem == reference_path.stem
        score = 100.0 if matched else 0.0
        return matched, score, "fallback"
