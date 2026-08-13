from dataclasses import dataclass


@dataclass(frozen=True)
class DocumentChunk:
    index: int
    text: str
    start_char: int
    end_char: int

    @property
    def identifier(self) -> str:
        return f"chunk-{self.index + 1}"


class DocumentChunker:
    def __init__(self, max_chars: int, overlap_chars: int = 0):
        if max_chars <= 0:
            raise ValueError("max_chars must be positive")
        if overlap_chars < 0 or overlap_chars >= max_chars:
            raise ValueError("overlap_chars must be between zero and max_chars")
        self.max_chars = max_chars
        self.overlap_chars = overlap_chars

    def split(self, text: str) -> list[DocumentChunk]:
        text = text.strip()
        if not text:
            return []
        if len(text) <= self.max_chars:
            return [DocumentChunk(0, text, 0, len(text))]

        chunks: list[DocumentChunk] = []
        start = 0
        while start < len(text):
            target_end = min(len(text), start + self.max_chars)
            end = self._boundary(text, start, target_end)
            if end <= start:
                end = target_end
            chunks.append(DocumentChunk(len(chunks), text[start:end].strip(), start, end))
            if end >= len(text):
                break
            start = max(start + 1, end - self.overlap_chars)
        return chunks

    @staticmethod
    def _boundary(text: str, start: int, target_end: int) -> int:
        if target_end >= len(text):
            return len(text)
        lower_bound = start + int((target_end - start) * 0.6)
        candidates = [
            text.rfind("\n--- Page ", lower_bound, target_end),
            text.rfind("\n\n", lower_bound, target_end),
            text.rfind("\n", lower_bound, target_end),
            text.rfind(". ", lower_bound, target_end),
        ]
        boundary = max(candidates)
        if boundary < lower_bound:
            return target_end
        return boundary + (2 if text[boundary:boundary + 2] == ". " else 1)
