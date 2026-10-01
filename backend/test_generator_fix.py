"""发电机导出/导入修复点的端到端校验（TestClient，内存 store 每次重启重置）。"""
import csv
import io

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def reset_store():
    from app.store import store
    from app.seed import SEED_ROWS
    store._tables = {name: [dict(row) for row in rows] for name, rows in SEED_ROWS.items()}
    # 重置导入指纹
    from app.routers.generator import service
    service._import_fingerprints.clear()


def parse_csv(text):
    return list(csv.reader(io.StringIO(text.lstrip("﻿"))))


results = []

def check(name, cond, detail=""):
    results.append((name, cond, detail))
    print(("PASS" if cond else "FAIL"), name, detail)


# ---------- 导出 ----------
reset_store()
r = client.get("/api/generator/export")
check("export 路由可访问（不再被 /{id} 吞掉）", r.status_code == 200, str(r.status_code))
rows = parse_csv(r.text)
header = rows[0]
expected = ["发电机编号", "所属机组", "额定电压", "绝缘电阻", "轴承温度", "上次检测日", "检测结论", "发电机状态"]
check("导出列含绝缘电阻、轴承温度", header[:5] == expected[:5], str(header))
check("导出列与详情页完全一致且不重复", header == expected and len(header) == len(set(header)), str(header))

# 同一台发电机编号重复的情况
from app.store import store
dup = dict(store.rows("generator")[0])
dup.pop("id")
dup_row = {"id": 99, **dup}
store.rows("generator").append(dup_row)
r = client.get("/api/generator/export")
data_rows = parse_csv(r.text)[1:]
codes = [row[0] for row in data_rows]
check("同一台发电机不出现重复行", len(codes) == len(set(codes)), str(codes))

r_list = client.get("/api/generator")
list_codes = [item["发电机编号"] for item in r_list.json()["items"]]
check("列表接口同样去重", len(list_codes) == len(set(list_codes)), str(list_codes))

# 导出取当前过滤条件全量（不受分页影响）
for i in range(50):
    store.rows("generator").append({
        "id": 1000 + i, "status": "检测合格", "pending": True, "abnormal": False,
        "发电机编号": f"GENE-B{i:03d}", "所属机组": "X", "额定电压": "690",
        "绝缘电阻": "100", "轴承温度": "40", "上次检测日": "2026-09-01",
        "检测结论": "合格", "发电机状态": "检测合格",
    })
r = client.get("/api/generator/export?status=检测合格")
data_rows = parse_csv(r.text)[1:]
expected_count = sum(1 for row in store.rows("generator") if row["status"] == "检测合格" and row["发电机编号"] != "GENE-0001")
check("导出按当前状态条件取全量、不分页", len(data_rows) == expected_count, f"{len(data_rows)} vs {expected_count}")

# ---------- 导入：逐行校验，坏行单列，成功保留 ----------
reset_store()
content = "\n".join([
    "发电机编号,所属机组,额定电压,绝缘电阻,轴承温度,上次检测日,检测结论,发电机状态",
    "GENE-1001,T-01,690,120,32,2026-09-01,合格,检测合格",
    "GENE-1002,T-02,690V,120MΩ,32℃,2026-09-01,合格,检测合格",  # 三个数值列带单位
    "GENE-1003,T-03,690,120,32,2026/09/01,合格,未知状态",        # 日期与状态都错
    "GENE-1004,,690,120,32,2026-09-01,合格,检测合格",            # 缺必填
])
r = client.post("/api/generator/import", json={"filename": "history.csv", "content": content})
body = r.json()
check("部分成功时整体不拦截", r.status_code == 200 and body["ok"] is True, str(body.get("message")))
check("成功行入库保留", body["imported"] == 1, str(body["imported"]))
check("坏行数量正确", body["failed"] == 3, str(body["failed"]))
reasons = {f["line"]: f["reason"] for f in body["failures"]}
check("带单位行给出具体原因与行号", 3 in reasons and "绝缘电阻" in reasons[3] and "32℃" in reasons[3], reasons.get(3, ""))
check("日期/状态错误分别说明", 4 in reasons and "上次检测日" in reasons[4] and "发电机状态" in reasons[4], reasons.get(4, ""))
check("缺必填字段说明字段名", 5 in reasons and "所属机组" in reasons[5], reasons.get(5, ""))

r = client.get("/api/generator?keyword=GENE-1001")
check("已成功解析的行在导入后可查询到", len(r.json()["items"]) == 1)

# 同一文件再导一次
r2 = client.post("/api/generator/import", json={"filename": "history.csv", "content": content})
b2 = r2.json()
check("同一文件重复导入标记 duplicated", b2["duplicated"] is True and b2["imported"] == 0, str(b2.get("message")))
r = client.get("/api/generator?keyword=GENE-1001")
check("重复导入不产生第二条记录", r.json()["total"] == 1)

# 文件内同编号重复
content2 = "\n".join([
    "发电机编号,所属机组,额定电压,绝缘电阻,轴承温度,上次检测日,检测结论,发电机状态",
    "GENE-2001,T-01,690,120,32,2026-09-01,合格,检测合格",
    "GENE-2001,T-01,690,120,32,2026-09-01,合格,检测合格",
])
r = client.post("/api/generator/import", json={"content": content2})
b = r.json()
check("文件内重复编号第二行报错", b["imported"] == 1 and any(f["line"] == 3 for f in b["failures"]), str(b["failures"]))

# 与库里已有编号冲突（换一份不同内容的文件，先过文件去重）
conflict = "发电机编号,所属机组,额定电压,绝缘电阻,轴承温度,上次检测日,检测结论,发电机状态\nGENE-2001,T-01,690,120,32,2026-09-01,合格,检测合格\n"
r = client.post("/api/generator/import", json={"content": conflict})
b = r.json()
check("与库内已有编号冲突的行被拦", b["ok"] is False and b["imported"] == 0 and "已存在" in b["failures"][0]["reason"], str(b["failures"]))

# 全部坏行：不登记指纹，修好后允许再次提交
bad = "发电机编号,所属机组\nGENE-BAD,,\n"
r = client.post("/api/generator/import", json={"content": bad})
check("全坏行 ok=False 且无新增", r.json()["ok"] is False and r.json()["imported"] == 0)
fixed = "发电机编号,所属机组\nGENE-OK,T-09\n"
r = client.post("/api/generator/import", json={"content": fixed})
check("修正后可正常导入（全坏行不占指纹）", r.json()["imported"] == 1)

# 空文件 / 缺表头
check("空内容被拦下", client.post("/api/generator/import", json={"content": ""}).json()["ok"] is False)
r = client.post("/api/generator/import", json={"content": "编号,所属机组\nX,T\n"})
check("缺少发电机编号列给文件级说明", r.json()["ok"] is False and "发电机编号" in r.json()["message"])

failed = [name for name, ok, _ in results if not ok]
print(f"\n{len(results) - len(failed)}/{len(results)} passed")
raise SystemExit(1 if failed else 0)
