"""Pruebas reales del protocolo stdio y consultas individuales oficiales."""
import asyncio
import json
import hashlib
import sys
from pathlib import Path
from fastmcp import Client
from fastmcp.client.transports import StdioTransport


async def main():
    root = Path(__file__).resolve().parent
    report = {"tests": []}
    (root/"smoke-results.json").write_text(json.dumps({"passed": False, "estado": "pruebas_en_curso"}))
    transport = StdioTransport(command=sys.executable, args=[str(root/"server.py")], cwd=str(root))
    async with Client(transport) as client:
        ts = await client.list_tools()
        report["tools"] = [t.name for t in ts]
        assert len(ts) == 14

        async def call(name, args, expected=True):
            r = await client.call_tool(name, args, raise_on_error=False)
            data = r.structured_content
            if data is None:
                data = json.loads(r.content[0].text)
            passed = data.get("ok") is expected and r.is_error is (not expected)
            entry = {"tool": name, "passed": passed, "ok": data.get("ok"), "is_error": r.is_error,
                "consultado_en": data.get("consultado_en"), "url_oficial": data.get("url_oficial")}
            if not passed or not expected:
                entry["error"] = data.get("error")
            report["tests"].append(entry)
            print(json.dumps(entry, ensure_ascii=False), flush=True)
            assert passed, data
            return data

        h = await call("juridico_estado", {})
        assert h["uid_proceso"] != 0, "El servidor no debe consultar fuentes como root"
        assert h["version"] == "1.1.0"
        report["version"] = h["version"]
        await call("boe_metadatos", {"identificador": "BOE-A-2015-10565"})
        idx = await call("boe_indice", {"identificador": "BOE-A-2015-10565", "limite": 5})
        assert idx["datos"]["siguiente_inicio"] == 5
        block = await call("boe_bloque", {"identificador": "BOE-A-2015-10565", "id_bloque": "a6"})
        assert len(block["datos"]["versiones"]) >= 2
        old = await call("boe_bloque", {"identificador": "BOE-A-2015-10565", "id_bloque": "a6", "fecha": "2016-01-01"})
        assert old["datos"]["version_seleccionada"]["fecha_publicacion"] <= "20160101"
        await call("boe_analisis", {"identificador": "BOE-A-2015-10565"})
        search = await call("boe_buscar", {"texto": "procedimiento administrativo", "limite": 3})
        assert search["datos"].get("data"), "Búsqueda BOE vacía inesperada"
        await call("boe_vigencia", {"identificador": "BOE-A-2015-10565"})
        await call("dogv_sumario", {"fecha": "2026-10-23", "limite": 3})
        await call("dogv_buscar", {"texto": "resolución", "fecha": "2026-10-23", "limite": 3})
        global_dogv = await call("dogv_buscar", {"texto": "procedimiento administrativo", "solo_titulo": True, "limite": 2})
        assert global_dogv["datos"]["modo"] == "busqueda_global" and global_dogv["datos"]["total"] > 10
        assert global_dogv["datos"]["publicaciones"][0]["fechaPublicacion"].endswith("2026")
        next_dogv = await call("dogv_buscar", {"texto": "procedimiento administrativo", "solo_titulo": True, "limite": 2, "inicio": 2})
        assert {x["id"] for x in global_dogv["datos"]["publicaciones"]}.isdisjoint({x["id"] for x in next_dogv["datos"]["publicaciones"]})
        await call("dogv_buscar", {"texto": "procedimiento administrativo", "desde": "2026-01-01", "hasta": "2026-10-26", "limite": 2})
        dogv = await call("dogv_publicacion", {"identificador": "DOGV-C-2024-14048"})
        assert len(dogv["datos"]["texto"]) > 100
        recent = await call("ts_buscar", {})
        assert recent["datos"]["resoluciones"], "Sin destacados del Supremo verificables"
        doc = await call("ts_resolucion", {"url": recent["datos"]["resoluciones"][0]["url_oficial"]})
        assert doc["datos"]["ecli_en_documento"] or doc["datos"]["roj_en_documento"]
        ts = await call("ts_buscar", {"consulta": "despido", "sala": "social", "limite": 1})
        assert ts["datos"]["modo"] == "busqueda_general_supremo" and ts["datos"]["total_fuente"] > 1
        first_ts = ts["datos"]["resoluciones"][0]
        ts_next = await call("ts_buscar", {"consulta": "despido", "sala": "social", "limite": 1, "inicio": 1})
        assert ts_next["datos"]["resoluciones"][0]["ecli"] != first_ts["ecli"]
        exact = await call("ts_buscar", {"ecli": first_ts["ecli"], "limite": 1})
        assert exact["datos"]["total_fuente"] == 1 and exact["datos"]["resoluciones"][0]["ecli"] == first_ts["ecli"]
        empty = await call("ts_buscar", {"ecli": "ECLI:ES:TS:2099:99999999", "limite": 1})
        assert empty["datos"]["total_fuente"] == 0 and not empty["datos"]["resoluciones"]
        await call("juridico_buscar", {"fuente": "DOGV", "consulta": "resolución", "fecha": "2026-10-23", "limite": 2})
        await call("juridico_documento", {"fuente": "BOE", "identificador": "BOE-A-2015-10565", "bloque": "a6", "max_caracteres": 1000})
        await call("boe_bloque", {"identificador": "BOE-A-2015-10565", "id_bloque": "../secreto"}, expected=False)
        await call("boe_metadatos", {"identificador": "BOE-A-2099-99999999"}, expected=False)
        await call("ts_resolucion", {"url": "https://127.0.0.1/"}, expected=False)
    report["passed"] = all(t["passed"] for t in report["tests"])
    report["tested_hashes"] = {name:hashlib.sha256((root/name).read_bytes()).hexdigest()
        for name in ("server.py", "juridico.py", "pdf_extract.py", "smoke_mcp.py")}
    (root/"smoke-results.json").write_text(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
