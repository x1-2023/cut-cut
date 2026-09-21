#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
capcut_effects_catalog.py - CapCut Comprehensive Effects Catalog & Manager
Provides unified effect definitions for both Cloud Render & CapCut Desktop Drafts.
"""

import os
import sys
from pathlib import Path
from typing import Dict, Any, List, Optional

sys.stdout.reconfigure(encoding="utf-8")

BASE_CAPCUT_LOCAL = os.path.join(os.environ.get("LOCALAPPDATA", ""), "CapCut")

EFFECTS_DATABASE: List[Dict[str, Any]] = [
    # Category 1: Ánh sáng & Hạt (Particles & Glow)
    {
        "id": "7408393507246755077",
        "name": "Ánh sao (Star Glow)",
        "category": "Ánh sáng & Hạt",
        "folder": "b52a31369802c14a5042a5a06b4991bd",
        "description": "Hiệu ứng ánh sao lấp lánh nhẹ nhàng, phù hợp cho video cinematic",
        "speed": 0.15,
        "intensity": 0.4,
    },
    {
        "id": "7408393532802731270",
        "name": "Chòm sao (Constellation)",
        "category": "Ánh sáng & Hạt",
        "folder": "3d12170bb03d8acd5302eeb9d9f10415",
        "description": "Dải chòm sao chuyển động huyền ảo",
        "speed": 0.12,
        "intensity": 0.35,
    },
    {
        "id": "7408393578776481030",
        "name": "Mưa kim tuyến (Glitter Rain)",
        "category": "Ánh sáng & Hạt",
        "folder": "8972e8c2456a1e70afd5083a2d8c70c6",
        "description": "Kim tuyến vàng óng rơi nhẹ tạo chiều sâu khung hình",
        "speed": 0.20,
        "intensity": 0.5,
    },
    {
        "id": "7408393594375064837",
        "name": "Tinh không dịu nhẹ (Soft Galaxy)",
        "category": "Ánh sáng & Hạt",
        "folder": "9b7136a0e1c03d7bc6deeb8b4f4aa5f1",
        "description": "Bầu không khí vũ trụ mờ ảo, nâng tầm màu sắc",
        "speed": 0.10,
        "intensity": 0.3,
    },
    {
        "id": "7408393601262177541",
        "name": "Tia lửa mờ (Soft Sparks)",
        "category": "Ánh sáng & Hạt",
        "folder": "c912f82e20b28834bc84b061ca31774f",
        "description": "Đốm lửa bay bổng tạo cảm giác ấm áp, sống động",
        "speed": 0.15,
        "intensity": 0.45,
    },
    {
        "id": "7408393608132300038",
        "name": "Mảnh sao (Star Shards)",
        "category": "Ánh sáng & Hạt",
        "folder": "11d39eefff5ba8fb136b5cc1d93d11bb",
        "description": "Mảnh tinh vân vỡ vụn lấp lánh",
        "speed": 0.18,
        "intensity": 0.4,
    },
    {
        "id": "7408393651212258565",
        "name": "Hạt mờ (Bokeh Particles)",
        "category": "Ánh sáng & Hạt",
        "folder": "fbca58375dffd228d34d243a3866b334",
        "description": "Hạt bokeh điện ảnh làm mờ hậu cảnh tự nhiên",
        "speed": 0.12,
        "intensity": 0.35,
    },

    # Category 2: Thời tiết & Khí quyển (Weather & Atmosphere)
    {
        "id": "7399470231229336838",
        "name": "Ngọn lửa (Fire Flame)",
        "category": "Thời tiết & Khí quyển",
        "folder": "fc346694609e66fccbc8cf5c171ac14d",
        "description": "Ngọn lửa bốc cháy chân thực, phù hợp nhạc sôi động / rap",
        "speed": 0.25,
        "intensity": 0.6,
    },
    {
        "id": "7399465653700234502",
        "name": "Sương mù (Mystic Fog)",
        "category": "Thời tiết & Khí quyển",
        "folder": "9030b2f627144b2724a3e3881213aeae",
        "description": "Làn sương khói mờ ảo trôi ngang màn hình",
        "speed": 0.08,
        "intensity": 0.3,
    },
    {
        "id": "7446316654000099856",
        "name": "Biến hình tuyết (Snow Transform)",
        "category": "Thời tiết & Khí quyển",
        "folder": "8ede7d0c27d9423da48f3226a8384f95",
        "description": "Tuyết rơi mùa đông chuyển đổi mượt mà",
        "speed": 0.15,
        "intensity": 0.4,
    },
    {
        "id": "7409872890478202118",
        "name": "Trong mây (Dreamy Clouds)",
        "category": "Thời tiết & Khí quyển",
        "folder": "2c871332504a40b7dbe9e8e9e0c9283b",
        "description": "Mây bồng bềnh như cõi mơ",
        "speed": 0.10,
        "intensity": 0.3,
    },
    {
        "id": "7399466782085500165",
        "name": "Mùa mưa 2 (Rain Season 2)",
        "category": "Thời tiết & Khí quyển",
        "folder": "e74b25973452e4c4b30e9afc39cf41d7",
        "description": "Cơn mưa lãng mạn kèm vệt nước loang",
        "speed": 0.22,
        "intensity": 0.5,
    },
    {
        "id": "7409872299135962374",
        "name": "Hạt mưa (Raindrops)",
        "category": "Thời tiết & Khí quyển",
        "folder": "2ed20557bb6b691f66e05aafdbb13595",
        "description": "Hạt mưa nhẹ trên mặt kính ống kính",
        "speed": 0.20,
        "intensity": 0.4,
    },
    {
        "id": "7399469933865815301",
        "name": "Mưa bão (Storm Rain)",
        "category": "Thời tiết & Khí quyển",
        "folder": "40a59ce61692a825c049cd5b15bc6ded",
        "description": "Cơn mưa lớn tốc độ cao",
        "speed": 0.30,
        "intensity": 0.6,
    },

    # Category 3: Viền & Điểm nhấn (Borders & Highlights)
    {
        "id": "7408393562729106693",
        "name": "Viền lấp lánh (Sparkle Border)",
        "category": "Viền & Khung hình",
        "folder": "b0d27c4b37b1e91333582a08c68cfcff",
        "description": "Viền khung lấp lánh xung quanh video tạo sự nổi bật",
        "speed": 0.15,
        "intensity": 0.5,
    },
]


class CapCutEffectsCatalog:
    """Provides categorized search and metadata retrieval for CapCut effects."""

    def __init__(self):
        self.effects = EFFECTS_DATABASE

    def get_categories(self) -> List[str]:
        """Return unique list of effect categories."""
        cats = []
        for e in self.effects:
            if e["category"] not in cats:
                cats.append(e["category"])
        return cats

    def get_effects_by_category(self, category: str) -> List[Dict[str, Any]]:
        """Filter effects by category."""
        return [e for e in self.effects if e["category"] == category]

    def get_effect_by_id(self, effect_id: str) -> Optional[Dict[str, Any]]:
        """Find effect by CapCut resource ID."""
        for e in self.effects:
            if e["id"] == str(effect_id):
                return e
        return None

    def get_local_effect_path(self, effect_id: str) -> Optional[str]:
        """Resolve local path to cached effect files if available on PC."""
        e = self.get_effect_by_id(effect_id)
        if not e:
            return None
        folder = e.get("folder", "")
        if not folder or not BASE_CAPCUT_LOCAL:
            return None
        p = os.path.join(BASE_CAPCUT_LOCAL, "User Data", "Cache", "effect", effect_id, folder)
        if os.path.exists(p):
            return p.replace("\\", "/")
        return None

    def list_all(self) -> List[Dict[str, Any]]:
        """Return all available effects."""
        return self.effects


if __name__ == "__main__":
    catalog = CapCutEffectsCatalog()
    print(f"Total Effects Loaded: {len(catalog.list_all())}")
    for cat in catalog.get_categories():
        items = catalog.get_effects_by_category(cat)
        print(f"Category [{cat}]: {len(items)} effects")
        for item in items:
            print(f"  - {item['name']} ({item['id']})")
