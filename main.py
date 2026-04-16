from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import create_engine, Column, Integer, String, Boolean, ForeignKey, DateTime
from sqlalchemy.orm import sessionmaker, declarative_base, Session
from datetime import datetime
import os

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./test.db")

# PostgreSQL on Render cần sslmode
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==========================
# MODELS
# ==========================
class JIG(Base):
    __tablename__ = "jigs"

    id = Column(Integer, primary_key=True)
    jig_code = Column(String, unique=True)
    name = Column(String)
    status = Column(String, default="AVAILABLE")


class BorrowSession(Base):
    __tablename__ = "borrow_sessions"

    id = Column(Integer, primary_key=True)
    user = Column(String)
    session_code = Column(String, unique=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class SessionItem(Base):
    __tablename__ = "session_items"

    id = Column(Integer, primary_key=True)
    session_id = Column(Integer, ForeignKey("borrow_sessions.id"))
    jig_id = Column(Integer, ForeignKey("jigs.id"))
    returned = Column(Boolean, default=False)


class Log(Base):
    __tablename__ = "logs"

    id = Column(Integer, primary_key=True)
    time = Column(DateTime, default=datetime.utcnow)
    user = Column(String)
    action = Column(String)
    detail = Column(String)


Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ==========================
# TEMP BORROW CART
# ==========================
borrow_cart = []


# ==========================
# ROOT
# ==========================
@app.get("/")
def root():
    return {"message": "JIG SYSTEM RUNNING"}


# ==========================
# JIG APIs
# ==========================
@app.get("/jigs")
def get_jigs(db: Session = Depends(get_db)):
    return db.query(JIG).all()


@app.post("/add_jig")
def add_jig(data: dict, db: Session = Depends(get_db)):
    jig = JIG(
        jig_code=data["jig_code"],
        name=data["name"],
        status="AVAILABLE"
    )
    db.add(jig)
    db.commit()
    return {"message": "JIG added"}


# ==========================
# SCAN BOX QR
# ==========================
@app.post("/scan_box")
def scan_box(data: dict, db: Session = Depends(get_db)):
    jig = db.query(JIG).filter_by(jig_code=data["jig_code"]).first()

    if not jig:
        return {"error": "JIG not found"}

    if jig.status == "BORROWED":
        return {"error": "Already borrowed"}

    if jig.id not in borrow_cart:
        borrow_cart.append(jig.id)

    return {"message": "Added to borrow cart"}


# ==========================
# CONFIRM BORROW
# ==========================
@app.post("/confirm_borrow")
def confirm_borrow(data: dict, db: Session = Depends(get_db)):
    if not borrow_cart:
        return {"error": "Cart empty"}

    session_code = f"SESSION-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"

    borrow_session = BorrowSession(
        user=data["user"],
        session_code=session_code
    )

    db.add(borrow_session)
    db.commit()
    db.refresh(borrow_session)

    for jig_id in borrow_cart:
        jig = db.query(JIG).filter_by(id=jig_id).first()
        jig.status = "BORROWED"

        item = SessionItem(
            session_id=borrow_session.id,
            jig_id=jig_id,
            returned=False
        )
        db.add(item)

    log = Log(
        user=data["user"],
        action="BORROW",
        detail=session_code
    )
    db.add(log)

    db.commit()
    borrow_cart.clear()

    return {
        "message": "Borrow confirmed",
        "session_code": session_code
    }


# ==========================
# RETURN SESSION
# ==========================
@app.post("/return_session")
def return_session(data: dict, db: Session = Depends(get_db)):
    session = db.query(BorrowSession).filter_by(
        session_code=data["session_code"]
    ).first()

    if not session:
        return {"error": "Session not found"}

    items = db.query(SessionItem).filter_by(
        session_id=session.id,
        returned=False
    ).all()

    for item in items:
        item.returned = True
        jig = db.query(JIG).filter_by(id=item.jig_id).first()
        jig.status = "AVAILABLE"

    log = Log(
        user=data["user"],
        action="RETURN",
        detail=data["session_code"]
    )
    db.add(log)

    db.commit()

    return {"message": "Returned"}


# ==========================
# LOGS
# ==========================
@app.get("/logs")
def get_logs(db: Session = Depends(get_db)):
    return db.query(Log).order_by(Log.id.desc()).all()