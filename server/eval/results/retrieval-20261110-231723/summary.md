# Retrieval eval 20261110-231723

20 held-out problems vs 35-card library; relevant = shares the gold pattern. Gold labels human-reviewed: 0/20.

| model | query | hit@1 | hit@3 | MRR@5 | query p50 (ms) |
|---|---|---|---|---|---|
| bge-small-zh-v1.5 | title | 0.35 | 0.5 | 0.452 | 1.4 |
| bge-small-zh-v1.5 | code | 0.15 | 0.3 | 0.26 | 3.6 |
| bge-small-zh-v1.5 | hyde | 0.8 | 0.95 | 0.875 | 2.1 |
| paraphrase-multilingual-MiniLM-L12-v2 | title | 0.2 | 0.35 | 0.279 | 3.5 |
| paraphrase-multilingual-MiniLM-L12-v2 | code | 0.4 | 0.45 | 0.425 | 11.9 |
| paraphrase-multilingual-MiniLM-L12-v2 | hyde | 0.5 | 0.7 | 0.635 | 6.1 |
| jina-embeddings-v2-base-zh | title | 0.35 | 0.5 | 0.439 | 7.7 |
| jina-embeddings-v2-base-zh | code | 0.3 | 0.45 | 0.395 | 23.0 |
| jina-embeddings-v2-base-zh | hyde | 0.6 | 0.8 | 0.692 | 12.1 |
