"""Transcription and consistency-analysis services for interview recordings.

The source of truth remains the original recording media. Transcript artifacts are
read-only derived outputs, and the service must report a truthful provider error
when real speech-to-text is unavailable instead of fabricating content.
"""

from __future__ import annotations

import hashlib
import importlib.util
import os
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PLACEHOLDER_TRANSCRIPT_MARKERS = (
    "we agree on the same statement",
    "the facts match exactly",
    "browser verification transcript",
    "this is a browser verification transcript",
    "used to validate the recording workflow",
    "same statement",
)


def is_placeholder_transcript_text(transcript_text: Any) -> bool:
    if transcript_text is None:
        return False
    text = str(transcript_text).strip().lower()
    if not text:
        return False
    normalized = re.sub(r"\s+", " ", text)
    return any(marker in normalized for marker in PLACEHOLDER_TRANSCRIPT_MARKERS)


class TranscriptionProvider:
    """Base interface for audio transcription providers."""

    name = "BASE"
    engine_version = "unknown"

    @staticmethod
    def _utc_now() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _coerce_recording(recording: Any) -> dict[str, Any] | None:
        if recording is None:
            return None
        if isinstance(recording, dict):
            return dict(recording)
        if hasattr(recording, "__dict__"):
            return dict(recording.__dict__)
        return {"text": str(recording)}

    @staticmethod
    def _normalise_nested_text(value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, dict):
            for nested_key in ("text", "transcript", "content"):
                nested = value.get(nested_key)
                text = TranscriptionProvider._normalise_nested_text(nested)
                if text:
                    return text
            return ""
        text = str(value).strip()
        return text

    @staticmethod
    def _extract_text(recording: dict[str, Any] | None) -> str:
        if not recording:
            return ""
        for key in ("transcript_text", "transcript", "text"):
            value = recording.get(key)
            text = TranscriptionProvider._normalise_nested_text(value)
            if text:
                return text
        return ""

    @staticmethod
    def _extract_segments(recording: dict[str, Any] | None) -> list[dict[str, Any]]:
        if not recording:
            return []
        for key in ("segments", "transcript_segments"):
            value = recording.get(key)
            if isinstance(value, list):
                return value
        transcript = recording.get("transcript")
        if isinstance(transcript, dict):
            segments = transcript.get("segments")
            if isinstance(segments, list):
                return segments
        return []

    @staticmethod
    def _hash_file(path: str | os.PathLike[str]) -> str:
        digest = hashlib.sha256()
        with open(path, "rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def is_available(self) -> bool:
        return False

    def transcribe(self, recording: Any) -> dict[str, Any]:
        raise NotImplementedError


class WhisperXProvider(TranscriptionProvider):
    """Speech-to-text provider for WhisperX-backed processing.

    The provider is intentionally honest: if the runtime dependency stack or the
    audio file is missing, it returns a BLOCKED/FAILED status rather than a fake
    transcript value.
    """

    name = "WhisperX"
    engine_version = "whisperx-unavailable"

    @staticmethod
    def _module_available(module_name: str) -> bool:
        return importlib.util.find_spec(module_name) is not None

    @staticmethod
    def _resolve_local_backend() -> str | None:
        for module_name in ("whisperx", "whisper", "faster_whisper"):
            if WhisperXProvider._module_available(module_name):
                return module_name
        return None

    def is_available(self) -> bool:
        backend = self._resolve_local_backend()
        if backend is None:
            return False
        return shutil.which("ffmpeg") is not None or backend == "whisper"

    @staticmethod
    def _resolve_media_path(recording: dict[str, Any] | None) -> str | None:
        if not recording:
            return None

        candidates: list[str] = []
        for key in ("storage_reference", "path", "source_path", "file_path"):
            value = recording.get(key)
            if value:
                candidates.append(str(value))

        if recording.get("filename"):
            candidates.append(str(recording["filename"]))

        seen_paths: set[str] = set()
        for candidate in candidates:
            path = Path(candidate)
            if path.is_absolute():
                if path.exists() and str(path) not in seen_paths:
                    seen_paths.add(str(path))
                    return str(path)
                continue
            alternative_paths = [
                Path.cwd() / candidate,
                Path.cwd() / "instance" / "uploads" / candidate,
                Path.cwd() / "instance" / "uploads" / "recordings" / candidate,
                Path("instance") / "uploads" / candidate,
                Path("instance") / "uploads" / "recordings" / candidate,
            ]
            for alt in alternative_paths:
                if alt.exists() and str(alt) not in seen_paths:
                    seen_paths.add(str(alt))
                    return str(alt)

        target_names = {Path(candidate).name.lower() for candidate in candidates if candidate and Path(candidate).name}
        if not target_names:
            return None

        base_dirs = [
            Path.cwd() / "instance" / "uploads",
            Path.cwd() / "instance" / "uploads" / "recordings",
            Path("instance") / "uploads",
            Path("instance") / "uploads" / "recordings",
        ]
        for base in base_dirs:
            if not base.exists():
                continue
            for match in sorted(base.rglob("*.mp4")) + sorted(base.rglob("*.wav")) + sorted(base.rglob("*.m4a")) + sorted(base.rglob("*.webm")):
                if not match.is_file():
                    continue
                lower_name = match.name.lower()
                if any(lower_name == target or lower_name.endswith(target) or target.endswith(lower_name) for target in target_names):
                    return str(match)
        return None

    def transcribe(self, recording: Any) -> dict[str, Any]:
        normalized = self._coerce_recording(recording)
        if normalized is None:
            return {"status": "FAILED", "error": "No recording supplied."}

        existing_text = self._extract_text(normalized)
        if existing_text:
            if is_placeholder_transcript_text(existing_text):
                return {
                    "status": "FAILED",
                    "recording_id": normalized.get("recording_id"),
                    "case_reference": normalized.get("case_reference"),
                    "recording_type": normalized.get("recording_type"),
                    "provider": self.name,
                    "error": "Transcript text appears to be placeholder browser-validation content rather than the actual audio transcription.",
                }
            return {
                "status": "COMPLETED",
                "recording_id": normalized.get("recording_id"),
                "case_reference": normalized.get("case_reference"),
                "recording_type": normalized.get("recording_type"),
                "provided_by": self.name,
                "provider": self.name,
                "engine_version": self.engine_version,
                "transcript": {
                    "text": existing_text,
                    "segments": self._extract_segments(normalized),
                    "language": normalized.get("language") or "en",
                    "provider": self.name,
                },
                "source_hash": normalized.get("sha256_hash"),
                "metadata": {"source_file": normalized.get("storage_reference")},
            }

        if not self.is_available():
            return {
                "status": "BLOCKED",
                "recording_id": normalized.get("recording_id"),
                "case_reference": normalized.get("case_reference"),
                "recording_type": normalized.get("recording_type"),
                "provider": self.name,
                "error": "WhisperX transcription is blocked because the required model and ffmpeg runtime are not installed in this environment.",
            }

        media_path = self._resolve_media_path(normalized)
        if not media_path:
            return {
                "status": "BLOCKED",
                "recording_id": normalized.get("recording_id"),
                "case_reference": normalized.get("case_reference"),
                "recording_type": normalized.get("recording_type"),
                "provider": self.name,
                "error": "WhisperX transcription is blocked because the original media file is missing or unreadable.",
            }

        backend = self._resolve_local_backend()
        try:
            if backend == "whisperx":
                import whisperx  # type: ignore
                model = whisperx.load_model("large-v2", device="cpu", compute_type="int8")
                audio = whisperx.load_audio(media_path)
                result = model.transcribe(audio, batch_size=8)
                segments = result.get("segments", []) if isinstance(result, dict) else []
                transcript_segments = []
                transcript_text_parts = []
                for segment in segments:
                    if isinstance(segment, dict):
                        segment_text = str(segment.get("text", "")).strip()
                        if not segment_text:
                            continue
                        transcript_text_parts.append(segment_text)
                        transcript_segments.append(
                            {
                                "start": segment.get("start"),
                                "end": segment.get("end"),
                                "text": segment_text,
                                "speaker": segment.get("speaker"),
                            }
                        )
                transcript_text = " ".join(transcript_text_parts).strip()
                if not transcript_text:
                    return {
                        "status": "FAILED",
                        "recording_id": normalized.get("recording_id"),
                        "case_reference": normalized.get("case_reference"),
                        "recording_type": normalized.get("recording_type"),
                        "provider": self.name,
                        "error": "WhisperX produced no transcript text from the supplied media.",
                    }
                return {
                    "status": "COMPLETED",
                    "recording_id": normalized.get("recording_id"),
                    "case_reference": normalized.get("case_reference"),
                    "recording_type": normalized.get("recording_type"),
                    "provider": self.name,
                    "engine_version": getattr(whisperx, "__version__", self.engine_version),
                    "transcript": {
                        "text": transcript_text,
                        "segments": transcript_segments,
                        "language": result.get("language", "en") if isinstance(result, dict) else "en",
                        "provider": self.name,
                    },
                    "source_hash": normalized.get("sha256_hash") or self._hash_file(media_path),
                    "metadata": {"source_file": normalized.get("storage_reference") or media_path},
                    "created_at": self._utc_now(),
                }

            if backend == "whisper":
                import whisper  # type: ignore
                model = whisper.load_model("base")
                result = model.transcribe(media_path, fp16=False, language="en")
                segments = result.get("segments", []) if isinstance(result, dict) else []
                transcript_segments = []
                transcript_text_parts = []
                for segment in segments:
                    if isinstance(segment, dict):
                        segment_text = str(segment.get("text", "")).strip()
                        if not segment_text:
                            continue
                        transcript_text_parts.append(segment_text)
                        transcript_segments.append(
                            {
                                "start": segment.get("start"),
                                "end": segment.get("end"),
                                "text": segment_text,
                                "speaker": segment.get("speaker"),
                            }
                        )
                transcript_text = " ".join(transcript_text_parts).strip()
                if not transcript_text:
                    return {
                        "status": "FAILED",
                        "recording_id": normalized.get("recording_id"),
                        "case_reference": normalized.get("case_reference"),
                        "recording_type": normalized.get("recording_type"),
                        "provider": self.name,
                        "error": "Whisper produced no transcript text from the supplied media.",
                    }
                return {
                    "status": "COMPLETED",
                    "recording_id": normalized.get("recording_id"),
                    "case_reference": normalized.get("case_reference"),
                    "recording_type": normalized.get("recording_type"),
                    "provider": self.name,
                    "engine_version": getattr(whisper, "__version__", self.engine_version),
                    "transcript": {
                        "text": transcript_text,
                        "segments": transcript_segments,
                        "language": result.get("language", "en") if isinstance(result, dict) else "en",
                        "provider": self.name,
                    },
                    "source_hash": normalized.get("sha256_hash") or self._hash_file(media_path),
                    "metadata": {"source_file": normalized.get("storage_reference") or media_path},
                    "created_at": self._utc_now(),
                }

            if backend == "faster_whisper":
                from faster_whisper import WhisperModel  # type: ignore
                model = WhisperModel("tiny", device="cpu", compute_type="int8")
                segments, info = model.transcribe(media_path, language="en")
                transcript_segments = []
                transcript_text_parts = []
                for segment in segments:
                    segment_text = str(segment.text).strip()
                    if not segment_text:
                        continue
                    transcript_text_parts.append(segment_text)
                    transcript_segments.append({
                        "start": segment.start,
                        "end": segment.end,
                        "text": segment_text,
                        "speaker": None,
                    })
                transcript_text = " ".join(transcript_text_parts).strip()
                if not transcript_text:
                    return {
                        "status": "FAILED",
                        "recording_id": normalized.get("recording_id"),
                        "case_reference": normalized.get("case_reference"),
                        "recording_type": normalized.get("recording_type"),
                        "provider": self.name,
                        "error": "Faster Whisper produced no transcript text from the supplied media.",
                    }
                return {
                    "status": "COMPLETED",
                    "recording_id": normalized.get("recording_id"),
                    "case_reference": normalized.get("case_reference"),
                    "recording_type": normalized.get("recording_type"),
                    "provider": self.name,
                    "engine_version": getattr(WhisperModel, "__name__", self.engine_version),
                    "transcript": {
                        "text": transcript_text,
                        "segments": transcript_segments,
                        "language": info.language if hasattr(info, "language") else "en",
                        "provider": self.name,
                    },
                    "source_hash": normalized.get("sha256_hash") or self._hash_file(media_path),
                    "metadata": {"source_file": normalized.get("storage_reference") or media_path},
                    "created_at": self._utc_now(),
                }

            return {
                "status": "BLOCKED",
                "recording_id": normalized.get("recording_id"),
                "case_reference": normalized.get("case_reference"),
                "recording_type": normalized.get("recording_type"),
                "provider": self.name,
                "error": "WhisperX transcription is blocked because no supported local transcription backend is installed.",
            }
        except Exception as exc:  # pragma: no cover - runtime-specific failure path
            return {
                "status": "FAILED",
                "recording_id": normalized.get("recording_id"),
                "case_reference": normalized.get("case_reference"),
                "recording_type": normalized.get("recording_type"),
                "provider": self.name,
                "error": f"WhisperX processing failed: {exc}",
            }


class LocalDemoTranscriptionProvider(TranscriptionProvider):
    """Explicitly disabled demo provider that never fabricates spoken words."""

    name = "LocalDemo"
    engine_version = "local-demo-disabled"

    def is_available(self) -> bool:
        return False

    def transcribe(self, recording: Any) -> dict[str, Any]:
        normalized = self._coerce_recording(recording) or {}
        return {
            "status": "BLOCKED",
            "recording_id": normalized.get("recording_id"),
            "case_reference": normalized.get("case_reference"),
            "recording_type": normalized.get("recording_type"),
            "provider": self.name,
            "engine_version": self.engine_version,
            "error": "Local demo transcription is disabled. Install the real Whisper runtime and supply the original audio file to create a transcript.",
            "metadata": {"source_file": normalized.get("storage_reference")},
            "created_at": self._utc_now(),
        }


class TranscriptGenerationService:
    """Generate transcript metadata for a recording using a configured provider."""

    VALID_STATUSES = {"PENDING", "PROCESSING", "COMPLETED", "FAILED", "BLOCKED", "NOT_IMPLEMENTED"}

    def __init__(self, provider: str | TranscriptionProvider = "WhisperX") -> None:
        self.provider = self._resolve_provider(provider)

    @staticmethod
    def _resolve_provider(provider: str | TranscriptionProvider) -> TranscriptionProvider:
        # Accept either a TranscriptionProvider subclass/instance or a duck-typed
        # provider object implementing `transcribe()` and `is_available()` so
        # tests and lightweight fakes can be used without subclassing.
        if isinstance(provider, TranscriptionProvider):
            return provider
        if hasattr(provider, "transcribe") and hasattr(provider, "is_available"):
            return provider
        if isinstance(provider, str):
            provider_name = provider.strip().upper()
            if provider_name in {"WHISPERX", "WHISPER_X"}:
                return WhisperXProvider()
        return WhisperXProvider()

    @staticmethod
    def _coerce_recording(recording: Any) -> dict[str, Any] | None:
        return TranscriptionProvider._coerce_recording(recording)

    @staticmethod
    def _extract_text(recording: dict[str, Any] | None) -> str:
        return TranscriptionProvider._extract_text(recording)

    @staticmethod
    def _extract_segments(recording: dict[str, Any] | None) -> list[dict[str, Any]]:
        return TranscriptionProvider._extract_segments(recording)

    @staticmethod
    def _is_placeholder_transcript_text(transcript_text: Any) -> bool:
        return is_placeholder_transcript_text(transcript_text)

    @classmethod
    def _looks_like_placeholder_provider(cls, report: dict[str, Any] | None) -> bool:
        if not isinstance(report, dict):
            return False
        provider_name = str(report.get("provider") or "").lower()
        engine_version = str(report.get("engine_version") or "").lower()
        if "fakebrowser" in provider_name or "browser" in provider_name and "verification" in provider_name:
            return True
        if "fake-browser" in engine_version or "browser-verification" in engine_version:
            return True
        return False

    @classmethod
    def _rejected_placeholder_report(cls, normalized: dict[str, Any], report: dict[str, Any]) -> dict[str, Any]:
        provider_name = report.get("provider") or getattr(cls, "provider", None) or "unknown"
        return {
            "status": "FAILED",
            "recording_id": normalized.get("recording_id"),
            "case_reference": normalized.get("case_reference"),
            "recording_type": normalized.get("recording_type"),
            "provider": provider_name,
            "error": "Transcript text appears to be placeholder browser-validation content rather than the actual audio transcription.",
        }

    def generate_transcript(self, recording: Any) -> dict[str, Any]:
        normalized = self._coerce_recording(recording)
        if normalized is None:
            return {"status": "FAILED", "error": "No recording supplied."}

        transcript_text = self._extract_text(normalized)
        if transcript_text:
            if self._is_placeholder_transcript_text(transcript_text):
                return self._rejected_placeholder_report(normalized, {"provider": self.provider.name, "engine_version": self.provider.engine_version})
            return {
                "status": "COMPLETED",
                "recording_id": normalized.get("recording_id"),
                "case_reference": normalized.get("case_reference"),
                "recording_type": normalized.get("recording_type"),
                "provider": self.provider.name,
                "engine_version": self.provider.engine_version,
                "transcript": {
                    "text": transcript_text,
                    "segments": self._extract_segments(normalized),
                    "language": normalized.get("language") or "en",
                    "provider": self.provider.name,
                },
                "source_hash": normalized.get("sha256_hash"),
                "created_at": TranscriptionProvider._utc_now(),
            }

        output = self.provider.transcribe(normalized)
        if not isinstance(output, dict):
            return {"status": "FAILED", "error": "Provider returned an invalid transcription payload."}

        if self._looks_like_placeholder_provider(output):
            transcript_value = output.get("transcript")
            transcript_text = ""
            if isinstance(transcript_value, dict):
                transcript_text = str(transcript_value.get("text") or "")
            elif transcript_value is not None:
                transcript_text = str(transcript_value)
            if not transcript_text:
                transcript_text = str(output.get("text") or output.get("transcript_text") or "")
            if self._is_placeholder_transcript_text(transcript_text):
                return self._rejected_placeholder_report(normalized, output)

        if output.get("status") in {"BLOCKED", "NOT_IMPLEMENTED"}:
            output.setdefault("error", f"{self.provider.name} transcription is blocked or unavailable.")
            return output
        return output


class RecordingComparisonEngine:
    """Compare two interview recordings using transcript text deterministically."""

    def compare(self, citizen_recording: Any, constable_recording: Any) -> dict[str, Any]:
        citizen = self._coerce_recording(citizen_recording)
        constable = self._coerce_recording(constable_recording)

        citizen_text = self._extract_text(citizen)
        constable_text = self._extract_text(constable)
        citizen_available = bool(citizen_text)
        constable_available = bool(constable_text)
        if not citizen_available or not constable_available:
            return {
                "status": "WAITING_FOR_BOTH_TRANSCRIPTS",
                "overall_similarity": 0.0,
                "findings": [],
                "citizen_transcript_available": citizen_available,
                "constable_transcript_available": constable_available,
                "error": "Waiting for both transcripts before comparison can run.",
                "metadata": {
                    "citizen_recording_type": citizen.get("recording_type") if isinstance(citizen, dict) else None,
                    "constable_recording_type": constable.get("recording_type") if isinstance(constable, dict) else None,
                    "citizen_duration": citizen.get("duration") if isinstance(citizen, dict) else None,
                    "constable_duration": constable.get("duration") if isinstance(constable, dict) else None,
                },
            }

        similarity = self._compute_similarity(citizen_text, constable_text)
        findings = self._build_findings(similarity)

        return {
            "status": "COMPLETED",
            "overall_similarity": round(similarity, 2),
            "findings": findings,
            "citizen_transcript_available": True,
            "constable_transcript_available": True,
            "metadata": {
                "citizen_recording_type": citizen.get("recording_type") if isinstance(citizen, dict) else None,
                "constable_recording_type": constable.get("recording_type") if isinstance(constable, dict) else None,
                "citizen_duration": citizen.get("duration") if isinstance(citizen, dict) else None,
                "constable_duration": constable.get("duration") if isinstance(constable, dict) else None,
            },
        }

    @staticmethod
    def _coerce_recording(recording: Any) -> dict[str, Any] | None:
        return TranscriptionProvider._coerce_recording(recording)

    @staticmethod
    def _extract_text(recording: dict[str, Any] | None) -> str:
        if not recording:
            return ""
        for key in ("transcript_text", "transcript", "text"):
            value = recording.get(key)
            if isinstance(value, dict):
                nested = value.get("text")
                if nested is not None:
                    text = str(nested).strip()
                    if text:
                        return text
                continue
            if value is None:
                continue
            text = str(value).strip()
            if text:
                return text
        return ""

    @staticmethod
    def _tokenise(text: str) -> list[str]:
        return [token for token in re.findall(r"[a-z0-9]+", text.lower()) if token]

    @staticmethod
    def _compute_similarity(left: str, right: str) -> float:
        left_tokens = set(RecordingComparisonEngine._tokenise(left))
        right_tokens = set(RecordingComparisonEngine._tokenise(right))
        if not left_tokens and not right_tokens:
            return 100.0
        if not left_tokens or not right_tokens:
            return 0.0
        overlap = len(left_tokens & right_tokens)
        union = len(left_tokens | right_tokens)
        if union == 0:
            return 100.0
        return (overlap / union) * 100.0

    @staticmethod
    def _build_findings(similarity: float) -> list[dict[str, Any]]:
        if similarity >= 90.0:
            return [
                {
                    "category": "POTENTIAL_WORDING_VARIANCE",
                    "severity": "LOW",
                    "summary": "Transcript content is materially aligned, with only minor wording differences.",
                }
            ]
        return [
            {
                "category": "SIGNIFICANT_SEQUENCE_VARIANCE",
                "severity": "MEDIUM",
                "summary": "Transcript content diverges materially enough to merit a specific review of the recording sequence.",
            }
        ]
