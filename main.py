from fastapi import FastAPI
import uvicorn

from apps.router import router
from apps.app01 import user
from apps.app02 import geometry
from apps.app03 import optimize

from tortoise.contrib.fastapi import register_tortoise
from settings import TORTOISE_ORM_sqlite


app = FastAPI()


register_tortoise(
    app,
    config=TORTOISE_ORM_sqlite
)

app.include_router(router)
app.include_router(user, prefix="/user", tags=["用户部分", ])
app.include_router(geometry, prefix="/geometry", tags=["几何建模", ])
app.include_router(optimize, prefix="/optimize", tags=["设计优化", ])

if __name__ == '__main__':
    uvicorn.run("main:app", host="127.0.0.1", port=8080,  reload=True)



