from bson import ObjectId

from app.core.f29.score import calculator as calc_module
from app.core.f29 import constants
from app.core.f29.score.calculator import HealthScoreCalculator
from app.core.f29.constants import STORE_DB

PRINT_ID = "6ad41ed60cc60d253a19a426"
PLAIN_ID = "6ad329c68f56419047cc310c"
BEN_THANH_ID = "6ad423e851d35d40306868ae"
SHOW_HIDDEN = {"seed_ref": {"$exists": False}}


def _print_id(calc: HealthScoreCalculator) -> str:
    products = calc.live_db["products"]
    if products.find_one({"_id": ObjectId(PRINT_ID), "design_placements.0": {"$exists": True}}, {"_id": 1}):
        return PRINT_ID
    return str(products.find_one({"design_placements.0": {"$exists": True}}, {"_id": 1})["_id"])


def _score(calc: HealthScoreCalculator, pid: str) -> dict:
    result = calc.calculate(pid)
    if result is None or "error" in result:
        raise SystemExit(f"{pid}: không chấm được ({result})")
    assert calc.save(result) == pid
    return result


def _show(name: str, pid: str, result: dict) -> None:
    print(f"\n== {name} {pid}  score={result['score']}  status={result['status']}")
    print(f"  so check description_*: {sum(c['id'].startswith('description_') for c in result['checks'])}")
    for c in result["checks"]:
        print(f"  {c['id']:<34} {c['severity']:<6} {c['action']}")


def main() -> None:
    assert STORE_DB == "vietcraft-test", STORE_DB
    calc_module.LOC_SP_THAT = SHOW_HIDDEN
    calc = HealthScoreCalculator()
    print_pid = _print_id(calc)
    results = {}
    for name, pid in (("in", print_pid), ("ao_tron", PLAIN_ID), ("cho_ben_thanh", BEN_THANH_ID)):
        results[name] = (pid, _score(calc, pid))
        _show(name, pid, results[name][1])
    removed = constants.store_db()["f29_image_index"].delete_many({"product_id": print_pid}).deleted_count
    print(f"\nĐã xoá {removed} dòng f29_image_index của sản phẩm ẩn {print_pid} trong vietcraft-test")

    for name, (pid, result) in results.items():
        assert isinstance(result.get("checks"), list), f"{name}: thiếu checks"
    in_checks = results["in"][1]["checks"]
    assert any(c["id"].startswith("print_dpi:") and c["severity"] == "block" for c in in_checks), "in: thiếu print_dpi block"
    ben_checks = results["cho_ben_thanh"][1]["checks"]
    assert any(c["id"].startswith("duplicate_same_shop:") and c["severity"] == "warn" for c in ben_checks), \
        "Chợ Bến Thành: thiếu duplicate_same_shop warn"
    print("\nSMOKE OK")


if __name__ == "__main__":
    main()
