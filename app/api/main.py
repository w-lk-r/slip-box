from fastapi import FastAPI
from mangum import Mangum

from routers import edges, graph, ingest, items, uploads

app = FastAPI(title="Slip Box API")
app.include_router(ingest.router)
app.include_router(items.router)
app.include_router(graph.router)
app.include_router(edges.router)
app.include_router(uploads.router)

handler = Mangum(app)
