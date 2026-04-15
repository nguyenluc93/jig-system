from fastapi import FastAPI, Depends
from sqlalchemy import create_engine, Column, Integer, String, Boolean, ForeignKey, DateTime
from sqlalchemy.orm import sessionmaker, declarative_base, Session
from datetime import datetime
import os

# ======================
# CONFIG
# ======================
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./test.db")

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()

app = FastAPI()

# ======================
# MODELS
# ======================

class JIG(Base):
    __tablename__ = "jigs"
    id = Column(Integer, primary_key=True)
    jig_code = Column(String, unique=True)
    name = Column(String)
    status = Column(String, default="AVAILABLE")


class BorrowSession(Base):
    __tablename__ = "borrow_sessions"
    id = Column(Integer, primary_key=True)
    user_name = Column(String)
    status = Column(String, default="ACTIVE")
    created_at = Column(DateTime, default=datetime.utcnow)


class SessionItem(Base):
    __tablename__ = "session_items"
    id = Column(Integer, primary_key=True)
    session_id = Column(Integer, ForeignKey("borrow_sessions.id"))
    jig_id = Column(Integer, ForeignKey("jigs.id"))
    is_returned = Column(Boolean, default=False)
    returned_at = Column(DateTime, nullable=True)


class Comment(Base):
    __tablename__ = "comments"
    id = Column(Integer, primary_key=True)
    text = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    username = Column(String)
    password = Column(String)
    role = Column(String)


Base.metadata.create_all(bind=engine)

# ======================
# DB
# ======================

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ======================
# BASIC
# ======================

@app.get("/")
def home():
    return {"message": "JIG SYSTEM RUNNING"}

# ======================
# INIT DATA
# ======================

@app.post("/init")
def init_data(db: Session = Depends(get_db)):
    jigs = [
        JIG(jig_code="T-1-1-1", name="JIG A"),
        JIG(jig_code="T-2-2-2", name="JIG B"),
        JIG(jig_code="T-3-3-3", name="JIG C"),
    ]
    db.add_all(jigs)

    admin = User(username="admin", password="123", role="admin")
    user = User(username="user", password="123", role="user")

    db.add_all([admin, user])

    db.commit()
    return {"message": "INIT DONE"}

# ======================
# LOGIN
# ======================

@app.post("/login")
def login(data: dict, db: Session = Depends(get_db)):
    user = db.query(User).filter_by(
        username=data["user"],
        password=data["pass"]
    ).first()

    if user:
        return {"username": user.username, "role": user.role}
    return {}

# ======================
# JIG
# ======================

@app.get("/jigs")
def get_jigs(db: Session = Depends(get_db)):
    return db.query(JIG).all()


@app.post("/add_jig")
def add_jig(data: dict, db: Session = Depends(get_db)):
    jig = JIG(jig_code=data["code"], name=data["code"])
    db.add(jig)
    db.commit()
    return {"ok": True}

# ======================
# BORROW
# ======================

@app.post("/borrow")
def borrow(data: dict, db: Session = Depends(get_db)):
    user_name = data["user"]
    jig_ids = data["jig_ids"]

    session = BorrowSession(user_name=user_name)
    db.add(session)
    db.commit()
    db.refresh(session)

    for jig_id in jig_ids:
        jig = db.get(JIG, jig_id)

        if jig.status != "AVAILABLE":
            return {"error": f"{jig.jig_code} not available"}

        jig.status = "BORROWED"

        item = SessionItem(
            session_id=session.id,
            jig_id=jig_id
        )
        db.add(item)

    db.commit()

    return {
        "session_id": session.id,
        "qr_url": f"/session/{session.id}"
    }

# ======================
# SESSION
# ======================

@app.get("/session/{session_id}")
def get_session(session_id: int, db: Session = Depends(get_db)):
    items = db.query(SessionItem).filter_by(session_id=session_id).all()

    result = []
    for item in items:
        jig = db.get(JIG, item.jig_id)
        result.append({
            "item_id": item.id,
            "jig_code": jig.jig_code,
            "returned": item.is_returned
        })

    return result

# ======================
# RETURN
# ======================

@app.post("/return")
def return_partial(data: dict, db: Session = Depends(get_db)):
    session_id = data["session_id"]
    item_ids = data["item_ids"]

    items = db.query(SessionItem).filter(SessionItem.id.in_(item_ids)).all()

    for item in items:
        if not item.is_returned:
            item.is_returned = True
            item.returned_at = datetime.utcnow()

            jig = db.get(JIG, item.jig_id)
            jig.status = "AVAILABLE"

    db.commit()

    return {"message": "Partial return done"}


@app.post("/return_all/{session_id}")
def return_all(session_id: int, db: Session = Depends(get_db)):
    items = db.query(SessionItem).filter_by(session_id=session_id).all()

    for item in items:
        if not item.is_returned:
            item.is_returned = True
            item.returned_at = datetime.utcnow()

            jig = db.get(JIG, item.jig_id)
            jig.status = "AVAILABLE"

    session = db.get(BorrowSession, session_id)
    session.status = "CLOSED"

    db.commit()

    return {"message": "All returned"}

# ======================
# COMMENT
# ======================

@app.post("/comment")
def add_comment(data: dict, db: Session = Depends(get_db)):
    c = Comment(text=data["text"])
    db.add(c)
    db.commit()
    return {"ok": True}


@app.get("/comments")
def get_comments(db: Session = Depends(get_db)):
    return db.query(Comment).order_by(Comment.id.desc()).all()