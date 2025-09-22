from api.p2 import app
from mangum import Mangum

handler = Mangum(app)
