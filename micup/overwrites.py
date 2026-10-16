"""Kanal izin üzerine yazmaları (permission_overwrites) için yardımcılar.

Micup bir kanalın izinlerini kanal nesnesindeki `permission_overwrites` listesi olarak döndürür:
    {"id": "...", "type": 0, "allow": "1048576", "deny": "2048"}
Bir bit ya izinlidir (allow), ya yasaklıdır (deny), ya da ayarlanmamıştır. Aynı bit iki listede birden olamaz.
Sunucuya tüm liste geri gönderildiği için önce listeyi okuyup yalnızca hedef girişi değiştiriyoruz.
"""
from typing import Any, Dict, List, Optional


def _normalize(ow: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": str(ow["id"]),
        "type": int(ow.get("type", 0) or 0),
        "allow": str(int(ow.get("allow", 0) or 0)),
        "deny": str(int(ow.get("deny", 0) or 0)),
    }


def merge_overwrites(
    existing: List[Dict[str, Any]],
    target_id: str,
    *,
    allow: int = 0,
    deny: int = 0,
    type: Optional[int] = None,
    remove: bool = False,
) -> List[Dict[str, Any]]:
    """Mevcut listeden `target_id` girişini çıkarıp (remove=True) ya da yeni allow/deny değerleriyle değiştirip
    güncellenmiş listeyi döndürür. Diğer girişlere dokunmaz.

    type: None ise hedefin mevcut tipi korunur (yoksa 0 = rol kabul edilir).
    """
    if allow < 0 or deny < 0:
        raise ValueError("allow ve deny negatif olamaz")
    if allow & deny:
        raise ValueError("Aynı izin hem allow hem deny içinde olamaz")

    target = str(target_id)
    out: List[Dict[str, Any]] = []
    eski_tip: Optional[int] = None
    for ow in existing or []:
        if str(ow.get("id")) == target:
            eski_tip = int(ow.get("type", 0) or 0)
            continue
        out.append(_normalize(ow))

    if remove:
        return out

    tip = type if type is not None else (eski_tip if eski_tip is not None else 0)
    out.append({"id": target, "type": int(tip), "allow": str(allow), "deny": str(deny)})
    return out
