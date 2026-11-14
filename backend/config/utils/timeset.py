"""Utilidades semánticas para parametrización temporal de configuración.

SetDays y SetMinutes actúan como anotaciones explícitas de unidades de tiempo
(días y minutos respectivamente) para los campos de configuración.
"""

def SetDays(days: int) -> int:
    """Representa un intervalo en días."""
    return days

def SetMinutes(minutes: int) -> int:
    """Representa un intervalo en minutos."""
    return minutes