from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import create_engine, Column, Integer, String, Boolean, ForeignKey, DateTime
from sqlalchemy.orm import sessionmaker, declarative_base, Session
from datetime import datetime
import os

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./test.db")

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

# ================= MODELS =================
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    username = Column(String, unique=True)
    password = Column(String)
    role = Column(String)

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
    returned_at = Column(DateTime)

class Comment(Base):
    __tablename__ = "comments"
    id = Column(Integer, primary_key=True)
    text = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)

Base.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ================= INIT =================
@app.post("/init")
def init(db: Session = Depends(get_db)):
    if not db.query(User).first():
        db.add_all([
            User(username="admin", password="123", role="admin"),
            User(username="user", password="123", role="user")
        ])

    if not db.query(JIG).first():
        db.add_all([
            JIG(jig_code="T-1-1-1", name="PRESS JIG"),
            JIG(jig_code="T-2-2-1", name="FIXTURE JIG"),
        ])

    db.commit()
    return {"message": "INIT DONE"}

# ================= LOGIN =================
@app.post("/login")
def login(data: dict, db: Session = Depends(get_db)):
    return db.query(User).filter_by(
        username=data["user"],
        password=data["pass"]
    ).first() or {}

# ================= USERS =================
@app.post("/create_user")
def create_user(data: dict, db: Session = Depends(get_db)):
    if db.query(User).filter_by(username=data["username"]).first():
        return {"error": "exists"}

    db.add(User(**data))
    db.commit()
    return {"message": "user created"}

@app.get("/users")
def users(db: Session = Depends(get_db)):
    return db.query(User).all()

@app.delete("/user/{id}")
def delete_user(id: int, db: Session = Depends(get_db)):
    db.query(User).filter_by(id=id).delete()
    db.commit()
    return {"message": "deleted"}

# ================= JIG =================
@app.get("/jigs")
def get_jigs(db: Session = Depends(get_db)):
    return db.query(JIG).all()

@app.post("/add_jig")
def add_jig(data: dict, db: Session = Depends(get_db)):
    db.add(JIG(**data))
    db.commit()
    return {"message": "jig created"}

@app.delete("/jig/{id}")
def delete_jig(id: int, db: Session = Depends(get_db)):
    db.query(JIG).filter_by(id=id).delete()
    db.commit()
    return {"message": "deleted"}

# ================= BORROW =================
@app.post("/borrow")
def borrow(data: dict, db: Session = Depends(get_db)):

    session = BorrowSession(user_name=data["user"])
    db.add(session)
    db.commit()
    db.refresh(session)

    for jid in data["jig_ids"]:
        jig = db.get(JIG, jid)
        if jig:
            jig.status = "BORROWED"
            db.add(SessionItem(session_id=session.id, jig_id=jid))

    db.commit()
    return {"session_id": session.id}

# ================= RETURN PARTIAL =================
@app.post("/return")
def return_partial(data: dict, db: Session = Depends(get_db)):

    items = db.query(SessionItem).filter(SessionItem.id.in_(data["item_ids"])).all()

    for i in items:
        if not i.is_returned:
            i.is_returned = True
            i.returned_at = datetime.utcnow()

            jig = db.get(JIG, i.jig_id)
            jig.status = "AVAILABLE"

    db.commit()
    return {"message": "partial done"}

@app.post("/return_all/{sid}")
def return_all(sid: int, db: Session = Depends(get_db)):

    items = db.query(SessionItem).filter_by(session_id=sid).all()

    for i in items:
        i.is_returned = True
        i.returned_at = datetime.utcnow()
        db.get(JIG, i.jig_id).status = "AVAILABLE"

    db.commit()
    return {"message": "all returned"}

# ================= COMMENT =================
@app.post("/comment")
def add_comment(data: dict, db: Session = Depends(get_db)):
    db.add(Comment(text=data["text"]))
    db.commit()
    return {"message": "ok"}

@app.get("/comments")
def get_comments(db: Session = Depends(get_db)):
    return db.query(Comment).order_by(Comment.id.desc()).all()

@app.delete("/comment/{id}")
def delete_comment(id: int, db: Session = Depends(get_db)):
    db.query(Comment).filter_by(id=id).delete()
    db.commit()
    return {"message": "deleted"}