# fine_tune.py
# Placeholder for fine-tuning dataset creation
import os
from rag_store import store

def prepare_finetune_dataset(output_path='finetune_dataset.jsonl'):
    # Very simple conversion: create trivial QA pairs from RAG texts (demo only)
    with open(output_path, 'w', encoding='utf-8') as f:
        for i, text in enumerate(store.texts[:100]):
            prompt = f"Q: Summarize document {i}\n\n{text[:500]}\n\n"
            completion = " A: Summary: ...\n"
            f.write(json.dumps({"prompt": prompt, "completion": completion}) + "\n")
    print('Wrote', output_path)

if __name__ == '__main__':
    prepare_finetune_dataset()
