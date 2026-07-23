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

    uvicorn.run(
        app,
        host=application.config.data.server.host,
        port=application.config.data.server.port,
    )


if __name__ == "__main__":
    main()
