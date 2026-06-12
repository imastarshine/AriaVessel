import aria2p
from src.shared import ARIA2_SECRET

aria2 = aria2p.API(aria2p.Client(host="http://localhost", port=6800, secret=ARIA2_SECRET))
