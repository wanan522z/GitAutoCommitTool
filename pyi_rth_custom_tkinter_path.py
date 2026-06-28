import sys


meipass = getattr(sys, "_MEIPASS", None)
if meipass and meipass not in sys.path:
    sys.path.insert(0, meipass)
