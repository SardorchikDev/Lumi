import os
import pickle
import sqlite3
from pathlib import Path

import numpy as np
from openai import OpenAI

# Local RAG using SQLite FTS5 (Keywords) + Numpy (Vectors)
DB_PATH = os.path.expanduser("~/.lumi_rag.db")
VEC_PATH = os.path.expanduser("~/.lumi_vectors.pkl")

# ── Embedding Client ──────────────────────────────────────────────────────────

def get_embedding_client():
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return None
    return OpenAI(
        api_key=api_key,
        base_url="https://generativelanguage.googleapis.com/v1beta/openai/"
    )

def get_embedding(text: str, client) -> list[float] | None:
    try:
        text = text.replace("\n", " ")[:8000]  # simple truncation
        resp = client.embeddings.create(
            input=[text],
            model="text-embedding-004"
        )
        return resp.data[0].embedding
    except Exception:
        return None

# ── Indexing ──────────────────────────────────────────────────────────────────

def build_index(repo_path="."):
    """Build hybrid index: SQLite FTS5 + Vector Embeddings."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DROP TABLE IF EXISTS search_index")
    c.execute("CREATE VIRTUAL TABLE search_index USING fts5(filepath, content)")

    vectors = {}  # {filepath: np.array}
    client = get_embedding_client()

    count = 0
    skipped = 0

    print(f"  Indexing {repo_path}...", end="", flush=True)

    for root, dirs, files in os.walk(repo_path):
        if any(ignore in root for ignore in ['.git', '__pycache__', 'node_modules', 'venv', '.venv', '.idea', '.vscode']):
            continue

        for file in files:
            if not file.endswith(('.py', '.md', '.txt', '.js', '.html', '.css', '.sh', '.json', '.yaml', '.yml', '.ts', '.rs', '.go')):
                continue

            filepath = os.path.join(root, file)
            try:
                content = Path(filepath).read_text(encoding='utf-8')
                if not content.strip():
                    continue

                # 1. SQLite FTS
                c.execute("INSERT INTO search_index (filepath, content) VALUES (?, ?)", (filepath, content))

                # 2. Vector Embedding (only if client available)
                if client and len(content) < 50000:  # skip huge files
                    emb = get_embedding(content, client)
                    if emb:
                        vectors[filepath] = np.array(emb, dtype=np.float32)

                count += 1
                if count % 10 == 0:
                    print(".", end="", flush=True)
            except Exception:
                skipped += 1

    conn.commit()
    conn.close()

    # Save vectors
    if vectors:
        with open(VEC_PATH, "wb") as f:
            pickle.dump(vectors, f)

    print(f" Done. ({count} indexed, {skipped} skipped)")
    return count

# ── Search ────────────────────────────────────────────────────────────────────

def cosine_similarity(v1, v2):
    return np.dot(v1, v2) / (np.linalg.norm(v1) * np.linalg.norm(v2))

def search_index(query, limit=5, hybrid=True):
    """
    Search using Hybrid approach (Keyword + Vector).
    Returns list of (filepath, content).
    """
    results = {}  # {filepath: (score, content)}

    # 1. Keyword Search (SQLite FTS)
    if os.path.exists(DB_PATH):
        try:
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            # FTS matches
            c.execute("SELECT filepath, content FROM search_index WHERE search_index MATCH ? LIMIT ?", (query, limit * 2))
            for row in c.fetchall():
                fp, content = row
                results[fp] = (1.0, content)  # Base score for keyword match
            conn.close()
        except Exception:
            pass

    # 2. Vector Search
    if hybrid and os.path.exists(VEC_PATH):
        client = get_embedding_client()
        if client:
            q_emb = get_embedding(query, client)
            if q_emb:
                q_vec = np.array(q_emb, dtype=np.float32)

                try:
                    with open(VEC_PATH, "rb") as f:
                        vectors = pickle.load(f)

                    # Calculate all similarities
                    # (In a real app, use Faiss or Annoy for speed, but loop is fine for <10k)
                    vec_scores = []
                    for fp, vec in vectors.items():
                        score = cosine_similarity(q_vec, vec)
                        vec_scores.append((score, fp))

                    # Top K vector matches
                    vec_scores.sort(key=lambda x: x[0], reverse=True)
                    for score, fp in vec_scores[:limit]:
                        # Retrieve content from DB if not already in results
                        if fp not in results:
                            # Need to fetch content from DB
                            conn = sqlite3.connect(DB_PATH)
                            cur = conn.cursor()
                            cur.execute("SELECT content FROM search_index WHERE filepath = ?", (fp,))
                            row = cur.fetchone()
                            conn.close()
                            if row:
                                results[fp] = (score + 0.5, row[0]) # Boost vector matches
                        else:
                            # Boost existing keyword match
                            old_score, content = results[fp]
                            results[fp] = (old_score + score, content)

                except Exception:
                    pass

    # Sort by score
    final = sorted(results.items(), key=lambda x: x[1][0], reverse=True)[:limit]
    return [(fp, content) for fp, (score, content) in final]
