# scripts/parse_shotlists.py
import pandas as pd, json, pathlib

def parse_one(path):
    df = pd.read_csv(path, dtype=str)
    return df[["Product ID", "Look Number"]].rename(columns=lambda c: c.strip().lower())

def main(capsule="S126"):
    base = pathlib.Path(f"capsules/{capsule}/inputs/shotlists")
    dfs = [parse_one(p) for p in base.glob("*.csv")]
    df = pd.concat(dfs, ignore_index=True)
    looks = {}
    for look_no, group in df.groupby("look number"):
        looks[f"Look_{look_no}"] = {
            "product_ids": group["product id"].dropna().unique().tolist(),
            "hero_product": group["product id"].dropna().iloc[0]
        }
    out = {
        "metadata": {"source_files": [p.name for p in base.glob('*.csv')]},
        "looks": looks
    }
    out_path = pathlib.Path(f"capsules/{capsule}/manifests/look_relations.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    json.dump(out, open(out_path, "w"), indent=2)
    print(f"✅ look_relations.json built → {out_path}")

if __name__ == "__main__":
    main()
