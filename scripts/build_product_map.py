# scripts/build_product_map.py
import pandas as pd, json, pathlib, re

def main(capsule="S126"):
    csv_path = pathlib.Path(f"capsules/{capsule}/inputs/products_export_1.csv")
    df = pd.read_csv(csv_path)
    df["CPI"] = df["Handle"].str.extract(r"(\d{4}-\d{6})")
    out = {row.CPI: row["Admin GraphQL API ID"] for row in df.itertuples() if pd.notna(row.CPI)}
    out_path = pathlib.Path(f"capsules/{capsule}/manifests/product_map.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    json.dump(out, open(out_path, "w"), indent=2)
    print(f"✅ product_map.json built → {out_path}")

if __name__ == "__main__":
    main()
