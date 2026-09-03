"""Esportazione dei risultati in CSV e JSON."""

import csv
import json
import dataclasses
from typing import List

from .models import PlaceResult


def export_csv(results: List[PlaceResult], path: str, max_reviews: int = 3):
    rows = [r.to_row(max_reviews=max_reviews) for r in results]
    if not rows:
        fieldnames = ["categoria", "nome", "indirizzo"]
    else:
        fieldnames = list(rows[0].keys())

    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def export_json(results: List[PlaceResult], path: str):
    def review_to_dict(r):
        return dataclasses.asdict(r)

    data = []
    for r in results:
        d = dataclasses.asdict(r)
        data.append(d)

    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
