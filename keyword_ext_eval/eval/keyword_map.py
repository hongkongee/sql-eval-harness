"""스키마 키워드(표면형) → 사전 묶음(대표 키워드) → 테이블 판정. 평가 전용.

- 표면형이 어느 묶음인지는 서비스 사전(schema_keywords.yaml)을 "읽어서" 판정한다.
  API가 낸 schema 키워드는 사전 표면형 그대로라 정확히 일치한다.
- 묶음 → 테이블은 eval/maps/schema_keyword_table_map.yaml (서비스는 이 파일을 안 읽음).
- GLiNER·Qwen처럼 사전에 없는 단어: 단어 안에 사전 표면형이 들어 있으면 그 묶음으로 본다
  (긴 표면형 우선, 겹치지 않게 여러 개 가능 - "심부전 진단" → 진단, "측정값 변화" → 측정값).
  하나도 없으면 "미매핑 단어"로 테이블을 덮지 못한 것으로 친다.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from eval.common import EVAL_DIR, dict_path

MAPS_DIR = EVAL_DIR / "maps"


def load_yaml(path: str | Path) -> dict:
    return yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}


@dataclass
class Resolution:
    word: str
    how: str  # exact | contains | unmapped
    groups: list = field(default_factory=list)
    tables: list = field(default_factory=list)


class KeywordTableMap:
    def __init__(self, dict_file: str | Path | None = None, table_map_file: str | Path | None = None,
                 warn=True):
        self.dict_file = Path(dict_file) if dict_file else dict_path()
        self.table_map_file = Path(table_map_file) if table_map_file else MAPS_DIR / "schema_keyword_table_map.yaml"
        raw_dict = load_yaml(self.dict_file)
        self.surface_to_group: dict[str, str] = {}
        for group, surfaces in raw_dict.items():
            for s in surfaces or []:
                self.surface_to_group[str(s)] = str(group)
        self.group_to_tables: dict[str, list[str]] = {
            str(k): list(v or []) for k, v in load_yaml(self.table_map_file).items()
        }
        self.unmapped_groups = sorted(set(raw_dict) - set(self.group_to_tables))
        if warn and self.unmapped_groups:
            print(f"[warn] 사전에 있는데 {self.table_map_file.name}에 없는 묶음: {self.unmapped_groups} "
                  "(이 묶음 키워드는 어떤 테이블도 덮지 않은 것으로 계산됩니다)", file=sys.stderr)
        # 긴 표면형부터 시도 (contains 판정용)
        self._surfaces_by_len = sorted(self.surface_to_group, key=len, reverse=True)

    def is_dict_surface(self, word: str) -> bool:
        return word in self.surface_to_group

    def contained_groups(self, word: str) -> list[str]:
        """word 안에 들어 있는 사전 표면형의 묶음들 (긴 표면형 우선, 겹치지 않게)."""
        taken = [False] * len(word)
        hits = []  # (start, group)
        for s in self._surfaces_by_len:
            start = word.find(s)
            while start != -1:
                end = start + len(s)
                if not any(taken[start:end]):
                    for i in range(start, end):
                        taken[i] = True
                    hits.append((start, self.surface_to_group[s]))
                start = word.find(s, start + 1)
        groups = []
        for _, g in sorted(hits):
            if g not in groups:
                groups.append(g)
        return groups

    def resolve(self, word: str) -> Resolution:
        if word in self.surface_to_group:
            groups, how = [self.surface_to_group[word]], "exact"
        else:
            groups = self.contained_groups(word)
            how = "contains" if groups else "unmapped"
        tables = []
        for g in groups:
            for t in self.group_to_tables.get(g, []):
                if t not in tables:
                    tables.append(t)
        return Resolution(word, how, groups, tables)


class LabelTableMap:
    """라벨 → 테이블 (gliner_schema_label_table_map.yaml, concept_label_table_map.yaml)."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.map = {str(k): list(v or []) for k, v in load_yaml(self.path).items()}

    def tables(self, label: str | None) -> list[str]:
        return self.map.get(label, []) if label else []
