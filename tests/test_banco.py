import pytest

from aprendermcp import server

pytestmark = pytest.mark.anyio   # todos los tests de este archivo son async

TRANSFERENCIA = {"origen": "CTA-001", "destino": "CTA-002", "monto": 1_000}

async def test_consultar_saldo_cuenta_existente(conectar):
    # Act
    async with conectar() as client:
        r = await client.call_tool("consultar_saldo", {"cuenta_id": "CTA-001"})
    # Assert
    assert not r.is_error
    assert "500,000" in r.content[0].text

async def test_consultar_saldo_cuenta_inexistente(conectar):
    async with conectar() as client:
        r = await client.call_tool("consultar_saldo", {"cuenta_id": "CTA-999"})
    assert r.is_error
    assert "CTA-XXX" in r.content[0].text


@pytest.mark.parametrize("action, content", [
    ("accept", {"confirmar": False}),
    ("decline", None),
    ("cancel", None),
])
async def test_no_transfiere_sin_confirmacion_explicita(conectar, action, content):
    async with conectar(action, content) as client:
        r = await client.call_tool(
            "transferir", {"origen": "CTA-001", "destino": "CTA-002", "monto": 1_000}
        )
    assert r.is_error
    assert server.CUENTAS["CTA-001"]["saldo"] == 500_000   # no se movió dinero
    assert server.CUENTAS["CTA-002"]["saldo"] == 120_000

async def test_transferencia_confirmada(conectar, formularios):
    async with conectar("accept", {"confirmar": True}) as client:
        r = await client.call_tool("transferir", TRANSFERENCIA)
    assert not r.is_error
    assert len(formularios) == 1
    assert server.CUENTAS["CTA-001"]["saldo"] == 499_000
    assert server.CUENTAS["CTA-002"]["saldo"] == 121_000

async def test_monto_sobre_limite(conectar, formularios):
    async with conectar("accept", {"confirmar": True}) as client:
        r = await client.call_tool("transferir", {**TRANSFERENCIA, "monto": 300_000})
    assert r.is_error
    assert formularios == []
    assert "200,000" in r.content[0].text

async def test_consultar_saldo_normaliza(conectar):
    async with conectar() as client:
        r = await client.call_tool("consultar_saldo", {"cuenta_id": " cta-001"})
    assert not r.is_error
    assert "500,000" in r.content[0].text

async def test_destino_inexistente(conectar, formularios):
    async with conectar("accept", {"confirmar": True}) as client:
        r = await client.call_tool("transferir", {**TRANSFERENCIA, "destino": "CTA-999"})
    assert r.is_error
    assert formularios == []
    assert server.CUENTAS["CTA-001"]["saldo"] == 500_000
    assert "no existe" in r.content[0].text

async def test_misma_cuenta(conectar, formularios):
    async with conectar("accept", {"confirmar": True}) as client:
        r = await client.call_tool("transferir", {**TRANSFERENCIA, "destino": "CTA-001"})
    assert r.is_error
    assert formularios == []
    assert server.CUENTAS["CTA-001"]["saldo"] == 500_000
    assert "no pueden ser la misma" in r.content[0].text


async def test_fondos_insuficientes(conectar, formularios):
    async with conectar("accept", {"confirmar": True}) as client:
        r = await client.call_tool("transferir", {"origen": "CTA-002", "destino": "CTA-001", "monto": 190_000})
    assert r.is_error
    assert formularios == []
    assert "120,000" in r.content[0].text

async def test_formulario_muestra_titular(conectar, formularios):
    async with conectar("accept", {"confirmar": True}) as client:
        await client.call_tool("transferir", TRANSFERENCIA)
    assert "Juan Pérez" in formularios[0]

async def test_reglamento(conectar):
    async with conectar() as client:
        r = await client.read_resource("banco://reglamento")
    assert f"${server.LIMITE_POR_TRANSFERENCIA:,}" in r.contents[0].text

async def test_prompt(conectar):
    async with conectar() as client:
        r = await client.get_prompt("planificar_transferencia", {"origen": "CTA-001", "destino": "CTA-002", "monto": "300000"})
    assert len(r.messages) == 2
    assert server.reglamento() in r.messages[0].content.text
    assert all(m.role in ("user", "assistant") for m in r.messages)