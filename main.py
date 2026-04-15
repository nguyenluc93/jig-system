from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import create_engine, Column, Integer, String, Boolean, ForeignKey, DateTime
from sqlalchemy.orm import sessionmaker, declarative_base, Session
from datetime import datetime
import os

# ======================
# DATABASE
# ======================
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./test.db")

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()

app = FastAPI()

# ======================
# CORS (IMPORTANT)
# ======================
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ======================
# MODELS
# ======================

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
    returned_at = Column(DateTime, nullable=True)

class Comment(Base):
    __tablename__ = "comments"
    id = Column(Integer, primary_key=True)
    text = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)

Base.metadata.create_all(bind=engine)

# ======================
# DB SESSION
# ======================
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ======================
# HEALTH CHECK
# ======================
@app.get("/")
def home():
    return {"message": "JIG SYSTEM RUNNING"}

# ======================
# INIT DATA (RUN ONCE)
# ======================
@app.post("/init")
def init_data(db: Session = Depends(get_db)):

    admin = db.query(User).filter_by(username="admin").first()
    if not admin:
        admin = User(username="admin", password="123", role="admin")
        user = User(username="user", password="123", role="user")
        db.add_all([admin, user])

    jig_exist = db.query(JIG).first()
    if not jig_exist:
        jigs = [
            JIG(jig_code="T-1-1-1", name="PRESS JIG A"),
            JIG(jig_code="T-2-2-1", name="CUT JIG B"),
            JIG(jig_code="T-3-3-1", name="FIXTURE C"),
        ]
        db.add_all(jigs)

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
# CREATE USER (ADMIN UI)
# ======================
@app.post("/create_user")
def create_user(data: dict, db: Session = Depends(get_db)):

    exist = db.query(User).filter_by(username=data["username"]).first()
    if exist:
        return {"error": "User already exists"}

    user = User(
        username=data["username"],
        password=data["password"],
        role=data.get("role", "user")
    )

    db.add(user)
    db.commit()

    return {"message": "user created"}

# ======================
# JIG
# ======================
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
    return {"message": "jig created"}

# ======================
# BORROW
# ======================
@app.post("/borrow")
def borrow(data: dict, db: Session = Depends(get_db)):

    session = BorrowSession(user_name=data["user"])
    db.add(session)
    db.commit()
    db.refresh(session)

    for jig_id in data["jig_ids"]:
        jig = db.get(JIG, jig_id)
        if jig:
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
# SESSION INFO
# ======================
@app.get("/session/{session_id}")
def get_session(session_id: int, db: Session = Depends(get_db)):

    items = db.query(SessionItem).filter_by(session_id=session_id).all()

    result = []
    for i in items:
        jig = db.get(JIG, i.jig_id)
        result.append({
            "item_id": i.id,
            "jig_code": jig.jig_code,
            "returned": i.is_returned
        })

    return result

# ======================
# RETURN PARTIAL
# ======================
@app.post("/return")
def return_partial(data: dict, db: Session = Depends(get_db)):

    items = db.query(SessionItem).filter(
        SessionItem.id.in_(data["item_ids"])
    ).all()

    for i in items:
        if not i.is_returned:
            i.is_returned = True
            i.returned_at = datetime.utcnow()

            jig = db.get(JIG, i.jig_id)
            if jig:
                jig.status = "AVAILABLE"

    db.commit()
    return {"message": "partial return done"}

# ======================
# RETURN ALL
# ======================
@app.post("/return_all/{session_id}")
def return_all(session_id: int, db: Session = Depends(get_db)):

    items = db.query(SessionItem).filter_by(session_id=session_id).all()

    for i in items:
        if not i.is_returned:
            i.is_returned = True
            i.returned_at = datetime.utcnow()

            jig = db.get(JIG, i.jig_id)
            if jig:
                jig.status = "AVAILABLE"

    db.commit()
    return {"message": "all returned"}

# ======================
# COMMENT
# ======================
@app.post("/comment")
def add_comment(data: dict, db: Session = Depends(get_db)):
    c = Comment(text=data["text"])
    db.add(c)
    db.commit()
    return {"message": "comment added"}

@app.get("/comments")
def get_comments(db: Session = Depends(get_db)):
    return db.query(Comment).order_by(Comment.id.desc()).all()