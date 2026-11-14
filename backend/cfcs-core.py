# Desarrollado por JanTime (NesANTIME)  
# --------------------------------------

import uvicorn

def main():
    print("[cfcs-core] cargando configuracion...")
    
    try:
        from config.load import CONFIG
        print("[cfcs-core] configuracion cargada correctamente!")

        uvicorn.run(
            "core.app:app", 
            host = CONFIG.Red.Host, 
            port = int(CONFIG.Red.Port), 
            proxy_headers = True,
            forwarded_allow_ips = CONFIG.Red.Trusted_proxies,
        )

    except Exception as e:
        import traceback
        print(f"[cfcs-core] Error al cargar o iniciar el servidor: {e}")
        traceback.print_exc()
        raise SystemExit(1)

if __name__ == "__main__":
    main()