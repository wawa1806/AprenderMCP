from mcp.server.mcpserver import (MCPServer, Resolve, 
                                  Elicit, ElicitationResult, AcceptedElicitation,
                                  )
from mcp.server.mcpserver.exceptions import ToolError
from typing import Annotated
from pydantic import BaseModel, Field
from mcp.server.mcpserver import UserMessage

mcp = MCPServer("banco")

# Datos falsos en memoria (simulan la base de datos del banco)
CUENTAS = {
    "CTA-001": {"titular": "Lukas Estay", "saldo": 500_000},
    "CTA-002": {"titular": "Juan Pérez", "saldo": 120_000},
}


LIMITE_POR_TRANSFERENCIA = 200_000  # fuente única de verdad


@mcp.resource("banco://reglamento", mime_type="text/markdown")
def reglamento() -> str:
    """Reglas del banco para transferencias de dinero entre cuentas. Útil antes de planificar
    una transferencia o cuando el usuario pregunte qué está permitido."""

    return f"""Reglas del banco:\n- Monto máximo por transferencia: ${LIMITE_POR_TRANSFERENCIA:,}.\n- No se puede transferir a la misma cuenta.\n- Toda transferencia requiere confirmación del usuario.
        """

@mcp.tool(annotations={"readOnlyHint": True})
def consultar_saldo(cuenta_id: str) -> str:
    """Consulta el saldo de la cuenta bancaria especificada por su ID.
    La ID está especificada en el formato 'CTA-XXX', donde XXX es un número
    de tres dígitos. Esta función es de solo lectura y se debe usar cuando se
    desea obtener información sobre el saldo y el titular de la cuenta sin modificar
    ningún dato en la base de datos."""

    cuenta_id = cuenta_id.strip().upper()  # Normaliza la ID de la cuenta

    if cuenta_id not in CUENTAS:
        raise ToolError(f"La cuenta con ID '{cuenta_id}' no existe. Formato esperado: CTA-XXX (ej. CTA-001). Por favor, verifica el ID y vuelve a intentarlo.")

    return f"Titular: {CUENTAS[cuenta_id]['titular']}, Saldo: ${CUENTAS[cuenta_id]['saldo']:,}"



@mcp.prompt(title="Planificar transferencia")
def planificar_transferencia(
    origen: Annotated[str, Field(description="¿Desde qué cuenta desea transferir?")],
    destino: Annotated[str, Field(description="¿A qué cuenta desea transferir?")],
    monto: Annotated[int, Field(description="¿Cuánto desea transferir?")],
) -> list[UserMessage]:
    """Revisa saldo y reglas, y propone un plan antes de transferir."""

    return [UserMessage(reglamento()),
        UserMessage(f"Quiero transferir ${monto:,} de la cuenta {origen} a la cuenta {destino}.\n"
                    f"1) Consulta el saldo de {origen}\n"
                    f"2) Compara ${monto:,} con el límite de ${LIMITE_POR_TRANSFERENCIA:,} y verifica que no exceda el saldo de la cuenta de {origen}.\n"
                    f"3) Si el monto excede el límite, sugiere un plan, ej; cómo dividirlo en tranferencias pequeñas.\n"
                    f"4) NO llames a `transferir` hasta que el usuario apruebe el plan."),
    ]
class Confirmacion(BaseModel):
    """El formulario que verá el HUMANO."""
    confirmar: bool = Field(description="Marca para autorizar la transferencia")

def pedir_confirmacion(origen: str, destino: str, monto: int) -> Elicit[Confirmacion]:
    """Resolver: corre ANTES del cuerpo de la tool. Recibe los argumentos por nombre"""

    if monto > LIMITE_POR_TRANSFERENCIA:
        raise ToolError(f"El monto de ${monto:,} excede el límite por transferencia de ${LIMITE_POR_TRANSFERENCIA:,}. Por favor, ingresa un monto menor o igual al límite.")

    cuenta_id_origen = origen.strip().upper()  # Normaliza la ID de la cuenta
    cuenta_id_destino = destino.strip().upper()  # Normaliza la ID de la cuenta
    
    if cuenta_id_origen == cuenta_id_destino:
        raise ToolError("La cuenta de origen y destino no pueden ser la misma.")

    if cuenta_id_origen not in CUENTAS:
        raise ToolError(f"La cuenta con ID '{cuenta_id_origen}' no existe. Formato esperado: CTA-XXX (ej. CTA-001). Por favor, verifica el ID y vuelve a intentarlo.")
        
    if cuenta_id_destino not in CUENTAS:
        raise ToolError(f"La cuenta con ID '{cuenta_id_destino}' no existe. Formato esperado: CTA-XXX (ej. CTA-001). Por favor, verifica el ID y vuelve a intentarlo.")
        
    if CUENTAS[cuenta_id_origen]['saldo'] < monto:
        raise ToolError(f"Fondos insuficientes para realizar la transferencia. Tu saldo actual es ${CUENTAS[cuenta_id_origen]['saldo']:,}. Por favor, ingresa un monto menor o igual a tu saldo.")

    return Elicit(f"¿Deseas transferir ${monto:,} de la cuenta {cuenta_id_origen} a la cuenta de Titular: {CUENTAS[cuenta_id_destino]['titular']} con cuenta: {cuenta_id_destino}?",
        Confirmacion)

@mcp.tool(annotations={"readOnlyHint": False, "destructiveHint": True, "idempotentHint": False, "openWorldHint": False})
def transferir(
    origen: str,
    destino: str,
    monto: Annotated[int, Field(gt=0)],
    confirmacion: Annotated[ElicitationResult[Confirmacion], Resolve(pedir_confirmacion)],
) -> str:
    """Transfiere un monto de dinero de una cuenta a otra.
    La ID de las cuentas debe estar en el formato 'CTA-XXX', donde XXX es un número
    de tres dígitos. Esta función modifica los datos de la base de datos y requiere
    confirmación del usuario antes de realizar la transferencia. Límite: $200.000 por transferencia. Ver banco://reglamento."""

    cuenta_id_origen = origen.strip().upper()  # Normaliza la ID de la cuenta
    cuenta_id_destino = destino.strip().upper()  # Normaliza la ID de la cuenta
    
    if cuenta_id_origen not in CUENTAS:
        raise ToolError(f"La cuenta con ID '{cuenta_id_origen}' no existe. Formato esperado: CTA-XXX (ej. CTA-001). Por favor, verifica el ID y vuelve a intentarlo.")
    
    if cuenta_id_destino not in CUENTAS:
        raise ToolError(f"La cuenta con ID '{cuenta_id_destino}' no existe. Formato esperado: CTA-XXX (ej. CTA-001). Por favor, verifica el ID y vuelve a intentarlo.")
    
    
    if not (isinstance(confirmacion, AcceptedElicitation) and confirmacion.data.confirmar):
        raise ToolError("El usuario rechazó la transferencia. No se movió dinero. No lo reintentes" \
        " a menos que el usuario lo indique explícitamente.")
    else:
        # Realiza la transferencia
        CUENTAS[cuenta_id_origen]['saldo'] -= monto
        CUENTAS[cuenta_id_destino]['saldo'] += monto

    return f"Transferencia exitosa de ${monto:,} transferidos desde Titular: {CUENTAS[cuenta_id_origen]['titular']} con cuenta: {cuenta_id_origen} a Titular: {CUENTAS[cuenta_id_destino]['titular']}, cuenta destino: {cuenta_id_destino}."



def main() -> None:
    mcp.run()  # stdio por defecto