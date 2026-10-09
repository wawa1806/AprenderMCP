import copy

import pytest
from mcp.client import Client
from mcp.types import ElicitResult

from aprendermcp import server

@pytest.fixture
def anyio_backend():
    """Le dice a pytest que corre los test async con asyncio"""
    return "asyncio"


@pytest.fixture(autouse=True)
def cuentas_limpias():
    """Antes de cada test guarda CUENTAS; después lo restaura."""
    original = copy.deepcopy(server.CUENTAS)
    yield                                  
    server.CUENTAS.clear()
    server.CUENTAS.update(original)

@pytest.fixture
def formularios():
    """Lista donde se registra cada formulario de elicitation que vio el 'usuario'."""
    return []

@pytest.fixture
def conectar(formularios):
    """"Crea un client MCP en memoria que simula al usuario"""
    def _conectar(action="accept", content=None):
        async def usuario_simulado(context, params):
            formularios.append(params.message)
            return ElicitResult(action=action, content=content)

        return Client(server.mcp, elicitation_callback=usuario_simulado)
    return _conectar


        