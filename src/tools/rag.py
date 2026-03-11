import os
import sqlite3
from pathlib import Path

# Local RAG using SQLite FTS5 for zero-dependency full text search
DB_PATH = os.path.expanduser("~/.lumi_rag.db")

def build_index(repo_path="."):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DROP TABLE IF EXISTS search_index")
    # Using FTS5 for full-text search capabilities natively in SQLite
    c.execute("CREATE VIRTUAL TABLE search_index USING fts5(filepath, content)")
    
    count = 0
    for root, dirs, files in os.walk(repo_path):
        if any(ignore in root for ignore in ['.git', '__pycache__', 'node_modules', 'venv', '.venv']):
            continue
        for file in files:
            filepath = os.path.join(root, file)
            # Only index specific extensions to avoid binary files
            if not file.endswith(('.py', '.md', '.txt', '.js', '.html', '.css', '.sh', '.json', '.yaml', '.yml')):
                continue
            try:
                content = Path(filepath).read_text(encoding='utf-8')
                c.execute("INSERT INTO search_index (filepath, content) VALUES (?, ?)", (filepath, content))
                count += 1
            except Exception:
                pass
                
    conn.commit()
    conn.close()
    return count

def search_index(query, limit=3):
    if not os.path.exists(DB_PATH):
        return []
        
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    # Rank by bm25 score implicitly in fts5
    try:
        c.execute("SELECT filepath, content FROM search_index WHERE search_index MATCH ? ORDER BY rank LIMIT ?", (query, limit))
        results = c.fetchall()
        conn.close()
        return results
    except Exception as e:
        conn.close()
        raise e
