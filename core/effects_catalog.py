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
    # --------------------------------------------------------------------------
    # Category 1: Ánh sáng & Hạt (Sparkle & Particles)
    # --------------------------------------------------------------------------
    {
        "id": "7613052884267060498",
        "name": "Đom đóm sao (Tiny Star Dust)",
        "category": "Ánh sáng & Hạt",
        "description": "Các hạt bụi sao nhỏ li ti, lơ lửng phát sáng tinh tế không che video",
        "speed": 0.12,
        "intensity": 0.35,
    },
    {
        "id": "7675835939205287175",
        "name": "Chòm sao lớn (Constellation Stars)",
        "category": "Ánh sáng & Hạt",
        "description": "Dải chòm sao và ngôi sao 5 cánh lớn chuyển động huyền ảo",
        "speed": 0.15,
        "intensity": 0.4,
    },
    {
        "id": "7677975064649796885",
        "name": "Lấp lánh (Sparkle Glow)",
        "category": "Ánh sáng & Hạt",
        "description": "Hạt bụi lấp lánh ánh kim điện ảnh phủ đều khung hình",
        "speed": 0.20,
        "intensity": 0.5,
    },
    {
        "id": "7657040797845458184",
        "name": "Đốm sao mờ (Soft Star Dust)",
        "category": "Ánh sáng & Hạt",
        "description": "Bụi tinh vân sao mờ lãng mạn, tăng chiều sâu video",
        "speed": 0.12,
        "intensity": 0.35,
    },
    {
        "id": "7679412954219007253",
        "name": "Ánh sáng mượt (Smooth Glow)",
        "category": "Ánh sáng & Hạt",
        "description": "Luồng ánh sáng mềm mại lan tỏa cinematic",
        "speed": 0.10,
        "intensity": 0.4,
    },
    {
        "id": "7678405750300921108",
        "name": "Nhảy bùng nắng (Sun Flare Burst)",
        "category": "Ánh sáng & Hạt",
        "description": "Tia nắng bùng sáng tạo cảm giác ấm áp, tươi mới",
        "speed": 0.18,
        "intensity": 0.5,
    },
    {
        "id": "7642399565123030279",
        "name": "Vũ trụ trừu tượng (Cosmic Space)",
        "category": "Ánh sáng & Hạt",
        "description": "Không gian vũ trụ trừu tượng huyền bí, cinematic",
        "speed": 0.12,
        "intensity": 0.45,
    },
    {
        "id": "7617821598745103633",
        "name": "Lấp lánh cổ điển (Classic Sparkle)",
        "category": "Ánh sáng & Hạt",
        "description": "Ánh sao lấp lánh kiểu cổ điển nhẹ nhàng",
        "speed": 0.15,
        "intensity": 0.4,
    },

    # --------------------------------------------------------------------------
    # Category 2: Thời tiết & Khí quyển (Atmosphere & Fire)
    # --------------------------------------------------------------------------
    {
        "id": "7399470231229336838",
        "name": "Ngọn lửa (Fire Flame)",
        "category": "Thời tiết & Khí quyển",
        "folder": "fc346694609e66fccbc8cf5c171ac14d",
        "description": "Ngọn lửa bốc cháy rực rỡ, phù hợp nhạc sôi động / rap",
        "speed": 0.25,
        "intensity": 0.6,
    },
    {
        "id": "7665927601499688208",
        "name": "Bừng lên trong than hồng (Ember Burst)",
        "category": "Thời tiết & Khí quyển",
        "description": "Đốm lửa tàn than hồng bốc bay cuồn cuộn",
        "speed": 0.22,
        "intensity": 0.55,
    },
    {
        "id": "7612051239978765575",
        "name": "Tuyết mùa đông (Winter Snow)",
        "category": "Thời tiết & Khí quyển",
        "description": "Bông tuyết trắng rơi chậm chuyển động tự nhiên",
        "speed": 0.15,
        "intensity": 0.4,
    },
    {
        "id": "7613057255059098898",
        "name": "Ngày tuyết rơi (Snowy Day)",
        "category": "Thời tiết & Khí quyển",
        "description": "Cơn mưa tuyết mùa đông lãng mạn",
        "speed": 0.18,
        "intensity": 0.45,
    },
    {
        "id": "7676410157496077576",
        "name": "Khói hồng (Pink Smoke Mist)",
        "category": "Thời tiết & Khí quyển",
        "description": "Làn sương khói hồng mờ ảo trôi ngang màn hình",
        "speed": 0.10,
        "intensity": 0.35,
    },
    {
        "id": "7676108681888484629",
        "name": "Mưa sắc màu (Prism Rain)",
        "category": "Thời tiết & Khí quyển",
        "description": "Vệt mưa lăng kính sắc màu chiếu qua ống kính",
        "speed": 0.20,
        "intensity": 0.5,
    },

    # --------------------------------------------------------------------------
    # Category 3: Tia sáng & Năng lượng (Light FX & Streaks)
    # --------------------------------------------------------------------------
    {
        "id": "7660564214800534805",
        "name": "Sao chổi tím (Purple Comet)",
        "category": "Tia sáng & Năng lượng",
        "description": "Tia sáng sao chổi tím quét ngang màn hình cực bắt mắt",
        "speed": 0.20,
        "intensity": 0.5,
    },
    {
        "id": "7664871326607281426",
        "name": "Ánh chớp nhạt màu (Soft Lightning Flash)",
        "category": "Tia sáng & Năng lượng",
        "description": "Hiệu ứng chớp sáng điện ảnh theo nhịp",
        "speed": 0.25,
        "intensity": 0.45,
    },
    {
        "id": "7511267138485767477",
        "name": "Khối lập phương tia lửa (Spark Cube)",
        "category": "Tia sáng & Năng lượng",
        "description": "Khối tia lửa sci-fi chuyển động công nghệ cao",
        "speed": 0.20,
        "intensity": 0.5,
    },
    {
        "id": "7512488287714561333",
        "name": "Vụ nổ màu vàng (Golden Explosion)",
        "category": "Tia sáng & Năng lượng",
        "description": "Chùm hạt vàng bùng nổ sang trọng",
        "speed": 0.22,
        "intensity": 0.55,
    },
    {
        "id": "7591942365263170832",
        "name": "Pháo hoa hình chữ (Text Fireworks)",
        "category": "Tia sáng & Năng lượng",
        "description": "Chùm pháo hoa tỏa sáng rực rỡ",
        "speed": 0.20,
        "intensity": 0.5,
    },

    # --------------------------------------------------------------------------
    # Category 4: Retro & Điện ảnh (Vintage & Film)
    # --------------------------------------------------------------------------
    {
        "id": "7658984064136826113",
        "name": "CRT noir (Vintage CRT Noir)",
        "category": "Retro & Điện ảnh",
        "description": "Vạch quét màn hình TV CRT cổ điển và viền mờ điện ảnh",
        "speed": 0.15,
        "intensity": 0.45,
    },
    {
        "id": "7677904078302661908",
        "name": "Trò chơi điện tử retro (Retro Arcade)",
        "category": "Retro & Điện ảnh",
        "description": "Phong cách trò chơi điện tử máy gạt cổ điển",
        "speed": 0.20,
        "intensity": 0.5,
    },
    {
        "id": "7678450186342960405",
        "name": "Nhịp phim (Film Reel Rhythm)",
        "category": "Retro & Điện ảnh",
        "description": "Chuyển động cuộn phim nhựa cổ điển",
        "speed": 0.18,
        "intensity": 0.45,
    },
    {
        "id": "7678448350139665685",
        "name": "Màn hình cổ điển (Vintage Screen)",
        "category": "Retro & Điện ảnh",
        "description": "Hiệu ứng màn hình máy quay phim xưa",
        "speed": 0.12,
        "intensity": 0.4,
    },

    # --------------------------------------------------------------------------
    # Category 5: Glitch & Cyberpunk (Nhiễu sóng & Sci-Fi)
    # --------------------------------------------------------------------------
    {
        "id": "7677555476464209172",
        "name": "Sóng sọc (Striped Waves Glitch)",
        "category": "Glitch & Cyberpunk",
        "description": "Nhiễu sóng scanline ngang chuyển động liên tục",
        "speed": 0.25,
        "intensity": 0.6,
    },
    {
        "id": "7665974987978722580",
        "name": "Quét dây (Scanline Glitch)",
        "category": "Glitch & Cyberpunk",
        "description": "Hiệu ứng quét sóng điện tử cyberpunk",
        "speed": 0.22,
        "intensity": 0.5,
    },
    {
        "id": "7606931439862435090",
        "name": "Kỳ dị 8 bit (8-Bit Glitch FX)",
        "category": "Glitch & Cyberpunk",
        "description": "Nhiễu hạt pixel số 8-bit hiện đại",
        "speed": 0.20,
        "intensity": 0.5,
    },
    {
        "id": "7668649738417294600",
        "name": "Vệt xung (Pulse Glitch)",
        "category": "Glitch & Cyberpunk",
        "description": "Xung nhịp giật mờ màn hình",
        "speed": 0.24,
        "intensity": 0.55,
    },
    {
        "id": "7663052971227270408",
        "name": "Tín hiệu nhiễu (Signal Interference)",
        "category": "Glitch & Cyberpunk",
        "description": "Nhiễu sóng tín hiệu truyền hình gián đoạn",
        "speed": 0.20,
        "intensity": 0.5,
    },

    # --------------------------------------------------------------------------
    # Category 6: Party & Hộp đêm (Party & Laser)
    # --------------------------------------------------------------------------
    {
        "id": "7677866220128849153",
        "name": "Hộp đêm laser (Laser Nightclub)",
        "category": "Party & Hộp đêm",
        "description": "Chùm tia laser quét phong cách bar / club",
        "speed": 0.28,
        "intensity": 0.65,
    },
    {
        "id": "7625337762262158600",
        "name": "Vũ điệu cầu vồng (Rainbow Dance)",
        "category": "Party & Hộp đêm",
        "description": "Vệt quang phổ cầu vồng rực rỡ đổi màu",
        "speed": 0.22,
        "intensity": 0.5,
    },
    {
        "id": "7675900132633677077",
        "name": "Bánh xe neon (Neon Wheel)",
        "category": "Party & Hộp đêm",
        "description": "Vòng xoay neon phát quang huyền ảo",
        "speed": 0.20,
        "intensity": 0.5,
    },
    {
        "id": "7676835680458132757",
        "name": "Nháy sáng rực (Vibrant Strobe)",
        "category": "Party & Hộp đêm",
        "description": "Nháy chớp vũ trường sôi động",
        "speed": 0.30,
        "intensity": 0.6,
    },
    {
        "id": "7677956245290028295",
        "name": "Nhịp RGB (RGB Rhythm)",
        "category": "Party & Hộp đêm",
        "description": "Đảo sắc màu RGB theo giai điệu",
        "speed": 0.25,
        "intensity": 0.55,
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
            if str(e["id"]) == str(effect_id):
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
        p = os.path.join(BASE_CAPCUT_LOCAL, "User Data", "Cache", "effect", str(effect_id), folder)
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
