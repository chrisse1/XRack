from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def index(request: Request):

    application = request.app.state.application

    return request.app.state.templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "application": application,
        },
    )


@router.get("/api/status")
async def status(request: Request):

    application = request.app.state.application

    application.update_status()

    return application.status.model_dump()
