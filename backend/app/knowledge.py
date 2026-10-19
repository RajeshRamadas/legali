"""Knowledge base for the chat assistant: markdown files in app/knowledge, split by section and searched with BM25.

Each `## ` section is one chunk, titled with its file's `# ` heading. BM25 needs no external service; swap
`search` for a vector store when the knowledge base outgrows keyword retrieval.
"""
import math
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

KNOWLEDGE_DIR = Path(__file__).parent / "knowledge"
# Query words customers use for the same idea the knowledge base words differently.
SYNONYMS = {"cost": "price", "fee": "price", "charge": "price", "much": "price", "rate": "price", "lawyer": "advocate", "electricity": "bescom"}
STOPWORDS = set("a an and are as at be by can do does for from has have how i if in is it its me my of on or our so that the their them then there this to us was we what when where which who why will with you your".split())

@dataclass
class Chunk:
    id: str
    title: str
    section: str
    text: str
    terms: Counter = field(default_factory=Counter, repr=False)

def tokenize(text: str) -> list[str]:
    words = re.findall(r"[a-z0-9₹]+(?:[-'][a-z0-9]+)*", text.lower())
    # Light stemming so "registrations" matches "registration" and "deeds" matches "deed".
    return [w[:-1] if len(w) > 3 and w.endswith("s") and not w.endswith("ss") else w for w in words if w not in STOPWORDS]

def load_chunks(directory: Path = KNOWLEDGE_DIR) -> list[Chunk]:
    chunks = []
    for path in sorted(directory.glob("*.md")):
        title, section, lines = path.stem, None, []
        def flush():
            body = "\n".join(lines).strip()
            if section and body:
                chunks.append(Chunk(id=f"{path.stem}/{re.sub(r'[^a-z0-9]+', '-', section.lower()).strip('-')}", title=title, section=section, text=body))
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.startswith("# "):
                title = line[2:].strip()
            elif line.startswith("## "):
                flush()
                section, lines = line[3:].strip(), []
            else:
                lines.append(line)
        flush()
    for chunk in chunks:
        # Headings count twice: they say what a section is about.
        chunk.terms = Counter(tokenize(f"{chunk.section} {chunk.section} {chunk.title} {chunk.text}"))
    return chunks

class KnowledgeBase:
    def __init__(self, chunks: list[Chunk], k1: float = 1.4, b: float = 0.75):
        self.chunks, self.k1, self.b = chunks, k1, b
        self.avg_len = sum(sum(c.terms.values()) for c in chunks) / max(len(chunks), 1)
        doc_freq = Counter(term for c in chunks for term in c.terms)
        n = len(chunks)
        self.idf = {term: math.log(1 + (n - df + 0.5) / (df + 0.5)) for term, df in doc_freq.items()}

    def search(self, query: str, limit: int = 4) -> list[Chunk]:
        query_terms = set(tokenize(query))
        query_terms |= {SYNONYMS[t] for t in query_terms if t in SYNONYMS}
        scored = []
        for chunk in self.chunks:
            length = sum(chunk.terms.values())
            score = 0.0
            for term in query_terms:
                tf = chunk.terms.get(term, 0)
                if tf:
                    score += self.idf[term] * tf * (self.k1 + 1) / (tf + self.k1 * (1 - self.b + self.b * length / self.avg_len))
            if score > 0:
                scored.append((score, chunk))
        scored.sort(key=lambda item: item[0], reverse=True)
        return [chunk for _, chunk in scored[:limit]]

knowledge_base = KnowledgeBase(load_chunks())
