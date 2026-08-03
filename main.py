from pathlib import Path

from core.application import Application
from web.server import create_app

import uvicorn


def main():

    application = Application()

    application.logger.info(
        "%s %s started.",
        application.config.data.application.name,
        application.config.data.application.version,
    )

    app = create_app(application)

    server_config = application.config.data.server

    ssl_certfile = Path(server_config.ssl_certfile)
    ssl_keyfile = Path(server_config.ssl_keyfile)

    if ssl_certfile.is_file() and ssl_keyfile.is_file():

        application.logger.info(
            "HTTPS aktiv (selbstsigniertes Zertifikat: %s).",
            ssl_certfile,
        )

        uvicorn.run(
            app,
            host=server_config.host,
            port=server_config.port,
            ssl_certfile=str(ssl_certfile),
            ssl_keyfile=str(ssl_keyfile),
        )

    else:

        application.logger.warning(
            "Kein TLS-Zertifikat gefunden (%s / %s) - Webinterface "
            "läuft unverschlüsselt über HTTP. install.sh ausführen, "
            "um HTTPS einzurichten.",
            ssl_certfile,
            ssl_keyfile,
        )

        uvicorn.run(
            app,
            host=server_config.host,
            port=server_config.port,
        )


if __name__ == "__main__":
    main()
