import sys, time, os
t0 = time.time()
try:
    import torch
except Exception as e:
    print("TORCH IMPORT FAILED:", type(e).__name__, str(e)[:300]); sys.exit(2)
print(f"torch {torch.__version__} | CUDA available: {torch.cuda.is_available()} | threads: {torch.get_num_threads()} | import {time.time()-t0:.1f}s")

t = time.time()
try:
    from sentence_transformers import SentenceTransformer, util
except Exception as e:
    print("sentence_transformers IMPORT FAILED:", type(e).__name__, str(e)[:300]); sys.exit(3)
print(f"sentence_transformers import {time.time()-t:.1f}s")

t = time.time()
model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2", device="cpu")
print(f"model loaded in {time.time()-t:.1f}s | embedding size: {getattr(model, "get_embedding_dimension", model.get_sentence_embedding_dimension)()} | parameters: {sum(p.numel() for p in model.parameters())/1e6:.1f}M")

pairs = [
    ("JS", "JavaScript"), ("JavaScript", "Node.js"), ("REST APIs", "web services development"),
    ("React", "Vue.js"), ("React", "front-end frameworks"), ("SQL", "PostgreSQL"), ("Docker", "containerization"),
    ("AWS", "cloud computing"), ("machine learning", "deep learning"), ("communication", "teamwork"),
    ("Python", "Java"), ("Python", "pandas"), ("Excel", "Python"), ("Python", "banana bread recipe"),
    ("Kubernetes", "container orchestration"), ("Postgres", "PostgreSQL"), ("C", "C++"),
]
a = model.encode([p[0] for p in pairs], convert_to_tensor=True, normalize_embeddings=True)
b = model.encode([p[1] for p in pairs], convert_to_tensor=True, normalize_embeddings=True)
print("\ncosine similarity (1.0 = same meaning, 0 = unrelated):")
for (x, y), s in sorted(zip(pairs, util.cos_sim(a, b).diagonal().tolist()), key=lambda z: -z[1]):
    print(f"  {s:5.2f}  {x!r:22} vs {y!r}")

# a requirement sentence vs resume sentences
req = "Experience building and maintaining REST APIs in Python"
cands = ["Built REST APIs with Node.js", "Developed FastAPI microservices in Python", "Led the college cultural club",
         "Designed web services using Django", "Winner of national hackathon"]
sc = util.cos_sim(model.encode(req, convert_to_tensor=True), model.encode(cands, convert_to_tensor=True))[0].tolist()
print(f"\nrequirement: {req!r}")
for c, s in sorted(zip(cands, sc), key=lambda z: -z[1]): print(f"  {s:5.2f}  {c}")

# speed
words = [f"skill number {i} such as python and sql and react" for i in range(200)]
t = time.time(); model.encode(words, batch_size=32); dt = time.time() - t
print(f"\nspeed: encoded 200 short texts in {dt:.2f}s ({200/dt:.0f} texts/s) on CPU")
t = time.time(); model.encode(["one more skill"]); print(f"single text: {(time.time()-t)*1000:.0f} ms")

cache = os.path.expanduser("~/.cache/huggingface")
size = sum(os.path.getsize(os.path.join(d, f)) for d, _, fs in os.walk(cache) for f in fs) if os.path.isdir(cache) else 0
print(f"model files on disk: {size/1e6:.0f} MB")
print(f"total time: {time.time()-t0:.1f}s")
